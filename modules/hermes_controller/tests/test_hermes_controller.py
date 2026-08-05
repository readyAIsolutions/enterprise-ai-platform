"""Tests for the Enterprise Hermes Controller module."""

from __future__ import annotations

import pytest

from modules.hermes_controller import (
    ControllerFacade,
    HermesControllerModule,
    create_hermes_controller_module,
)


def _controller_available() -> bool:
    try:
        return ControllerFacade().available()
    except Exception:
        return False


@pytest.fixture
def module() -> HermesControllerModule:
    return create_hermes_controller_module({"test": True})


def test_module_meta_fields(module: HermesControllerModule) -> None:
    assert module.name == "hermes_controller"
    assert module.version == "1.0.0"


@pytest.mark.asyncio
async def test_module_lifecycle(module: HermesControllerModule) -> None:
    await module.initialize()
    assert module.status.value == "healthy"  # type: ignore[attr-defined]
    health = await module.health_check()
    assert health.value in ("healthy", "unhealthy")
    await module.shutdown()


def test_facade_always_returns_expand(module: HermesControllerModule) -> None:
    facade = module.facade()
    res = facade.expand("build a new module")
    assert isinstance(res, dict)
    assert "goal" in res
    assert "prompt" in res
    assert res["goal"] == "build a new module"
    # Either full or fallback expansion must yield a non-empty prompt
    assert len(res["prompt"]) > 0


def test_facade_process_fallback(module: HermesControllerModule) -> None:
    facade = module.facade()
    res = facade.process("hello")
    # When the full controller isn't importable in this env, we must still get
    # a structured, non-crashing response (graceful degradation).
    assert isinstance(res, dict)
    assert "ok" in res


def test_create_helper_returns_module() -> None:
    assert isinstance(create_hermes_controller_module({"x": 1}), HermesControllerModule)
