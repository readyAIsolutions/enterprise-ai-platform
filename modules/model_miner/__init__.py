"""Enterprise Model Miner OS Module — scan/rip local model training into the KB.

Turns LO's idea into a first-class enterprise module: scan local models that
have training worth using, connect to each, "rip" their trained knowledge into
the local knowledge base, and expose each model to Hermes via a local MCP-style
tool + LSP note. Runs as part of the enterprise platform lifecycle (initialize /
health_check / shutdown) and can be booted as an infinite ever-expanding loop.

Data flow (all local-first, no cloud egress unless the chosen model is a local
endpoint):
  scan  -> discover local models (ollama, local OpenAI-compat, HF cache)
  rip   -> probe each chat-capable model with a curated topic battery
  store -> save each answer to the KB (deduplicated, tagged, provenance)
  serve -> register model as a local MCP tool + LSP note for Hermes

All components are stdlib-only with zero external dependencies.
"""

from __future__ import annotations

import logging
from typing import Any

try:
    from eni_controller import model_miner as _miner_pkg, model_trainer as _trainer_pkg

    _HAVE_MINER = True
except Exception:  # pragma: no cover - controller not installed on this box
    _HAVE_MINER = False

from enterprise.platform_kernel import HealthStatus, Module, module  # noqa: F401

logger = logging.getLogger("eni.model_miner_module")

__version__ = "1.0.0"
__module__ = "model_miner"

__all__ = ["__version__", "ModelMinerModule", "ModelMinerFacade"]


class MinerFacade:
    """Thin, always-available facade to the ENI Model Miner.

    Provides deterministic scan/rip/status operations even when the full
    controller package is unavailable; degrades gracefully.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._miner = _miner_pkg.get_miner() if _HAVE_MINER else None
        self._trainer = _trainer_pkg.get_trainer() if _HAVE_MINER else None
        self._ripple = (
            _trainer_pkg.CloudRipple(store=_trainer_pkg.get_trainer().store)
            if _HAVE_MINER
            else None
        )

    def available(self) -> bool:
        return self._miner is not None

    def discover(self) -> list[dict[str, Any]]:
        if self._miner is None:
            return []
        try:
            return self._miner.discover()
        except Exception as e:  # noqa: BLE001 - degrade gracefully
            logger.warning(f"miner discover failed: {e}")
            return []

    def mine(
        self, model_name: str | None = None, topics: list[dict[str, str]] | None = None
    ) -> dict[str, Any]:
        if self._miner is None:
            return {
                "ok": False,
                "error": "model_miner package unavailable",
                "scan": self.discover(),
            }
        try:
            return self._miner.mine(model_name=model_name, topics=topics)
        except Exception as e:  # noqa: BLE001 - isolate failures
            return {"ok": False, "error": str(e), "scan": self.discover()}

    def infinite_loop(
        self, interval: float = 300.0, max_passes: int | None = None
    ) -> dict[str, Any]:
        """Run the ever-expanding scan/rip loop (infinite by default)."""
        if self._miner is None:
            return {"ok": False, "error": "model_miner package unavailable"}
        return self._miner.infinite_loop(interval=interval, max_passes=max_passes)

    # -- Model Trainer (download -> serve -> rip -> delete) ---------------
    def train_and_rip(
        self,
        model: str,
        delete_after: bool = True,
        topics: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Download a HF model, rip its training, delete it after."""
        if self._trainer is None:
            return {"ok": False, "error": "model_trainer package unavailable"}
        return self._trainer.train_and_rip(model, delete_after=delete_after, topics=topics)

    def run_batch(
        self,
        models: list[str] | None = None,
        max_models: int | None = None,
        delete_after: bool = True,
    ) -> dict[str, Any]:
        """Rip through many models, deleting each after (the 'SHIT tons' loop)."""
        if self._trainer is None:
            return {"ok": False, "error": "model_trainer package unavailable"}
        return self._trainer.run_batch(
            models=models, max_models=max_models, delete_after=delete_after
        )

    def drives(self) -> list[dict[str, Any]]:
        if self._trainer is None:
            return []
        return self._trainer.drive_status()

    def cloud_capture(
        self,
        *,
        model: str,
        provider: str,
        prompt: str,
        response: str,
        topic: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Persist a cloud-model exchange as a KB entry (consistent rip)."""
        if self._ripple is None:
            return {"ok": False, "error": "model_trainer package unavailable"}
        return self._ripple.capture(
            model=model,
            provider=provider,
            prompt=prompt,
            response=response,
            topic=topic,
            tags=tags,
        )

    def status(self) -> dict[str, Any]:
        models = self.discover()
        return {
            "available": self.available(),
            "models_discovered": len(models),
            "models": [m["name"] for m in models],
            "sources": sorted({m.get("source", "") for m in models}),
        }


@module(name="model_miner", version=__version__)
class ModelMinerModule(Module):
    """Enterprise module giving the platform a local-model miner facade."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._facade: MinerFacade | None = None

    async def initialize(self) -> None:
        self._facade = MinerFacade(self._config)
        self.status = HealthStatus.HEALTHY
        logger.info("Model Miner module initialized")

    async def health_check(self) -> HealthStatus:
        healthy = bool(self._facade is not None)
        return HealthStatus.HEALTHY if healthy else HealthStatus.UNHEALTHY

    async def shutdown(self) -> None:
        self._facade = None
        self.status = HealthStatus.STOPPING
        return

    def facade(self) -> MinerFacade:
        if self._facade is None:
            self._facade = MinerFacade(self._config)
        return self._facade


def create_model_miner_module(config: dict[str, Any] | None = None) -> ModelMinerModule:
    """Create a :class:`ModelMinerModule` from an optional config dict."""
    return ModelMinerModule(config)
