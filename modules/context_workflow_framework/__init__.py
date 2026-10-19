"""context_workflow_framework — build-your-own context-engineering workflow
framework for the ENI Enterprise Platform.

Grounded ENTIRELY in ColeMedin's "The True Power of AI Coding - Build Your
OWN Workflows (Full Guide)" (https://www.youtube.com/watch?v=mHBk8Z7Exag).
AI coding is about building REUSABLE WORKFLOWS/SYSTEMS, not one-off prompts.
Existing frameworks (PRP = Product Requirement Prompt, BMAD, GitHub spec-kit)
share one philosophy: scope the task, gather and assemble context (docs,
examples, rules), plan, implement, validate. Understand that structure and
COMPOSE YOUR OWN. This module exposes WorkflowPhase / WorkflowFramework /
ContextAssembler plus named built-in templates (prp/bmad/spec_kit).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import Event, EventBus, HealthStatus, Module, module

from .core import (  # noqa: F401
    ContextAssembler,
    WorkflowError,
    WorkflowFramework,
    WorkflowPhase,
)

__version__ = "1.0.0"
logger = logging.getLogger("eni.context_workflow_framework_module")


@module(name="context_workflow_framework", version="1.0.0")
class ContextWorkflowFrameworkModule(Module):
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._event_bus: Optional[EventBus] = None
        self._framework: Optional[WorkflowFramework] = None

    async def initialize(self) -> None:
        self._status = HealthStatus.STARTING
        try:
            self._framework = WorkflowFramework()
            self._status = HealthStatus.HEALTHY
        except Exception:
            self._status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        return self._status

    async def shutdown(self) -> None:
        self._status = HealthStatus.STOPPING
        self._framework = None
        self._status = HealthStatus.UNKNOWN

    def set_event_bus(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    def _publish(self, topic: str, payload: Dict[str, Any]) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(
                Event.create(topic=topic, source=self.name, payload=payload)
            )

    # ── facade ────────────────────────────────────────────────────────────
    def _require(self) -> WorkflowFramework:
        if self._framework is None:
            raise WorkflowError("module not initialized")
        return self._framework

    def phase_names(self) -> List[str]:
        return self._require().phase_names()

    def render(self) -> str:
        return self._require().render()

    def validate_context(
        self, provided: Dict[str, Any]
    ) -> Dict[str, List[str]]:
        return self._require().validate_context(provided)

    def load_template(self, name: str) -> WorkflowFramework:
        framework = WorkflowFramework.load_template(name)
        self._publish(
            "context_workflow_framework.template_loaded",
            {"name": name, "phases": framework.phase_names()},
        )
        return framework


def create_context_workflow_framework_module(
    config: Optional[Dict[str, Any]] = None,
) -> ContextWorkflowFrameworkModule:
    return ContextWorkflowFrameworkModule(config=config or {})


__all__ = [
    "ContextAssembler",
    "ContextWorkflowFrameworkModule",
    "WorkflowError",
    "WorkflowFramework",
    "WorkflowPhase",
    "create_context_workflow_framework_module",
    "__version__",
]
