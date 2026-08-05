"""Tests for the Enterprise Model Miner module."""

from __future__ import annotations

import sys  # noqa: E402
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from modules.model_miner import (  # noqa: E402
    ModelMinerModule,
    create_model_miner_module,
)


@pytest.fixture
def module() -> ModelMinerModule:
    return create_model_miner_module({"test": True})


def test_module_meta_fields(module: ModelMinerModule) -> None:
    assert module.name == "model_miner"
    assert module.version == "1.0.0"


@pytest.mark.asyncio
async def test_module_lifecycle(module: ModelMinerModule) -> None:
    await module.initialize()
    assert module.status.value == "healthy"  # type: ignore[attr-defined]
    health = await module.health_check()
    assert health.value in ("healthy", "unhealthy")
    await module.shutdown()


def test_facade_returns_structured_status(module: ModelMinerModule) -> None:
    facade = module.facade()
    st = facade.status()
    assert isinstance(st, dict)
    assert "available" in st
    # discover may return real models or empty list if package absent, but must
    # always be a list and never raise.
    assert isinstance(facade.discover(), list)


def test_facade_mine_never_raises(module: ModelMinerModule) -> None:
    facade = module.facade()
    res = facade.mine("__nonexistent_model__")
    assert isinstance(res, dict)
    assert "ok" in res  # either True (mined) or False (error/absent pkg)


def test_create_helper_returns_module() -> None:
    assert isinstance(create_model_miner_module({"x": 1}), ModelMinerModule)
