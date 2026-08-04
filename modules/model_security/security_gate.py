#!/usr/bin/env python3
"""
UPGRADE RUN 1 — Kernel-level, model-agnostic security gate.

Decision: the security pipeline should be UNMISSABLE — enforced by the kernel
itself on every model/event call, not left to optional per-module opt-in. This
adds a `SecurityGate` that wraps a model callable and injects the full
InputSanitizer -> PromptInjectionShield -> JailbreakShield -> (model) ->
OutputValidator -> AuditLogger pipeline around it, blocking before any content
reaches a model and redacting before any response leaves.

Stdlib-only. Works with ANY model backend because it sits at the call boundary.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from enterprise.modules.model_security.model_security import (
    AuditLogger,
    GuardAction,
    InputSanitizer,
    JailbreakShield,
    OutputValidator,
    PipelineResult,
    PromptInjectionShield,
    SecurityPipeline,
)

logger = logging.getLogger("eni.security_gate")


@dataclass
class SecurityGateStats:
    total: int = 0
    blocked_input: int = 0
    redacted_output: int = 0
    passed: int = 0
    last_blocked_reason: str = ""
    by_action: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "blocked_input": self.blocked_input,
            "redacted_output": self.redacted_output,
            "passed": self.passed,
            "last_blocked_reason": self.last_blocked_reason,
            "by_action": self.by_action,
        }


class SecurityGate:
    """
    Wrap any model-callable so every request passes the full security pipeline.

    Usage:
        gate = SecurityGate(config)
        safe_model = gate.wrap(my_model_callable)   # now returns PipelineResult
        result = safe_model(prompt)                 # guards run automatically

    Or directly:
        result = gate.execute(prompt, model_fn)     # PipelineResult with final_output
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self.pipeline = SecurityPipeline({
            "audit_path": cfg.get("audit_path", "data/security_gate_audit.log"),
            "policy_path": cfg.get("policy_path", "config/security_policies.yaml"),
            "injection_threshold": cfg.get("injection_threshold", 0.7),
            "jailbreak_threshold": cfg.get("jailbreak_threshold", 0.7),
            "toxicity_threshold": cfg.get("toxicity_threshold", 0.7),
            "refusal_threshold": cfg.get("refusal_threshold", 0.8),
        })
        self.stats = SecurityGateStats()
        self._lock = threading.RLock()

    def execute(
        self,
        prompt: str,
        model_fn: Callable[[str], str],
        model_name: str = "model",
        model_type: str = "cloud",
    ) -> PipelineResult:
        """Run the full pipeline around model_fn. Returns PipelineResult."""
        with self._lock:
            # Pre-block check (fast path) so we short-circuit before model.
            sanitized, placeholders = self.pipeline.sanitizer.sanitize(prompt)
            project_context = {
                "has_secrets": len(placeholders) > 0,
                "target_model": {"type": model_type, "name": model_name},
            }
            inj = self.pipeline.injection_shield.scan(sanitized)
            jb = self.pipeline.jailbreak_shield.scan(sanitized)
            if not inj.passed or not jb.passed:
                reason = "prompt_injection" if not inj.passed else "jailbreak"
                self.stats.total += 1
                self.stats.blocked_input += 1
                self.stats.by_action["block"] = self.stats.by_action.get("block", 0) + 1
                self.stats.last_blocked_reason = reason
                self.pipeline.audit_logger.log(
                    "security_gate", model_name, "blocked_input", {"reason": reason}
                )
                return PipelineResult(
                    passed=False, final_output="", stage_results={},
                    placeholder_map=placeholders,
                    routing_decision=f"gate_block:{reason}",
                    model_used=model_name, duration_ms=0,
                )

            # Run the full pipeline (this re-runs sanitize; acceptable, keeps gate hermetic)
            result = self.pipeline.execute(
                prompt, model_fn, model_name, model_type
            )
            self.stats.total += 1
            if not result.passed:
                self.stats.blocked_input += 1 if result.routing_decision.startswith("gate_block") else self.stats.blocked_input
                self.stats.by_action[result.stage_results.get("output_validation", None).action.value if result.stage_results.get("output_validation") else "?"] = \
                    self.stats.by_action.get("?", 0) + 1
            else:
                self.stats.passed += 1
                self.stats.by_action["allow"] = self.stats.by_action.get("allow", 0) + 1

            self.pipeline.audit_logger.log(
                "security_gate", model_name, "done",
                {"passed": result.passed, "routing": result.routing_decision},
            )
            return result

    def wrap(self, model_fn: Callable[[str], str], model_name: str = "model",
             model_type: str = "cloud") -> Callable[[str], PipelineResult]:
        """Return a wrapper callable that applies the gate to model_fn."""
        def _wrapped(prompt: str) -> PipelineResult:
            return self.execute(prompt, model_fn, model_name, model_type)
        return _wrapped

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return self.stats.to_dict()

    def verify_audit(self) -> bool:
        ok, _ = self.pipeline.audit_logger.verify_chain()
        return ok
