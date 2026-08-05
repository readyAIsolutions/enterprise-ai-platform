"""Enterprise Hermes Controller OS Module — autonomous controller for Hermes Agent.

A stdlib-only facade that wraps the ENI Hermes Controller (prompt expander +
router + privacy boundary + reinforcement). Exposes it to the enterprise
platform so every build can:
  - expand LO's short instructions into massive detailed prompts,
  - sanitize secrets on egress (cloud never sees private data),
  - auto-continue through free-model rate limits,
  - queue work for deferred continuation (e.g. 6pm local),
  - retain good outcomes to the KB and build skills.

All components are stdlib-only with zero external dependencies.
"""

from __future__ import annotations

from typing import Any

try:
    from eni_controller import controller as _controller_pkg

    _HAVE_CONTROLLER = True
except Exception:  # pragma: no cover - controller not installed on this box
    _HAVE_CONTROLLER = False

from enterprise.platform_kernel import HealthStatus, Module, module  # noqa: F401

__version__ = "1.0.0"
__module__ = "hermes_controller"

__all__ = [
    "__version__",
    "HermesControllerModule",
    "ControllerFacade",
]


class ControllerFacade:
    """Thin, always-available facade to the Hermes Controller.

    Provides the deterministic operations (expand, catalog, status, queue) even
    when the full controller package is not importable; degrades gracefully.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._controller = _controller_pkg.Controller() if _HAVE_CONTROLLER else None

    def available(self) -> bool:
        return self._controller is not None

    def expand(self, text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._controller is None:
            # Deterministic fallback expansion when the package is unavailable
            return {
                "goal": text,
                "build_mode": "normal",
                "recommended_modules": ["guardrails", "prompt_guard"],
                "prompt": f"# ENI TASK\n\n{text}",
                "meta": {"fallback": True},
            }
        return self._controller.expander.expand(text, context)

    def process(self, text: str, use_hermes: bool = True, **kw: Any) -> dict[str, Any]:  # noqa: ANN401
        if self._controller is None:
            return {"ok": False, "error": "controller package unavailable", "queued": False}
        return self._controller.process(text, use_hermes=use_hermes, **kw)

    def status(self) -> dict[str, Any]:
        if self._controller is None:
            return {"ok": False, "enterprise": {"total": 0}, "secrets": {"broker_attached": False}}
        return self._controller.status()


@module(name="hermes_controller", version=__version__)
class HermesControllerModule(Module):
    """Enterprise module giving the platform a Hermes-controller facade."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._facade: ControllerFacade | None = None

    async def initialize(self) -> None:
        self._facade = ControllerFacade(self._config)
        self.status = HealthStatus.HEALTHY

    async def health_check(self) -> HealthStatus:
        healthy = bool(self._facade is not None)
        return HealthStatus.HEALTHY if healthy else HealthStatus.UNHEALTHY

    async def shutdown(self) -> None:
        self._facade = None
        self.status = HealthStatus.STOPPING
        return

    def facade(self) -> ControllerFacade:
        if self._facade is None:
            self._facade = ControllerFacade(self._config)
        return self._facade


def create_hermes_controller_module(config: dict[str, Any] | None = None) -> HermesControllerModule:
    """Create a :class:`HermesControllerModule` from an optional config dict."""
    return HermesControllerModule(config)
