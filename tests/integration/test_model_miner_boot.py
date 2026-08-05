"""Verify the ENI Model Miner module is discovered by the platform registry."""

from __future__ import annotations

from pathlib import Path

from enterprise.platform_kernel import ModuleRegistry


def test_model_miner_registry_discovery() -> None:
    registry = ModuleRegistry(Path(__file__).resolve().parents[2] / "modules")
    names = registry.discover()
    assert "model_miner" in names, f"model_miner not discovered (got {names})"
