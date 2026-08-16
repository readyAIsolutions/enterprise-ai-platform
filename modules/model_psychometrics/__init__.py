"""Enterprise Model Psychometrics OS Module — audit the trait profile of AI
models with validated psychometric scales.

Grounded in JEVanClief's "ethics engine" / "becoming an AI psychologist"
pipeline (data/transcripts/JEVanClief/UGyTimVObus.md and Wtf6E-fwuwI.md): a
data pipeline that administers validated personality / psychometric scales
(right-wing authoritarianism, moral foundations, social dominance, Rosenberg
self-esteem) across AI models, personas, model variations and providers to tell
you where a model "lands" on moral foundations / authoritarianism / personality
dimensions.

Module design (mirroring the transcript's own engineering notes):
  * Scales are data — name, description, citation, Likert response range,
    item text, reverse-score flags — and users can select built-ins or add
    custom scales.
  * The pipeline runs scales against AI models through a provider-adapter
    interface. Real providers need credentials and degrade gracefully when
    none are present; the core is network-free and stdlib-only.
  * Stateless by design: no secrets are stored (matches the transcript's
    "it is stateless / doesn't save any personal information").

Version: 1.0.0
Python: 3.10+
"""

from __future__ import annotations

import logging
from typing import Any

from enterprise.platform_kernel import HealthStatus, Module, module  # noqa: F401

from .model_psychometrics import (  # noqa: F401
    DEFAULT_SCALES,
    BatchReport,
    ModelProfile,
    ModelPsychometricsRunner,
    NoopProvider,
    ProfileReport,
    ProviderAdapter,
    PsychometricItem,
    PsychometricScale,
    RealProvider,
    ScaleRegistry,
    ScaleResult,
    TestProvider,
    build_custom_scale,
    summarize_battery,
)

__version__ = "1.0.0"
__module__ = "model_psychometrics"

_logger = logging.getLogger("eni.model_psychometrics")

__all__ = [
    "__version__",
    "ModelPsychometricsModule",
    # public API re-exported from the core
    "PsychometricItem",
    "PsychometricScale",
    "ScaleRegistry",
    "DEFAULT_SCALES",
    "ProviderAdapter",
    "TestProvider",
    "NoopProvider",
    "RealProvider",
    "ModelProfile",
    "ScaleResult",
    "ProfileReport",
    "BatchReport",
    "ModelPsychometricsRunner",
    "build_custom_scale",
    "summarize_battery",
]


@module(
    name="model_psychometrics",
    version=__version__,
    config_defaults={
        "registry": "defaults",  # "defaults" | "empty" (start with no scales)
        "publish_events": True,
    },
)
class ModelPsychometricsModule(Module):
    """Enterprise module exposing a stateless model-psychometrics pipeline.

    The core is network-free and stores nothing; this Module exists so the
    pipeline can be discovered, initialized, health-checked and shut down as a
    first-class platform module, and so battery-completion events can be
    published to the platform EventBus when one is wired in.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._event_bus: Any | None = None
        self._registry: ScaleRegistry | None = None
        self._runner: ModelPsychometricsRunner | None = None

    # ------------------------------------------------------------------ props

    @property
    def registry(self) -> ScaleRegistry | None:
        """The active :class:`ScaleRegistry`, if initialized."""
        return self._registry

    @property
    def runner(self) -> ModelPsychometricsRunner | None:
        """A default stateless runner tied to this module's registry (may be
        ``None`` until :meth:`initialize` runs)."""
        return self._runner

    # -------------------------------------------------------------- lifecycle

    async def initialize(self) -> None:
        """Build the scale registry and runner.

        Sets ``status = HEALTHY`` on success; on failure sets ``UNHEALTHY`` and
        re-raises so the platform startup can surface the error.
        """
        self._status = HealthStatus.STARTING
        try:
            default_provider = TestProvider(
                provider_name="module-default", model_name="module-default"
            )
            if self._config.get("registry", "defaults") == "empty":
                registry = ScaleRegistry.empty()
            else:
                registry = ScaleRegistry.defaults()
            self._registry = registry
            self._runner = ModelPsychometricsRunner(provider=default_provider, registry=registry)

            self._publish("model_psychometrics.initialized", {"version": __version__})
            self._status = HealthStatus.HEALTHY
            _logger.info("Model Psychometrics module initialized (scales=%d)", len(registry))
        except Exception as exc:
            _logger.exception("Failed to initialize model_psychometrics module: %s", exc)
            self._status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        """Report health based on whether the registry/runner are present."""
        healthy = self._registry is not None and self._runner is not None
        self._status = HealthStatus.HEALTHY if healthy else HealthStatus.UNHEALTHY
        return self._status

    async def shutdown(self) -> None:
        """Release the registry and runner (there is no other state to clean)."""
        self._status = HealthStatus.STOPPING
        self._runner = None
        self._registry = None
        self._event_bus = None
        self._status = HealthStatus.HEALTHY
        _logger.info("Model Psychometrics module shut down")

    # ------------------------------------------------------------- event bus

    def set_event_bus(self, event_bus: Any) -> None:
        """Wire the platform EventBus into this module for event publishing."""
        self._event_bus = event_bus

    def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        """Publish an event to the wired EventBus, only when one is set."""
        bus = self._event_bus
        if bus is None:
            return
        try:
            bus.publish(
                bus.Event.create(topic=topic, source="model_psychometrics", payload=payload)
                if hasattr(bus, "Event")
                else __import__(
                    "enterprise.platform_kernel", fromlist=["Event"]
                ).Event.create(
                    topic=topic, source="model_psychometrics", payload=payload
                )
            )
        except Exception as exc:  # publishing must never crash lifecycle
            _logger.warning("model_psychometrics event publish failed: %s", exc)


def create_model_psychometrics_module(
    config: dict[str, Any] | None = None,
) -> ModelPsychometricsModule:
    """Create a :class:`ModelPsychometricsModule` from an optional config dict.

    The config may contain ``registry`` ("defaults" or "empty") and
    ``publish_events`` (bool).
    """
    cfg = dict(config or {})
    return ModelPsychometricsModule(
        config={
            "registry": cfg.get("registry", "defaults"),
            "publish_events": cfg.get("publish_events", True),
        }
    )
