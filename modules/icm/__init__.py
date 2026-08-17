"""ICM (Interpretable Context Methodology) — skill/prompt-engineering layer.

Registers the ICM engine as a first-class Platform Kernel module so the rest of
the stack can:
  * scaffold standard numbered-stage skill projects,
  * route a task to the correct stage folder via 00_master.md,
  * load ONLY the current stage's markdown (progressive disclosure → lighter
    token spend per OpenRouter / swarm call),
  * classify whether a task belongs in deterministic sequential ICM work or in
    the concurrent multi-agent swarm layer (division of labor, spec §3).

This is the prompt-engineering discipline layer: orchestration decides WHICH
agent runs a task; ICM governs HOW that single agent structures its execution.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from enterprise.platform_kernel import HealthStatus, Module, module

from .icm import ICMProject, StageFolder, classify, should_use_swarm  # noqa: F401
from .scaffold import DEFAULT_STAGES, scaffold  # noqa: F401

logger = logging.getLogger("eni.icm")

__version__ = "1.0.0"


@module(
    name="icm",
    version="1.0.0",
    config_defaults={
        # default directory the CLI/scaffold writes new skill projects into
        "projects_dir": "icm_projects",
        "auto_scaffold": False,
    },
)
class ICMModule(Module):
    """Kernel module exposing the Interpretable Context Methodology engine."""

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self.projects_dir: Optional[Path] = None
        self._last_route: Optional[dict[str, Any]] = None
        self._init_error: Optional[str] = None

    async def initialize(self) -> None:
        try:
            pd = self.config.get("projects_dir", "icm_projects")
            base = Path(pd)
            if not base.is_absolute():
                base = (self._repo_root or Path(".")) / pd
            base.mkdir(parents=True, exist_ok=True)
            self.projects_dir = base
            self.status = HealthStatus.HEALTHY
        except Exception as exc:  # defensively mark unhealthy, never crash kernel
            self._init_error = str(exc)
            self.status = HealthStatus.UNHEALTHY
            logger.warning("ICM module init failed: %s", exc)

    async def health_check(self) -> HealthStatus:
        if self._init_error:
            return HealthStatus.UNHEALTHY
        return HealthStatus.HEALTHY

    async def shutdown(self) -> None:
        self.status = HealthStatus.UNKNOWN
        logger.info("ICM module shutdown")

    @property
    def _repo_root(self) -> Optional[Path]:
        # repo root: enterprise/ is the package; root is two levels up from modules/icm
        return Path(__file__).resolve().parent.parent.parent

    # ------------------------------------------------------------- facade
    def new_project(self, name: str, stages: Optional[list[str]] = None) -> Path:
        """Scaffold a new skill project and return its root path."""
        target = (self.projects_dir or Path(name)) / name
        return scaffold(target, stages=stages, with_examples=True)

    def route(self, project_dir: str, task: str) -> dict[str, Any]:
        """Route a task to a stage folder; return a compact routing summary."""
        proj = ICMProject.open(project_dir)
        stage = proj.route(task)
        result = {
            "project": str(proj.root),
            "task": task,
            "route": classify(task),
            "stage": stage.slug if stage else None,
        }
        self._last_route = result
        return result

    def stage_context(self, project_dir: str, stage: str) -> str:
        """Return only the markdown for one stage (progressive disclosure)."""
        proj = ICMProject.open(project_dir)
        for s in proj.stages:
            if s.slug == stage or stage in s.slug:
                return proj.stage_context(s)
        return ""


def create_icm_module(config: Optional[dict[str, Any]] = None) -> ICMModule:
    """Create (but do not initialize) an :class:`ICMModule`."""
    return ICMModule(config=config or {})


__all__ = [
    "ICMModule",
    "create_icm_module",
    "ICMProject",
    "StageFolder",
    "scaffold",
    "classify",
    "should_use_swarm",
    "DEFAULT_STAGES",
    "__version__",
]