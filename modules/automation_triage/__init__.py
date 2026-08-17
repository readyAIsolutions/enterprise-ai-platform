"""Automation Triage module — a decision framework for WHAT to automate.

Implements the task-triage ladder, wrong-layer detection, "what not to automate"
guard, and one-client scoping guard extracted from four pulled JE Van Clief
transcripts:

  * "The Ladder That Explains Every AI Failure (And How to Avoid Them)"
  * "You're Automating The Wrong Layer (How 30,000 People Build AI Without Frameworks)"
  * "The Real Skill in AI: Knowing What Not to Automate"
  * "Stop Building Production-Ready AI. Solve for One Client First"

Export surface:
  * triage_task / AutomationLayer / TriageAction / TriageDecision — the ladder.
  * detect_wrong_layer / WrongLayerReport — wrong-layer flagging.
  * what_not_to_automate / NotAutoDecision — the judgment-preservation guard.
  * scope_for_one_client / ScopeVerdict — the one-client-first scoping guard.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import HealthStatus, Module, module

from .triage import (  # noqa: F401
    AutomationLayer, NotAutoDecision, PRODUCTION_KEYWORDS, ScopeVerdict,
    TriageAction, TriageDecision, WrongLayerReport, JUDGMENT_KEYWORDS,
    detect_wrong_layer, scope_for_one_client, triage_task, what_not_to_automate,
)

logger = logging.getLogger("eni.automation_triage")
__version__ = "1.0.0"


@module(
    name="automation_triage",
    version="1.0.0",
    config_defaults={
        "default_volume": 5,
        "judgment_threshold": 2,
    },
)
class AutomationTriageModule(Module):
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        self.default_volume: int = int(self.config.get("default_volume", 5))
        self.judgment_threshold: int = int(self.config.get("judgment_threshold", 2))
        self._ready: bool = False

    async def initialize(self) -> None:
        self._ready = True
        self.status = HealthStatus.HEALTHY

    async def health_check(self) -> HealthStatus:
        return HealthStatus.HEALTHY if self._ready else HealthStatus.UNHEALTHY

    async def shutdown(self) -> None:
        self._ready = False
        self.status = HealthStatus.UNKNOWN

    # ---- facade methods (thin wrappers over the pure core) ----

    def triage(self, task: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return triage_task(task, context or {}).to_dict()

    def detect_wrong_layer(self, task: str, attempted_layer: Any,
                           context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return detect_wrong_layer(task, attempted_layer, context or {}).to_dict()

    def what_not_to_automate(self, task: str,
                             context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return what_not_to_automate(task, context or {}).to_dict()

    def scope_for_one_client(self, proposal_reqs: Any,
                             context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return scope_for_one_client(proposal_reqs, context or {}).to_dict()


def create_automation_triage_module(config: Optional[Dict[str, Any]] = None) -> AutomationTriageModule:
    return AutomationTriageModule(config=config or {})


__all__ = [
    "AutomationTriageModule", "create_automation_triage_module",
    "AutomationLayer", "TriageAction", "TriageDecision", "WrongLayerReport",
    "ScopeVerdict", "NotAutoDecision", "triage_task", "detect_wrong_layer",
    "what_not_to_automate", "scope_for_one_client",
    "JUDGMENT_KEYWORDS", "PRODUCTION_KEYWORDS", "__version__",
]
