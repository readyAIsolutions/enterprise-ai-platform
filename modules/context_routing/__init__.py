"""Context Routing module — task→(read/skip/skills) routing with token discipline.

Implements the routing-table + progressive-disclosure principles extracted from
the pulled JE Van Clief transcript "Stop Building AI Agents. Use This Folder
System Instead": tell the agent exactly which files to read and skip for a task,
within a token budget, so it never wastes context or guesses wrong.

Export surface:
  * ContextRouter — the routing table engine.
  * RoutingRule — one task's read/skip/skills/budget rule.
  * example_rules() — a ready-made ruleset (project-doc oriented).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import HealthStatus, Module, module

from .router import ContextRouter, RoutingRule, TOKENS_PER_BYTE  # noqa: F401

logger = logging.getLogger("eni.context_routing")
__version__ = "1.0.0"


def example_rules() -> List[RoutingRule]:
    """A demonstration ruleset: intake/read only what the task needs."""
    return [
        RoutingRule(task="intake", read=["README.md", "docs/architecture*"],
                    skip=["data/", "logs/"], skills=["file-read"], budget_tokens=6000),
        RoutingRule(task="verify", read=["tests/", "docs/checklist*"],
                    skip=["build/", "node_modules/"], skills=["shell"],
                    budget_tokens=4000),
        RoutingRule(task="write", read=["docs/template*", "styleguide.md"],
                    skip=["data/"], skills=["write-file"], budget_tokens=9000),
        RoutingRule(task="default", read=["**/*.md"], skip=[], skills=[],
                    budget_tokens=12000, fallback=True),
    ]


def make_router(rules: Optional[List[RoutingRule]] = None) -> ContextRouter:
    return ContextRouter(rules if rules is not None else example_rules())


@module(
    name="context_routing",
    version="1.0.0",
    config_defaults={"budget_default": 8000},
)
class ContextRoutingModule(Module):
    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self.router: Optional[ContextRouter] = None

    async def initialize(self) -> None:
        self.router = make_router()
        self.status = HealthStatus.HEALTHY

    async def health_check(self) -> HealthStatus:
        return HealthStatus.HEALTHY if self.router is not None else HealthStatus.UNHEALTHY

    async def shutdown(self) -> None:
        self.status = HealthStatus.UNKNOWN

    # facade
    def route(self, task: str) -> Dict[str, Any]:
        return self.router.route(task).__dict__

    def budget(self, task: str, files: Dict[str, int]) -> Dict[str, Any]:
        return self.router.budget(task, files)


def create_context_routing_module(config: Optional[dict[str, Any]] = None) -> ContextRoutingModule:
    return ContextRoutingModule(config=config or {})


__all__ = ["ContextRouter", "RoutingRule", "ContextRoutingModule",
           "create_context_routing_module", "make_router", "example_rules",
           "TOKENS_PER_BYTE", "__version__"]