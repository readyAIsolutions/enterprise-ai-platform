"""slash_workflow — Plan->Implement->Validate AI-coding workflow with reusable markdown slash-commands, a plan-document schema, isolated-context sub-agents, a deterministic task cycle, and CLAUDE.md-style cascading global rules. Grounded in ColeMedin's "The True Power of AI Coding - Build Your OWN Workflows" (https://www.youtube.com/watch?v=mHBk8Z7Exag)."""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from enterprise.platform_kernel import Event, HealthStatus, Module, module

from .slash_workflow import (  # noqa: F401
    GlobalRules,
    Phase,
    PhaseReport,
    PlanDocument,
    SlashCommand,
    SlashCommandRegistry,
    SubAgent,
    TaskItem,
    TaskManager,
    TaskStatus,
    WorkflowEngine,
    WorkflowValidator,
    allowed_transitions,
    build_plan,
    default_global_rules,
    default_slash_commands,
)

logger = logging.getLogger("eni.slash_workflow_module")
__version__ = "1.0.0"


def create_slash_workflow(
    config: Optional[Dict[str, Any]] = None,
) -> WorkflowEngine:
    """Facade: construct and return the core workflow engine."""
    cfg = config or {}
    rules = default_global_rules()
    extra_rules = cfg.get("global_rules")
    if isinstance(extra_rules, list):
        for rule in extra_rules:
            rules.add(rule)
    commands = SlashCommandRegistry()
    plan = None
    plan_spec = cfg.get("plan")
    if isinstance(plan_spec, dict):
        plan = PlanDocument(
            title=plan_spec.get("title", "Untitled"),
            goals=list(plan_spec.get("goals", [])),
            tasks=[TaskItem(title=t) for t in plan_spec.get("tasks", [])],
            files_to_edit=list(plan_spec.get("files_to_edit", [])),
            files_to_create=list(plan_spec.get("files_to_create", [])),
            patterns=list(plan_spec.get("patterns", [])),
            success_criteria=list(plan_spec.get("success_criteria", [])),
            references=list(plan_spec.get("references", [])),
        )
    return WorkflowEngine(plan=plan, validator=WorkflowValidator())


@module(
    name="slash_workflow",
    version="1.0.0",
    config_defaults={"max_rework": 3},
)
class SlashWorkflowModule(Module):
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        self.engine: Optional[WorkflowEngine] = None
        self._event_bus = None

    async def initialize(self) -> None:
        try:
            self.engine = create_slash_workflow(self.config)
            self._status = HealthStatus.HEALTHY
        except Exception:  # pragma: no cover - defensive
            self._status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        return self._status

    async def shutdown(self) -> None:
        self._status = HealthStatus.STOPPING

    def _publish(self, topic: str, payload: Dict[str, Any]) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(
                Event.create(topic=topic, source=self.name, payload=payload)
            )

    # facade methods delegating to the engine
    def render_command(self, name: str, **kwargs: str) -> str:
        return SlashCommandRegistry().render(name, **kwargs)

    def validate_plan(self, plan: PlanDocument) -> List[str]:
        return self.engine.validator.validate_plan(plan)

    def run_workflow(
        self,
        plan: PlanDocument,
        implement: Callable[[TaskItem], None] = lambda t: None,
        review: Callable[[TaskItem], bool] = lambda t: True,
    ) -> List[PhaseReport]:
        reports = self.engine.run(plan, implement=implement, review=review)
        self._publish(
            "slash_workflow.run",
            {
                "phase_count": len(reports),
                "all_ok": self.engine.all_ok,
                "status": self.status.value,
            },
        )
        return reports


def create_slash_workflow_module(
    config: Optional[Dict[str, Any]] = None,
) -> SlashWorkflowModule:
    return SlashWorkflowModule(config=config or {})


__all__ = [
    "GlobalRules",
    "Phase",
    "PhaseReport",
    "PlanDocument",
    "SlashCommand",
    "SlashCommandRegistry",
    "SlashWorkflowModule",
    "SubAgent",
    "TaskItem",
    "TaskManager",
    "TaskStatus",
    "WorkflowEngine",
    "WorkflowValidator",
    "allowed_transitions",
    "build_plan",
    "create_slash_workflow",
    "create_slash_workflow_module",
    "default_global_rules",
    "default_slash_commands",
    "__version__",
]
