"""Video as Code Enterprise Module.

Grounded in the JEVanClief talk *"Video as Code: My AI Animation Stack"*
(https://www.youtube.com/watch?v=yEa6dgh7wuc). Treats AI video/animation
generation as software engineering applied to a creative problem, where the
hard work is the spec (a markdown "brief") rather than the AI or the code.
A loose spec makes the agent "make more interpretive choices or hallucinate
more"; a tight spec "directs it at every beat" — *"Give me the freedom of a
tight brief."*

This module expose a network-free, stdlib-only spec-driven generation pipeline:

  * ``VideoSpec`` / ``Scene`` — structured brief model.
  * ``parse_spec_markdown`` / ``spec_from_dict`` — describe a brief.
  * ``validate_spec`` — warns on missing/loose fields.
  * ``tightness_score`` / ``hallucination_risk_estimate`` — tightness scoring.
  * ``PipelineRunner`` — spec -> (optional generation) -> assembly manifest ->
    final artifact. Generation is an injectable deterministic ``StubGenerator``;
    the ``RealGenerator`` interface degrades gracefully (ok: False) when no
    external tooling is available.

Exports:
  VideoAsCodeModule — @module-decorated Module subclass
  plus the pure pipeline API from .video_as_code.

Version: 1.0.0
Python: 3.10+
"""

from __future__ import annotations

__version__ = "1.0.0"
__module__ = "video_as_code"

import asyncio  # noqa: F401
import logging
import threading
from typing import Any

from enterprise.platform_kernel import Event, EventBus, HealthStatus, Module, module

from .video_as_code import (  # noqa: F401
    LOOSE_SPEC_CLAIM,
    TIGHT_BRIEF_QUOTE,
    VIDEO_AS_CODE_STACK,
    AssemblyManifest,
    Generator,
    GenerationError,
    PipelineResult,
    PipelineRunner,
    RealGenerator,
    Scene,
    SceneRender,
    SpecValidationReport,
    StubGenerator,
    VideoSpec,
    hallucination_risk_estimate,
    hallucination_risk_label,
    parse_spec_markdown,
    run_pipeline,
    run_pipeline_from_dict,
    scene_count,
    spec_from_dict,
    spec_to_dict,
    tightness_score,
    total_duration,
    validate_spec,
)

__all__ = [
    "__version__",
    "VideoAsCodeModule",
    # pure pipeline API
    "VideoSpec",
    "Scene",
    "SpecValidationReport",
    "parse_spec_markdown",
    "spec_to_dict",
    "spec_from_dict",
    "validate_spec",
    "tightness_score",
    "hallucination_risk_estimate",
    "hallucination_risk_label",
    "Generator",
    "RealGenerator",
    "StubGenerator",
    "SceneRender",
    "GenerationError",
    "PipelineRunner",
    "PipelineResult",
    "AssemblyManifest",
    "run_pipeline",
    "run_pipeline_from_dict",
    "total_duration",
    "scene_count",
    "VIDEO_AS_CODE_STACK",
    "TIGHT_BRIEF_QUOTE",
    "LOOSE_SPEC_CLAIM",
    "create_video_as_code_module",
]

# Module logger
_logger: logging.Logger = logging.getLogger("enterprise.video_as_code")


@module(
    name="video_as_code",
    version="1.0.0",
    config_defaults={
        "publish_events": True,
        "default_pipeline_source": "brief.markdown",
        "generator": "stub",  # "stub" | "real" — real degrades when no tooling
    },
)
class VideoAsCodeModule(Module):
    """Enterprise Video-as-Code module.

    Wraps the pure, network-free spec-driven generation pipeline and exposes it
    to the Platform Kernel. On initialization it validates its settings, stands
    up a default :class:`PipelineRunner`, and performs a health check.

    If no event bus is wired (``set_event_bus`` not called), the module stays
    fully functional but simply does not publish events.

    Events published (only when an event bus is present):
      - video_as_code.pipeline.ran
      - video_as_code.health.status
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._runner: PipelineRunner | None = None
        self._event_bus: EventBus | None = None
        self._lock: threading.RLock = threading.RLock()

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def runner(self) -> PipelineRunner | None:
        """Return the active :class:`PipelineRunner`, if initialized."""
        with self._lock:
            return self._runner

    @property
    def event_bus(self) -> EventBus | None:
        """Return the wired event bus, if any."""
        with self._lock:
            return self._event_bus

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Initialize the Video-as-Code module.

        Registers the pure pipeline core, sets a default pipeline runner, and
        runs an initial health check. On failure the module is marked
        UNHEALTHY and the exception is re-raised.
        """
        with self._lock:
            self._status = HealthStatus.STARTING
            generator: Generator = StubGenerator()
            if self._config.get("generator", "stub") == "real":
                generator = RealGenerator()  # degrades gracefully offline
            self._runner = PipelineRunner(generator=generator)

        try:
            _logger.info(
                "Video-as-Code module initializing (generator=%s)",
                self._config.get("generator", "stub"),
            )
            # Basic sanity check of the pure core on startup.
            if not self._runner:
                raise RuntimeError("pipeline runner failed to initialize")
            health = await self.health_check()
            if health is not HealthStatus.HEALTHY:
                raise RuntimeError(f"initial health check returned {health.value}")
            self._status = HealthStatus.HEALTHY
            _logger.info("Video-as-Code module initialized successfully")
        except Exception as exc:
            _logger.exception("Failed to initialize Video-as-Code module: %s", exc)
            self._status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        """Return the module's health status.

        The core is pure/stdlib-only, so health reflects whether the pipeline
        runner is available and sane.
        """
        with self._lock:
            runner = self._runner
        if runner is None:
            self._status = HealthStatus.UNKNOWN
            return self._status
        try:
            if runner.generator is None:
                raise RuntimeError("generator is None")
            self._status = HealthStatus.HEALTHY
        except Exception as exc:
            _logger.exception("Health check failed: %s", exc)
            self._status = HealthStatus.UNHEALTHY
        return self._status

    async def shutdown(self) -> None:
        """Gracefully shut down the module."""
        with self._lock:
            self._status = HealthStatus.STOPPING
        _logger.info("Shutting down Video-as-Code module...")
        try:
            with self._lock:
                self._runner = None
            self._status = HealthStatus.HEALTHY
            _logger.info("Video-as-Code module shut down successfully")
        except Exception as exc:
            _logger.exception("Error during Video-as-Code shutdown: %s", exc)
            self._status = HealthStatus.UNHEALTHY
            raise

    # ── Event Bus Wiring ─────────────────────────────────────────────────

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Wire the platform EventBus into this module.

        Called by the Platform Kernel after module discovery but before
        initialize().  If an event bus is already active it is replaced
        gracefully.
        """
        with self._lock:
            self._event_bus = event_bus

    # ── Public helpers ───────────────────────────────────────────────────

    def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        """Publish an event only when an event bus is wired (not None)."""
        with self._lock:
            bus = self._event_bus
        if bus is not None:
            bus.publish(Event.create(topic, source=self.name, payload=payload))

    async def run_pipeline(
        self,
        spec: VideoSpec,
        output_dir: str | None = None,
        source: str | None = None,
    ) -> PipelineResult:
        """Run the spec pipeline and (if an event bus is wired) publish an event."""
        runner = self._runner or PipelineRunner()
        src = source or str(self._config.get("default_pipeline_source", "brief.markdown"))
        result = await asyncio.to_thread(
            runner.run, spec, output_dir=output_dir, source=src
        )
        self._publish(
            "video_as_code.pipeline.ran",
            {
                "ok": result.ok,
                "spec_title": result.manifest.spec_title,
                "total_scenes": result.manifest.total_scenes,
                "tightness": result.manifest.tightness,
                "hallucination_risk": result.manifest.hallucination_risk,
            },
        )
        return result


def create_video_as_code_module(config: dict[str, Any] | None = None) -> VideoAsCodeModule:
    """Create a :class:`VideoAsCodeModule` from an optional config dict.

    The config may contain ``publish_events`` (bool), ``generator``
    (``"stub"`` or ``"real"``) and ``default_pipeline_source`` (str).

    Args:
        config: Optional module configuration dictionary.

    Returns:
        A fully constructed :class:`VideoAsCodeModule`.
    """
    cfg = dict(config or {})
    return VideoAsCodeModule(
        config={
            "publish_events": cfg.get("publish_events", True),
            "generator": cfg.get("generator", "stub"),
            "default_pipeline_source": cfg.get(
                "default_pipeline_source", "brief.markdown"
            ),
        }
    )