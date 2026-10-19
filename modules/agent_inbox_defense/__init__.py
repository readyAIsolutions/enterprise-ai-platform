"""agent_inbox_defense — enterprise module wrapping a defensive scanner for
untrusted inbound content handed to an AI agent.

Grounded in the matthew_berman transcript *"I was hacked..."*
(https://www.youtube.com/watch?v=_E4ZT1h7MZs). See
:mod:`enterprise.modules.agent_inbox_defense.agent_inbox_defense` for the full
mapping of the five attacks (token-aid flood, siege/quota-drain, jailbreak,
format-override prompt injection, system-command spoof, memory-exfil probe) to
the detectors and controls (quarantine, token budget, allow-list, human review,
frontier-model scanner) implemented here.

The deterministic, network-free core lives in the sibling logic module; this
package registers it as a Platform Kernel module with an
initialize / health_check / shutdown lifecycle and a thin facade.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from enterprise.platform_kernel import Event, HealthStatus, Module, module

from .agent_inbox_defense import (
    AllowList,
    InboxDefenseEngine,
    ModelStrength,
    ScanResult,
    ScanVerdict,
    Signal,
    ThreatType,
    TokenBudget,
    estimate_tokens,
)

logger = logging.getLogger("eni.agent_inbox_defense_module")

__version__ = "1.0.0"
__all__ = [
    "AgentInboxDefenseModule",
    "create_agent_inbox_defense_module",
    "InboxDefenseEngine",
    "TokenBudget",
    "AllowList",
    "ScanResult",
    "Signal",
    "ThreatType",
    "ScanVerdict",
    "ModelStrength",
    "estimate_tokens",
]


@module(
    name="agent_inbox_defense",
    version=__version__,
    config_defaults={
        "scanner_model": "standard",       # instant | standard | frontier (rule #2)
        "require_review": True,            # human-in-the-loop (rule #1)
        "review_threshold": 0.35,
        "quarantine_threshold": 0.6,
        "token_flood_chars": 40000,        # token-aid flood threshold
        "per_message_token_max": 50000,
        "total_token_budget": 500000,      # siege / wallet-drain cap
        "siege_window_sec": 60.0,
        "siege_burst_max": 5,
    },
)
class AgentInboxDefenseModule(Module):
    """Kernel module exposing the inbound-content defence engine."""

    def __init__(self, config: Optional[dict] = None) -> None:
        super().__init__(config)
        self._engine: Optional[InboxDefenseEngine] = None
        self._event_bus = None

    async def initialize(self) -> None:
        self._status = HealthStatus.STARTING
        try:
            cfg = self._config or {}
            model = ModelStrength(str(cfg.get("scanner_model", "standard")).lower())
            budget = TokenBudget(
                per_message_max=int(cfg.get("per_message_token_max", 50000)),
                total_max=int(cfg.get("total_token_budget", 500000)),
            )
            allow = AllowList(list(cfg.get("allow_list", []) or []))
            self._engine = InboxDefenseEngine(
                budget=budget,
                allow_list=allow,
                scanner_model=model,
                require_review=bool(cfg.get("require_review", True)),
                review_threshold=float(cfg.get("review_threshold", 0.35)),
                quarantine_threshold=float(cfg.get("quarantine_threshold", 0.6)),
                token_flood_chars=int(cfg.get("token_flood_chars", 40000)),
                siege_window_sec=float(cfg.get("siege_window_sec", 60.0)),
                siege_burst_max=int(cfg.get("siege_burst_max", 5)),
            )
            self._status = HealthStatus.HEALTHY
        except Exception as exc:  # pragma: no cover - defensive
            self._status = HealthStatus.UNHEALTHY
            raise exc

    async def health_check(self) -> HealthStatus:
        if self._engine is None:
            self._status = HealthStatus.UNKNOWN
        return self._status

    async def shutdown(self) -> None:
        self._status = HealthStatus.STOPPING
        self._engine = None

    # -- facade -------------------------------------------------------------
    def scan(self, content: str, sender: Optional[str] = None) -> ScanResult:
        """Scan one inbound item; publish an event when a threat is caught."""
        result = self._require_engine().scan(content, sender=sender)
        if result.quarantined:
            self._publish(
                "inbox_defense.quarantined",
                {
                    "sender": sender,
                    "verdict": result.verdict.value,
                    "risk": round(result.risk, 4),
                    "threats": [t.value for t in result.threats],
                },
            )
        elif result.verdict == ScanVerdict.REVIEW:
            self._publish(
                "inbox_defense.review_required",
                {"sender": sender, "risk": round(result.risk, 4)},
            )
        return result

    def allow_sender(self, sender: str) -> None:
        self._require_engine().allow_list.add(sender)

    def block_sender(self, sender: str) -> None:
        self._require_engine().allow_list.remove(sender)

    def stats(self) -> dict[str, Any]:
        return self._require_engine().stats()

    def audit_log(self) -> list:
        return self._require_engine().audit_log()

    def reset(self) -> None:
        self._require_engine().reset()

    @property
    def engine(self) -> Optional[InboxDefenseEngine]:
        return self._engine

    # -- helpers ------------------------------------------------------------
    def _require_engine(self) -> InboxDefenseEngine:
        if self._engine is None:
            raise RuntimeError("agent_inbox_defense module not initialized")
        return self._engine

    def _publish(self, topic: str, payload: dict) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(
                Event.create(topic=topic, source=self.name, payload=payload)
            )

    def set_event_bus(self, event_bus) -> None:
        """Store the kernel EventBus for cross-module publishing."""
        self._event_bus = event_bus


def create_agent_inbox_defense_module(
    config: Optional[dict] = None,
) -> AgentInboxDefenseModule:
    """Factory used for kernel discovery / direct instantiation."""
    return AgentInboxDefenseModule(config=config)
