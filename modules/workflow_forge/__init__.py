"""Workflow Forge — Composable AI-Coding Workflow System

Enterprise-grade module for building and executing reusable AI coding workflows,
grounded in the philosophy from Cole Medin's "The True Power of AI Coding -
Build Your OWN Workflows" (mHBk8Z7Exag).

Exports:
  WorkflowForgeModule   — @module-decorated Module subclass
  WorkflowForge         — Builder for composable workflows
  Workflow              — Ordered sequence of workflow phases
  WorkflowPhase         — Single phase (rules/plan/tasks/implement/validate)
  WorkflowPlan          — PRP-style structured plan
  WorkflowTask          — Discrete implementation task
  ValidationGate        — Validation check definition
  ValidationReport      — Validation execution result
  PhaseKind             — Enum: RULES, PLAN, TASKS, IMPLEMENT, VALIDATE
  TaskStatus            — Enum: PENDING, IN_PROGRESS, COMPLETED, FAILED, SKIPPED
  ValidationResult      — Enum: PASS, FAIL, WARNING
  run_workflow_async    — Async convenience function

Version: 1.0.0
Python: 3.10+
"""

from __future__ import annotations

__version__ = "1.0.0"
__module__ = "workflow_forge"

import asyncio
import logging
import threading
from typing import Any, Optional

from enterprise.platform_kernel import (
    EventBus,
    Event,
    EventPriority,
    HealthStatus,
    Module,
    module,
)

from .workflow_forge import (
    PhaseKind,
    TaskStatus,
    ValidationResult,
    WorkflowPhase,
    WorkflowTask,
    ValidationGate,
    ValidationReport,
    WorkflowPlan,
    Workflow,
    WorkflowForge,
    run_workflow_async,
)

__all__ = [
    "__version__",
    "WorkflowForgeModule",
    "WorkflowForge",
    "Workflow",
    "WorkflowPhase",
    "WorkflowPlan",
    "WorkflowTask",
    "ValidationGate",
    "ValidationReport",
    "PhaseKind",
    "TaskStatus",
    "ValidationResult",
    "run_workflow_async",
    "create_workflow_forge_module",
]

# ---------------------------------------------------------------------------
# Module logger
# ---------------------------------------------------------------------------
_logger: logging.Logger = logging.getLogger("enterprise.workflow_forge")


@module(name="workflow_forge", version="1.0.0")
class WorkflowForgeModule(Module):
    """Enterprise Workflow Forge Module.

    Wraps the WorkflowForge library, exposing composable workflow construction,
    PRP-style plan generation, task breakdown, and validation gates as a
    registered Platform Kernel module.

    Events published:
      - workflow.created
      - workflow.plan.generated
      - workflow.task.started
      - workflow.task.completed
      - workflow.task.failed
      - workflow.validation.completed
      - workflow.health.status
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._forge: WorkflowForge | None = None
        self._event_bus: EventBus | None = None
        self._lock: threading.RLock = threading.RLock()
        self._forge_config: dict[str, Any] = {}

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def forge(self) -> WorkflowForge | None:
        """Return the active WorkflowForge instance, if initialized."""
        with self._lock:
            return self._forge

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Initialize the Workflow Forge module.

        Creates the WorkflowForge instance and performs an initial health check.
        """
        with self._lock:
            self._status = HealthStatus.STARTING
            self._forge_config = {
                "auto_register_validators": self._config.get("auto_register_validators", True),
                "publish_events": self._config.get("publish_events", True),
                "default_workflow": self._config.get("default_workflow", "standard"),
            }

        try:
            _logger.info(
                "Workflow Forge module initializing (default_workflow=%s)",
                self._forge_config["default_workflow"],
            )

            # Instantiate the forge
            self._forge = WorkflowForge()

            # Optionally register default validators (already done at import)
            if self._forge_config["auto_register_validators"]:
                _logger.debug("Default validators already registered at import time")

            self._status = HealthStatus.HEALTHY
            _logger.info("Workflow Forge module initialized successfully")

            # Publish initialization event
            if self._event_bus is not None and self._forge_config["publish_events"]:
                self._event_bus.publish(
                    Event.create(
                        topic="workflow.module.initialized",
                        source="workflow_forge",
                        payload={"version": self.version, "config": self._forge_config},
                    )
                )

        except Exception as exc:
            _logger.exception("Failed to initialize Workflow Forge module: %s", exc)
            self._status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        """Perform a health check on the workflow forge.

        Returns:
            HealthStatus indicating operational status.
        """
        if self._forge is None:
            self._status = HealthStatus.UNKNOWN
            return self._status

        try:
            # Simple health check: verify we can create a workflow and generate a plan
            test_workflow = WorkflowForge.standard_ai_coding_workflow("health_check")
            test_plan = self._forge.generate_plan(
                "Health check test feature",
                context={"goals": ["Verify module operational"]},
            )

            # Verify basic functionality
            if len(test_workflow.phases) != 5:
                raise RuntimeError(f"Expected 5 phases, got {len(test_workflow.phases)}")
            if not test_plan.tasks:
                raise RuntimeError("Plan generation produced no tasks")

            self._status = HealthStatus.HEALTHY

            if self._event_bus is not None and self._forge_config["publish_events"]:
                self._event_bus.publish(
                    Event.create(
                        topic="workflow.health.status",
                        source="workflow_forge",
                        payload={"status": self._status.value},
                    )
                )

            return self._status

        except Exception as exc:
            _logger.exception("Health check failed: %s", exc)
            self._status = HealthStatus.UNHEALTHY

            if self._event_bus is not None and self._forge_config["publish_events"]:
                self._event_bus.publish(
                    Event.create(
                        topic="workflow.health.status",
                        source="workflow_forge",
                        payload={"status": self._status.value, "error": str(exc)},
                        priority=EventPriority.HIGH,
                    )
                )
            return self._status

    async def shutdown(self) -> None:
        """Gracefully shut down the workflow forge module."""
        with self._lock:
            self._status = HealthStatus.STOPPING

        _logger.info("Shutting down Workflow Forge module...")

        try:
            self._forge = None
            self._status = HealthStatus.HEALTHY
            _logger.info("Workflow Forge module shut down successfully")

        except Exception as exc:
            _logger.exception("Error during Workflow Forge shutdown: %s", exc)
            self._status = HealthStatus.UNHEALTHY
            raise

    # ── Event Bus Wiring ─────────────────────────────────────────────────

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Wire the platform EventBus into this module.

        Called by the Platform Kernel after module discovery but
        before initialize(). If an event bus is already active,
        it is replaced gracefully.

        Args:
            event_bus: The platform EventBus instance.
        """
        with self._lock:
            self._event_bus = event_bus


def create_workflow_forge_module(
    config: dict[str, Any] | None = None,
) -> WorkflowForgeModule:
    """Create a :class:`WorkflowForgeModule` from an optional config dict.

    The config may contain:
      - auto_register_validators (bool): Register default validators (default True)
      - publish_events (bool): Publish lifecycle events (default True)
      - default_workflow (str): Default workflow template (default "standard")

    Args:
        config: Optional module configuration dictionary.

    Returns:
        A fully constructed :class:`WorkflowForgeModule`.
    """
    cfg = dict(config or {})
    return WorkflowForgeModule(
        config={
            "auto_register_validators": cfg.get("auto_register_validators", True),
            "publish_events": cfg.get("publish_events", True),
            "default_workflow": cfg.get("default_workflow", "standard"),
        }
    )