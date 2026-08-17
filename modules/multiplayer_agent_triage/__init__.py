"""multiplayer_agent_triage — a Platform Kernel module for triaging problems and
wins when many AI agents / players operate together in one shared product.

Grounded in the JEVanClief transcript *"Alpha Launch 24 Hours in: AI multiplayer
Problems and Wins!"* (https://www.youtube.com/watch?v=e3RgzvuYTBY), which is a
24-hour post-mortem of a multiplayer AI platform: many users and coding agents
sharing workspaces. The transcript catalogues concrete failures (oversized
per-request reads, deployment / Azure blob file-naming problems leaving agents
stuck in thinking mode, workspace files not surfacing, sandbox read failures
that needed a fallback, token/cost monitoring) and wins (extremely efficient
shared token usage, a community knowledge-corpus upload, a "choose your own
adventure" template with memories/states, workflow/explainer automation, and
organizations enabling people to work together).

The deterministic, stdlib-only logic lives in
:mod:`enterprise.modules.multiplayer_agent_triage.multiplayer_agent_triage`
(``MultiplayerTriageEngine``, ``classify_problem``, ``classify_win``,
``analyze_token_spend``, ``summarize_incidents``). This package registers it as
a module with an initialize / health_check / shutdown lifecycle, a thin facade,
and EventBus publishing for triaged problems and wins.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from enterprise.platform_kernel import Event, HealthStatus, Module, module

from .multiplayer_agent_triage import (
    MultiplayerTriageEngine,
    TriageResult,
    WinRecord,
    analyze_token_spend,
    classify_problem,
    classify_win,
    summarize_incidents,
)

logger = logging.getLogger("eni.multiplayer_agent_triage_module")

__version__ = "1.0.0"
__all__ = [
    "MultiplayerAgentTriageModule",
    "create_multiplayer_agent_triage_module",
    "MultiplayerTriageEngine",
    "TriageResult",
    "WinRecord",
    "analyze_token_spend",
    "classify_problem",
    "classify_win",
    "summarize_incidents",
]


@module(
    name="multiplayer_agent_triage",
    version=__version__,
    config_defaults={
        "max_problems_to_keep": 1000,  # ring-buffer cap for in-memory records
        "publish_events": True,  # emit EventBus events when triaging
    },
)
class MultiplayerAgentTriageModule(Module):
    """Kernel module exposing a multiplayer-agent problem/wins triage engine."""

    def __init__(self, config: Optional[dict] = None) -> None:
        super().__init__(config)
        self._engine: Optional[MultiplayerTriageEngine] = None

    async def initialize(self) -> None:
        self._status = HealthStatus.STARTING
        try:
            cfg = self._config or {}
            self._engine = MultiplayerTriageEngine(config=cfg)
            self._status = HealthStatus.HEALTHY
        except Exception as exc:  # pragma: no cover - defensive
            self._status = HealthStatus.UNHEALTHY
            raise exc

    async def health_check(self) -> HealthStatus:
        return self._status

    async def shutdown(self) -> None:
        self._status = HealthStatus.STOPPING
        self._engine = None

    # -- facade -------------------------------------------------------------
    def triage(self, observation: dict) -> TriageResult:
        """Classify a problem observation and record it."""
        result = self._require_engine().triage(observation)
        self._publish(
            "multiplayer_agent_triage.problem",
            {
                "problem_type": result.problem_type,
                "severity": result.severity,
                "confidence": result.confidence,
                "is_critical": result.is_critical,
            },
        )
        return result

    def record_win(self, observation: dict):
        """Classify a win observation and record it."""
        record = self._require_engine().record_win(observation)
        if record is not None:
            self._publish(
                "multiplayer_agent_triage.win",
                {"win_type": record.win_type, "title": record.title},
            )
        return record

    def critical_items(self):
        """Problems that must be fixed before scaling access."""
        return self._require_engine().critical_items()

    def summary(self) -> dict:
        """Aggregate incident summary (counts, severities, critical list)."""
        return self._require_engine().summary()

    def token_spend(self, calls) -> dict:
        """Analyze a batch of API-call records for token/cost usage."""
        return self._require_engine().token_spend(calls)

    @property
    def engine(self) -> MultiplayerTriageEngine:
        """Direct access to the underlying triage engine."""
        return self._require_engine()

    # -- helpers ------------------------------------------------------------
    def _require_engine(self) -> MultiplayerTriageEngine:
        if self._engine is None:
            raise RuntimeError("multiplayer_agent_triage module not initialized")
        return self._engine

    def _publish(self, topic: str, payload: dict) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(
                Event.create(topic=topic, source=self.name, payload=payload)
            )

    def set_event_bus(self, event_bus) -> None:
        """Store the kernel EventBus for cross-module publishing."""
        self._event_bus = event_bus


def create_multiplayer_agent_triage_module(
    config: Optional[dict] = None,
) -> MultiplayerAgentTriageModule:
    """Factory used for kernel discovery / direct instantiation."""
    return MultiplayerAgentTriageModule(config=config)
