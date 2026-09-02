"""agentic_workflow_builder — compose agentic workflows (Claude Code + Cursor).

Grounded in the JEVanClief transcript *"Claude Code + Cursor: Making Agentic
workflows with an Agentic workflow!"*
(https://www.youtube.com/watch?v=v2UnNFmkia0). The speaker builds a multi-agent
pipeline by running Claude Code (CLI or Cursor plugin) inside WSL/PowerShell,
authoring ``.md`` system-prompt files, composing sections of parser/auditor/
framework-loader agents, modelling parsed compliance statements with a
Pydantic-style schema (``ParsedStatement``), generating agent to-do lists before
editing, refactoring a monolithic ``massive.py`` into modules that initiate from
each other, and estimating cost from token usage.

The deterministic, stdlib-only core lives in
:mod:`enterprise.modules.agentic_workflow_builder.agentic_workflow_builder`
(``AgentSpec``, ``Workflow``, ``ParsedStatement``, ``build_workflow``,
``create_todo_list``, ``decompose_module``, ``estimate_cost``,
``statement_matches``, ``workflow_stats``); this package registers it as an
enterprise module with an initialize / health_check / shutdown lifecycle and a
thin facade.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, List, Optional

from enterprise.platform_kernel import Event, HealthStatus, Module, module

from .agentic_workflow_builder import (
    AgentSpec,
    ParsedStatement,
    Workflow,
    build_workflow,
    create_todo_list,
    decompose_module,
    estimate_cost,
    statement_matches,
    workflow_stats,
)

logger = logging.getLogger("eni.agentic_workflow_builder_module")

__version__ = "1.0.0"
__all__ = [
    "AgentSpec",
    "AgenticWorkflowBuilderModule",
    "ParsedStatement",
    "Workflow",
    "build_workflow",
    "create_agentic_workflow_builder_module",
    "create_todo_list",
    "decompose_module",
    "estimate_cost",
    "statement_matches",
    "workflow_stats",
]


@module(
    name="agentic_workflow_builder",
    version=__version__,
    config_defaults={
        # Default runtime environment for the composed workflow (CLI target).
        "environment": "wsl",
        # Tools the agents may use (Claude Code CLI and/or the Cursor plugin).
        "tools": ["claude_code", "cursor"],
        # Default billing plan used by cost estimation ("api", "pro", "max").
        "plan": "api",
        # Default hourly API rate in USD (tokens in + tokens out).
        "hourly_rate": 5.0,
    },
)
class AgenticWorkflowBuilderModule(Module):
    """Kernel module exposing agentic-workflow composition logic."""

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self._event_bus = None
        self._workflows: list[Workflow] = []

    async def initialize(self) -> None:
        self._status = HealthStatus.STARTING
        try:
            cfg = self._config or {}
            env = str(cfg.get("environment", "terminal")).lower()
            # Normalize aliases: cli/cli → terminal; wsl stays wsl; powershell stays.
            _env_aliases = {"cli": "terminal", "terminal": "terminal",
                            "wsl": "wsl", "powershell": "powershell"}
            env = _env_aliases.get(env, env)
            if env not in _env_aliases.values():
                raise ValueError(
                    f"unsupported environment {env!r}; expected wsl/powershell/terminal"
                )
            tools = cfg.get("tools", ["claude_code", "cursor"])
            _tool_aliases = {"claude": "claude_code", "claude_code": "claude_code",
                             "cursor": "cursor"}
            normalized_tools = []
            for tool in tools:
                t = _tool_aliases.get(str(tool).lower(), str(tool).lower())
                if t not in ("claude_code", "cursor"):
                    raise ValueError(f"unsupported tool {tool!r}")
                normalized_tools.append(t)
            cfg["environment"] = env
            cfg["tools"] = normalized_tools
            self._status = HealthStatus.HEALTHY
        except Exception as exc:  # pragma: no cover - defensive
            self._status = HealthStatus.UNHEALTHY
            raise exc

    async def health_check(self) -> HealthStatus:
        return self._status

    async def shutdown(self) -> None:
        self._status = HealthStatus.STOPPING
        self._workflows.clear()

    def set_event_bus(self, event_bus) -> None:
        """Store the kernel EventBus for cross-module publishing."""
        self._event_bus = event_bus

    # -- facade -------------------------------------------------------------
    def create_agent(
        self,
        name: str,
        role: str,
        system_prompt: str = "",
        tools: Iterable[str] | None = None,
    ) -> AgentSpec:
        agent = AgentSpec(
            name=name,
            role=role,
            system_prompt=system_prompt,
            tools=[str(t) for t in (tools or ["claude_code"])],
        )
        self._publish("agentic_workflow_builder.agent_created", {"name": name})
        return agent

    def compose_workflow(self, name: str, agents: Iterable[AgentSpec]) -> Workflow:
        workflow = build_workflow(name, *list(agents))
        self._workflows.append(workflow)
        self._publish(
            "agentic_workflow_builder.workflow_composed",
            {"name": name, "agents": len(workflow.agents)},
        )
        return workflow

    def make_todo_list(self, goal: str, steps: Iterable[str]) -> list[dict]:
        return create_todo_list(goal, steps)

    def make_statement(
        self,
        individual: str,
        description: str,
        category: str,
        field: str = "",
        compliance: Iterable[str] | None = None,
    ) -> ParsedStatement:
        return ParsedStatement(
            individual=individual,
            description=description,
            category=category,
            field=field,
            compliance=list(compliance or []),
        )

    def split_monolith(self, source: str, filename: str = "massive.py") -> list[dict]:
        return decompose_module(source, filename)

    def cost(self, hours: float | None = None) -> dict:
        cfg = self._config or {}
        plan = str(cfg.get("plan", "api"))
        hourly = float(cfg.get("hourly_rate", 5.0))
        return estimate_cost(hours=hours, plan=plan, hourly_rate=hourly)

    def stats(self) -> dict:
        return {
            "module": self.name,
            "version": self.version,
            "status": self.status.value,
            "workflow_count": len(self._workflows),
            "environment": (self._config or {}).get("environment", "wsl"),
        }

    # -- helpers ------------------------------------------------------------
    def _publish(self, topic: str, payload: dict) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(
                Event.create(topic=topic, source=self.name, payload=payload)
            )


def create_agentic_workflow_builder_module(config: dict | None = None) -> AgenticWorkflowBuilderModule:
    """Factory used for kernel discovery / direct instantiation."""
    return AgenticWorkflowBuilderModule(config=config)
