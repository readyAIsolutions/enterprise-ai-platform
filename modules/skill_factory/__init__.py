"""
ENI Skill Factory Module — Meta-Skill Generator / Registry / Self-Evolution.

Enterprise-grade module that discovers, generates, stores, versions, benchmarks,
and self-evolves markdown skill recipes (superpowers / hermes-skill-factory /
SkillClaw concepts).

Capabilities
------------
* SkillRegistry  — filesystem-backed versioned registry of ``SKILL.md`` recipes.
* SkillGenerator — meta-skill auto-generation from prompts or command sequences.
* SkillEvolutionLoop — benchmark scores, feedback trails, and self-evolution.

Exports:
  SkillFactoryModule — @module-decorated Module subclass
  SkillFactory       — facade over registry + generator + evolution
  SkillRegistry      — versioned markdown skill store
  SkillGenerator     — meta-skill auto-generation
  SkillEvolutionLoop — benchmark / refine / self-evolve
  SkillRecord        — versioned skill data model

Version: 1.0.0
Python: 3.10+
"""

from __future__ import annotations

__version__ = "1.0.0"
__module__ = "skill_factory"

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from enterprise.platform_kernel import (
    Event,
    EventBus,
    EventPriority,
    HealthStatus,
    Module,
    module,
)

from .skill_factory import (
    MAX_STEPS,
    SCORE_ALPHA,
    SkillEvolutionLoop,
    SkillFactory,
    SkillGenerator,
    SkillRecord,
    SkillRegistry,
    build_frontmatter,
    bump_version,
    extract_steps,
    moving_average,
    name_from_prompt,
    parse_frontmatter,
)
from .skills_import import (
    SkillImport,
    SkillsImportFacade,
    import_skill_from_markdown,
    parse_skill_markdown,
)
from .evolution import (
    DEFAULT_PROMOTE_THRESHOLD,
    EvolutionEngine,
    RESULT_FAIL,
    RESULT_SUCCESS,
    SkillFeedbackStore,
    SkillScore,
    compute_evolution_score,
)

__all__ = [
    "__version__",
    "SkillFactoryModule",
    "SkillFactory",
    "SkillRegistry",
    "SkillGenerator",
    "SkillEvolutionLoop",
    "SkillRecord",
    "build_frontmatter",
    "parse_frontmatter",
    "extract_steps",
    "name_from_prompt",
    "bump_version",
    "moving_average",
    "MAX_STEPS",
    "SCORE_ALPHA",
    # Standard markdown-skills import capability
    "SkillImport",
    "SkillsImportFacade",
    "import_skill_from_markdown",
    "parse_skill_markdown",
    # Real outcome-based evolution (master-class)
    "EvolutionEngine",
    "SkillFeedbackStore",
    "SkillScore",
    "compute_evolution_score",
    "RESULT_SUCCESS",
    "RESULT_FAIL",
    "DEFAULT_PROMOTE_THRESHOLD",
]

# ---------------------------------------------------------------------------
# Module logger
# ---------------------------------------------------------------------------
_logger: logging.Logger = logging.getLogger("enterprise.skill_factory")

# Default data directory: <repo_root>/data/skills
_DEFAULT_DATA_DIR: Path = Path(__file__).resolve().parents[2] / "data" / "skills"


@module(name="skill_factory", version="1.0.0")
class SkillFactoryModule(Module):
    """Enterprise Skill Factory Module.

    Bundles the SkillRegistry, SkillGenerator and SkillEvolutionLoop behind a
    single SkillFactory facade, wired into the Platform Kernel lifecycle and
    event bus.

    Events published:
      - skill.created
      - skill.updated
      - skill.evolved

    Configuration keys:
      - ``data_dir``      (str)    Root data directory (default: ``<repo_root>/data/skills``).
      - ``auto_generate`` (bool)   Reserved for future auto-generation behaviour.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._factory: SkillFactory | None = None
        self._event_bus: EventBus | None = None

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def factory(self) -> SkillFactory | None:
        """Return the active SkillFactory, if initialized."""
        return self._factory

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Build the SkillFactory from configuration and run a health check."""
        self._status = HealthStatus.STARTING
        try:
            data_dir = Path(self._config.get("data_dir", str(_DEFAULT_DATA_DIR)))
            _logger.info(
                "SkillFactory module initializing (data_dir=%s)", data_dir
            )

            self._factory = SkillFactory(data_dir=data_dir)
            if self._event_bus is not None:
                self._factory.set_event_publisher(self._publish_event)

            # Ensure the skills root is created and writable during startup.
            self._factory.registry.ensure()

            self._status = HealthStatus.HEALTHY
            _logger.info("SkillFactory module initialized successfully")
        except Exception as exc:
            _logger.exception("Failed to initialize SkillFactory module: %s", exc)
            self._status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        """Return HEALTHY if the registry directory is writable, else UNHEALTHY."""
        if self._factory is None:
            self._status = HealthStatus.UNHEALTHY
            return self._status

        try:
            if self._factory.registry.is_writable():
                self._status = HealthStatus.HEALTHY
            else:
                self._status = HealthStatus.UNHEALTHY
        except Exception as exc:
            _logger.exception("SkillFactory health check failed: %s", exc)
            self._status = HealthStatus.UNHEALTHY
        return self._status

    async def shutdown(self) -> None:
        """Gracefully shut down the SkillFactory module."""
        self._status = HealthStatus.STOPPING
        _logger.info("Shutting down SkillFactory module...")
        try:
            if self._factory is not None:
                # No open resources to release; detach the event publisher.
                self._factory.set_event_publisher(None)
                self._factory = None
            self._event_bus = None
            self._status = HealthStatus.HEALTHY
            _logger.info("SkillFactory module shut down successfully")
        except Exception as exc:
            _logger.exception("Error during SkillFactory shutdown: %s", exc)
            self._status = HealthStatus.UNHEALTHY
            raise

    # ── Event Bus Wiring ─────────────────────────────────────────────────

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Wire the platform EventBus into this module.

        Called by the Platform Kernel after module discovery but before
        ``initialize()``.  Also forwards the bus to the active factory so that
        skill lifecycle events are published.
        """
        self._event_bus = event_bus
        if self._factory is not None:
            self._factory.set_event_publisher(self._publish_event)

    def _publish_event(self, topic: str, payload: dict[str, Any]) -> None:
        """Publish a skill event on the platform bus, guarding a None bus."""
        if self._event_bus is None:
            return
        try:
            event = Event.create(
                topic=topic,
                source="skill_factory",
                payload=payload,
                priority=EventPriority.NORMAL,
            )
            self._event_bus.publish(event)
        except Exception as exc:
            _logger.warning("Failed to publish event %s: %s", topic, exc)
