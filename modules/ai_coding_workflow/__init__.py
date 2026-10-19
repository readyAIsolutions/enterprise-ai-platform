"""ai_coding_workflow — a framework-agnostic, 3-phase AI-coding workflow
engine for the ENI Enterprise Platform.

Grounded in ColeMedin's "The True Power of AI Coding - Build Your OWN
Workflows" (https://www.youtube.com/watch?v=mHBk8Z7Exag). The workflow runs
REQUIREMENTS -> PLAN -> EXECUTE -> VALIDATE -> COMPLETE: a codebase-analyst
research step builds a granular task plan, a per-task state machine cycles
each task TODO->DOING->REVIEW->DONE one at a time (to prevent hallucination),
and a validation gate generates tests + a human code-review step that can
reopen tasks. Works with PRP / BMAD / spec-kit / plain markdown.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import Event, HealthStatus, Module, module

from .core import (  # noqa: F401
    SUPPORTED_FRAMEWORKS,
    Plan,
    Task,
    TaskState,
    ValidationResult,
    WorkflowEngine,
    WorkflowError,
    WorkflowPhase,
)

logger = logging.getLogger("eni.ai_coding_workflow_module")
__version__ = "1.0.0"


def create_workflow_engine(
    name: str = "workflow",
    framework: str = "plain",
) -> WorkflowEngine:
    """Facade: construct and return a WorkflowEngine."""
    return WorkflowEngine(name=name, framework=framework)


@module(
    name="ai_coding_workflow",
    version="1.0.0",
    config_defaults={"default_framework": "plain"},
)
class AICodingWorkflowModule(Module):
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._event_bus = None
        self._workflows: Dict[str, WorkflowEngine] = {}

    async def initialize(self) -> None:
        try:
            framework = self.config.get("default_framework", "plain")
            if framework not in SUPPORTED_FRAMEWORKS:
                raise WorkflowError(f"Unknown default_framework {framework!r}")
            self._default_framework = framework
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

    # ── facade methods ──────────────────────────────────────────────────────
    def create_workflow(
        self, name: str, framework: Optional[str] = None
    ) -> WorkflowEngine:
        fw = framework or self.config.get("default_framework", "plain")
        engine = create_workflow_engine(name=name, framework=fw)
        self._workflows[name] = engine
        self._publish(
            "ai_coding_workflow.workflow_created",
            {"name": name, "framework": fw},
        )
        return engine

    def get_workflow(self, name: str) -> Optional[WorkflowEngine]:
        return self._workflows.get(name)

    def set_requirements(self, name: str, text: str) -> None:
        engine = self._require(name)
        engine.set_requirements(text)
        self._publish(
            "ai_coding_workflow.requirements_set",
            {"name": name, "phase": engine.phase.value},
        )

    def create_plan(
        self,
        name: str,
        tasks: List[Dict[str, Any]],
        success_criteria: List[str],
        research_notes: Optional[List[str]] = None,
    ) -> Plan:
        engine = self._require(name)
        plan = engine.create_plan(tasks, success_criteria, research_notes)
        self._publish(
            "ai_coding_workflow.plan_created",
            {"name": name, "task_count": len(plan.tasks)},
        )
        return plan

    def start_task(self, name: str, task_id: Optional[str] = None) -> Task:
        engine = self._require(name)
        task = engine.start_task(task_id)
        self._publish(
            "ai_coding_workflow.task_started",
            {"name": name, "task_id": task.id, "state": task.state.value},
        )
        return task

    def advance_task(self, name: str, task_id: str) -> Task:
        engine = self._require(name)
        task = engine.advance_task(task_id)
        self._publish(
            "ai_coding_workflow.task_advanced",
            {"name": name, "task_id": task.id, "state": task.state.value},
        )
        return task

    def validate(
        self,
        name: str,
        generated_tests: Optional[List[str]] = None,
        review_findings: Optional[List[str]] = None,
    ) -> ValidationResult:
        engine = self._require(name)
        result = engine.validate(generated_tests, review_findings)
        self._publish(
            "ai_coding_workflow.validated",
            {"name": name, "passed": result.passed},
        )
        return result

    def progress(self, name: str) -> Dict[str, int]:
        return self._require(name).progress()

    def summary(self, name: str) -> Dict[str, Any]:
        return self._require(name).summary()

    def render(self, name: str) -> str:
        return self._require(name).render()

    def _require(self, name: str) -> WorkflowEngine:
        engine = self._workflows.get(name)
        if engine is None:
            raise WorkflowError(f"No workflow named {name!r}")
        return engine


def create_ai_coding_workflow_module(
    config: Optional[Dict[str, Any]] = None,
) -> AICodingWorkflowModule:
    return AICodingWorkflowModule(config=config or {})


__all__ = [
    "SUPPORTED_FRAMEWORKS",
    "AICodingWorkflowModule",
    "Plan",
    "Task",
    "TaskState",
    "ValidationResult",
    "WorkflowEngine",
    "WorkflowError",
    "WorkflowPhase",
    "create_ai_coding_workflow_module",
    "create_workflow_engine",
    "__version__",
]
