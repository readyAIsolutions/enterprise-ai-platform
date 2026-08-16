"""AI Coding Harness module — repeatable agentic Claude-Code coding workflows.

Implements the prompt->scaffold->generate->iterate->verify loop that
JE Van Clief demonstrates across four transcripts (websites from a prompt,
installing Claude Code, SVG-to-React animations, and the Remotion
script->spec->scenes->render pipeline).

The pure, offline engine lives in :mod:`harness`; this file wires it into the
ENI platform kernel as a registered module.

Public export surface:
  * AiCodingHarness        — the core engine (context, scaffold, plan, generate,
                             verify, iterate, run_stages).
  * ContextSpec, ScaffoldSpec, Artifact, GenerationPlan, VerificationResult,
    ArtifactKind, PipelineStage — value types surfaced by the engine.
  * create_ai_coding_harness()  — build a bare engine.
  * create_ai_coding_harness_module(config) — build the kernel module.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import HealthStatus, Module, module

from .harness import (  # noqa: F401
    AiCodingHarness,
    Artifact,
    ArtifactKind,
    ContextSpec,
    GenerationPlan,
    PipelineStage,
    ScaffoldSpec,
    VerificationResult,
    default_context,
)

logger = logging.getLogger("eni.ai_coding_harness")
__version__ = "1.0.0"


def create_ai_coding_harness(config: Optional[dict[str, Any]] = None) -> AiCodingHarness:
    """Facade: construct and return the core engine."""
    cfg = config or {}
    context = None
    spec = cfg.get("context")
    if isinstance(spec, dict):
        context = ContextSpec(
            role=spec.get("role", "agentic coding harness"),
            read_paths=list(spec.get("read_paths", [])),
            skills=list(spec.get("skills", [])),
            notes=spec.get("notes", ""),
        )
    return AiCodingHarness(
        context=context,
        max_iterations=int(cfg.get("max_iterations", 5)),
    )


@module(
    name="ai_coding_harness",
    version="1.0.0",
    config_defaults={"max_iterations": 5},
)
class AiCodingHarnessModule(Module):
    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self.engine: Optional[AiCodingHarness] = None

    async def initialize(self) -> None:
        try:
            self.engine = create_ai_coding_harness(self.config)
            self.status = HealthStatus.HEALTHY
        except Exception:  # pragma: no cover - defensive
            self.status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        return HealthStatus.HEALTHY if self.engine is not None else HealthStatus.UNHEALTHY

    async def shutdown(self) -> None:
        self.status = HealthStatus.UNKNOWN

    # facade methods delegating to the engine
    def build_context(self) -> str:
        return self.engine.build_context()

    def scaffold(self, spec: ScaffoldSpec, root_dir: Any) -> List[Any]:
        from pathlib import Path
        return self.engine.scaffold(spec, Path(root_dir))

    def generate_from_prompt(self, prompt: str, kind: ArtifactKind) -> Artifact:
        return self.engine.iterate(self.engine.generate(self.engine.plan(prompt, kind)))


def create_ai_coding_harness_module(
    config: Optional[dict[str, Any]] = None,
) -> AiCodingHarnessModule:
    return AiCodingHarnessModule(config=config or {})


__all__ = [
    "AiCodingHarness",
    "AiCodingHarnessModule",
    "ContextSpec",
    "ScaffoldSpec",
    "Artifact",
    "GenerationPlan",
    "VerificationResult",
    "ArtifactKind",
    "PipelineStage",
    "default_context",
    "create_ai_coding_harness",
    "create_ai_coding_harness_module",
    "__version__",
]