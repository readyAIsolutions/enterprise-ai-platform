"""composable_workflow_engine — a compose-your-own context-engineering
workflow engine for the ENI Enterprise Platform.

Grounded ENTIRELY in ColeMedin's "The True Power of AI Coding - Build Your OWN
Workflows (Full Guide)" (https://www.youtube.com/watch?v=mHBk8Z7Exag). AI
coding is about building SYSTEMS/WORKFLOWS, not one-off prompts. Rather than
adopt an existing framework wholesale (PRP, BMAD, GitHub spec-kit), understand
the fundamental PHASES — planning -> implementation -> validation, with context
engineering (RAG, memory, task management, prompt engineering) — and COMPOSE
YOUR OWN. This module provides WorkflowPhase / WorkflowTemplate data structures,
built-in templates mirroring the named frameworks, custom composition, pure
deterministic execution producing a per-phase log, validation, and JSON-safe
serialization.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import Event, HealthStatus, Module, module

from .core import (  # noqa: F401
    BUILDING_BLOCKS,
    CONTEXT_COMPONENTS,
    KNOWN_FRAMEWORKS,
    ValidationResult,
    WorkflowEngine,
    WorkflowError,
    WorkflowPhase,
    WorkflowTemplate,
)

logger = logging.getLogger("eni.composable_workflow_engine_module")
__version__ = "1.0.0"


@module(
    name="composable_workflow_engine",
    version="1.0.0",
    config_defaults={"default_template": "three-step"},
)
class ComposableWorkflowEngineModule(Module):
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._event_bus: Any = None
        self._engine: Optional[WorkflowEngine] = None

    async def initialize(self) -> None:
        self._status = HealthStatus.STARTING
        try:
            self._engine = WorkflowEngine()
            default = self.config.get("default_template", "three-step")
            if not self._engine.has_template(default):
                raise WorkflowError(
                    f"Unknown default_template {default!r}"
                )
            self._default_template = default
            self._status = HealthStatus.HEALTHY
        except Exception:
            self._status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        return self._status

    async def shutdown(self) -> None:
        self._status = HealthStatus.STOPPING

    def set_event_bus(self, event_bus: Any) -> None:
        """Attach the platform event bus; events only emitted when present."""
        self._event_bus = event_bus

    def _publish(self, topic: str, payload: Dict[str, Any]) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(
                Event.create(topic=topic, source=self.name, payload=payload)
            )

    def _require_engine(self) -> WorkflowEngine:
        if self._engine is None:
            raise WorkflowError("module not initialized")
        return self._engine

    # ── facade methods ───────────────────────────────────────────────────────
    def all_templates(self) -> List[str]:
        return self._require_engine().all_templates()

    def get_template(self, name: str) -> WorkflowTemplate:
        return self._require_engine().get_template(name)

    def register_template(
        self, template: WorkflowTemplate, overwrite: bool = False
    ) -> None:
        self._require_engine().register_template(template, overwrite=overwrite)
        self._publish(
            "composable_workflow_engine.template_registered",
            {"name": template.name, "framework": template.framework},
        )

    def compose(
        self,
        name: str,
        phases: List[WorkflowPhase],
        framework: str = "custom",
        description: str = "",
        register: bool = True,
        overwrite: bool = False,
    ) -> WorkflowTemplate:
        template = self._require_engine().compose(
            name=name,
            phases=phases,
            framework=framework,
            description=description,
            register=register,
            overwrite=overwrite,
        )
        self._publish(
            "composable_workflow_engine.template_composed",
            {"name": name, "phase_count": len(template.phases)},
        )
        return template

    def validate_template(
        self, template: WorkflowTemplate
    ) -> ValidationResult:
        return self._require_engine().validate_template(template)

    def run(
        self,
        template_name: str,
        context: Optional[Dict[str, Any]] = None,
        strict: bool = True,
    ) -> Dict[str, Any]:
        result = self._require_engine().run(
            template_name, context=context, strict=strict
        )
        self._publish(
            "composable_workflow_engine.workflow_run",
            {
                "template": result["template"],
                "phase_count": result["phase_count"],
            },
        )
        return result

    def describe(self, template_name: str) -> Dict[str, Any]:
        return self._require_engine().describe(template_name)


def create_composable_workflow_engine_module(
    config: Optional[Dict[str, Any]] = None,
) -> ComposableWorkflowEngineModule:
    return ComposableWorkflowEngineModule(config=config or {})


__all__ = [
    "BUILDING_BLOCKS",
    "CONTEXT_COMPONENTS",
    "KNOWN_FRAMEWORKS",
    "ComposableWorkflowEngineModule",
    "ValidationResult",
    "WorkflowEngine",
    "WorkflowError",
    "WorkflowPhase",
    "WorkflowTemplate",
    "create_composable_workflow_engine_module",
    "__version__",
]
