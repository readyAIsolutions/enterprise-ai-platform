"""custom_agent_workflows — build your OWN AI coding workflows as a module.

Grounded in the Cole Medin transcript *"The True Power of AI Coding — Build
Your OWN Workflows (Full Guide)"* (https://www.youtube.com/watch?v=mHBk8Z7Exag):
creating AI coding systems is far more than prompts — it is about building
reusable workflows (plan -> implement -> validate) composed of global rules,
slash commands, and subagents that can evolve to fit your needs.

The deterministic core lives in
:mod:`enterprise.modules.custom_agent_workflows.custom_agent_workflows`
(``CodingWorkflow``, ``TaskManager``, ``WorkflowPlan``, ``Task``, ``SubAgent``,
``build_initial_md``, ``build_plan``, ``validate_plan``, ``validate_code``,
``research_codebase`` and the slash-command builders). This package registers
it as a Platform Kernel module with an initialize / health_check / shutdown
lifecycle and a thin facade.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from enterprise.platform_kernel import Event, HealthStatus, Module, module

from .custom_agent_workflows import (
    AGENT_CODEBASE_ANALYST,
    AGENT_VALIDATOR,
    CODEBASE_ANALYST,
    PHASE_IMPLEMENTATION,
    PHASE_PLANNING,
    PHASE_VALIDATION,
    SLASH_CREATE_PLAN,
    SLASH_EXECUTE_PLAN,
    SLASH_PRIMER,
    TASK_DONE,
    TASK_DOING,
    TASK_REVIEW,
    TASK_TODO,
    VALIDATOR,
    CodingWorkflow,
    SlashCommand,
    SubAgent,
    Task,
    TaskManager,
    WorkflowPlan,
    build_initial_md,
    build_plan,
    create_plan_slash_command,
    execute_plan_slash_command,
    primer_slash_command,
    research_codebase,
    validate_code,
    validate_plan,
)

logger = logging.getLogger("eni.custom_agent_workflows_module")

__version__ = "1.0.0"

__all__ = [
    "AGENT_CODEBASE_ANALYST",
    "AGENT_VALIDATOR",
    "CODEBASE_ANALYST",
    "CustomAgentWorkflowsModule",
    "PHASE_IMPLEMENTATION",
    "PHASE_PLANNING",
    "PHASE_VALIDATION",
    "SLASH_CREATE_PLAN",
    "SLASH_EXECUTE_PLAN",
    "SLASH_PRIMER",
    "TASK_DONE",
    "TASK_DOING",
    "TASK_REVIEW",
    "TASK_TODO",
    "VALIDATOR",
    "CodingWorkflow",
    "SlashCommand",
    "SubAgent",
    "Task",
    "TaskManager",
    "WorkflowPlan",
    "build_initial_md",
    "build_plan",
    "create_custom_agent_workflows_module",
    "create_plan_slash_command",
    "execute_plan_slash_command",
    "primer_slash_command",
    "research_codebase",
    "validate_code",
    "validate_plan",
]


@module(
    name="custom_agent_workflows",
    version=__version__,
    config_defaults={
        "max_tasks": 12,  # safety cap on granular tasks in a single plan
        "phase": PHASE_PLANNING,  # starting phase of the workflow
    },
)
class CustomAgentWorkflowsModule(Module):
    """Kernel module exposing custom AI coding workflow authoring."""

    def __init__(self, config: Optional[dict] = None) -> None:
        super().__init__(config)
        self._workflow: Optional[CodingWorkflow] = None
        self._max_tasks: int = 12

    async def initialize(self) -> None:
        self._status = HealthStatus.STARTING
        try:
            cfg = self._config or {}
            self._max_tasks = max(1, int(cfg.get("max_tasks", 12)))
            self._workflow = CodingWorkflow(name=self.name)
            self._status = HealthStatus.HEALTHY
        except Exception as exc:  # pragma: no cover - defensive
            self._status = HealthStatus.UNHEALTHY
            raise exc

    async def health_check(self) -> HealthStatus:
        return self._status

    async def shutdown(self) -> None:
        self._status = HealthStatus.STOPPING
        self._workflow = None

    # -- facade ------------------------------------------------------------
    def plan(self, feature: str, references=None, integration_points=None,
             is_new_project: bool = True) -> dict:
        wf = self._require_workflow()
        plan = wf.plan(feature, references, integration_points, is_new_project)
        self._publish("custom_agent_workflows.plan_created",
                      {"title": plan.title, "tasks": len(plan.tasks)})
        return self._plan_to_dict(plan)

    def build_initial_md(self, feature: str, references=None,
                         integration_points=None, is_new_project: bool = True) -> str:
        md = build_initial_md(feature, references, integration_points, is_new_project)
        self._publish("custom_agent_workflows.initial_md",
                      {"feature": feature, "chars": len(md)})
        return md

    def execute(self, plan_dict: dict) -> bool:
        wf = self._require_workflow()
        plan = self._plan_from_dict(plan_dict)
        manager = TaskManager(plan.tasks)
        self._workflow._task_manager = manager
        done = wf.execute()
        self._publish("custom_agent_workflows.executed", {"completed": done})
        return done

    def validate_plan(self, plan_dict: dict) -> dict:
        plan = self._plan_from_dict(plan_dict)
        return validate_plan(plan)

    def primer(self, project_root=None, key_files=None) -> dict:
        result = primer_slash_command(project_root, key_files)
        self._publish("custom_agent_workflows.primer",
                      {"files": result["files_to_read"]})
        return result

    def research_codebase(self, codebase_path: str) -> dict:
        result = research_codebase(codebase_path)
        self._publish("custom_agent_workflows.research",
                      {"file_count": result["file_count"]})
        return result

    def validate_code(self, code_path: str) -> dict:
        return validate_code(code_path)

    def stats(self) -> dict:
        return {
            "max_tasks": self._max_tasks,
            "status": self._status.value,
            "workflow_initialized": self._workflow is not None,
        }

    # -- helpers -----------------------------------------------------------
    def _require_workflow(self) -> CodingWorkflow:
        if self._workflow is None:
            raise RuntimeError("custom_agent_workflows module not initialized")
        return self._workflow

    def _plan_to_dict(self, plan: WorkflowPlan) -> dict:
        return {
            "title": plan.title,
            "summary": plan.summary,
            "tasks": [
                {"id": t.id, "description": t.description, "files": list(t.files),
                 "status": t.status}
                for t in plan.tasks
            ],
            "success_criteria": list(plan.success_criteria),
            "desired_structure": list(plan.desired_structure),
            "references": list(plan.references),
        }

    def _plan_from_dict(self, data: dict) -> WorkflowPlan:
        tasks = [
            Task(id=t["id"], description=t["description"],
                 files=list(t.get("files", [])), status=t.get("status", TASK_TODO))
            for t in data.get("tasks", [])
        ]
        return WorkflowPlan(
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            tasks=tasks,
            success_criteria=list(data.get("success_criteria", [])),
            desired_structure=list(data.get("desired_structure", [])),
            references=list(data.get("references", [])),
        )

    def _publish(self, topic: str, payload: dict) -> None:
        if getattr(self, "_event_bus", None) is not None:
            self._event_bus.publish(Event.create(topic=topic, source=self.name,
                                                 payload=payload))

    def set_event_bus(self, event_bus) -> None:
        """Store the kernel EventBus for cross-module publishing."""
        self._event_bus = event_bus


def create_custom_agent_workflows_module(config: Optional[dict] = None) -> CustomAgentWorkflowsModule:
    """Factory used for kernel discovery / direct instantiation."""
    return CustomAgentWorkflowsModule(config=config)
