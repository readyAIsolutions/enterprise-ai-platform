"""
Test Suite — InfraStatus facade, module health aggregation, plugin hot-reload
==============================================================================

Covers:
  - InfraStatus registry: status_report() aggregation, determinism, overall
    HEALTHY / DEGRADED / UNHEALTHY mapping, component(name) accessor.
  - ClaudeCodeInfraModule health_check() migrated onto the facade:
    HEALTHY when all core components OK, DEGRADED when one fails.
  - Hardened plugin hot-reload: idempotent load/unload, no double
    registration, change-aware reload (changed_plugins / reload_changed),
    tracked plugin lifecycle state.

Run: python3 -m pytest enterprise/modules/agent_infra/tests/test_infra_status.py -q
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

_ENTERPRISE_ROOT = Path(__file__).resolve().parents[3]
if str(_ENTERPRISE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENTERPRISE_ROOT))

from enterprise.modules.agent_infra import (
    CORE_COMPONENTS,
    ClaudeCodeInfraModule,
    ComponentState,
    ComponentStatus,
    InfraStatus,
)
from enterprise.modules.agent_infra.plugin_system import (
    PluginManager,
    PluginState,
)
from enterprise.platform_kernel import HealthStatus


@pytest.fixture
def event_loop():
    """Create a fresh event loop for each test."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# Fixtures: plugin dir
# =============================================================================

PLUGIN_MANIFEST = {
    "name": "mytest",
    "version": "1.0.0",
    "description": "test plugin",
    "main": "plugin.py",
    "permissions": [],
}

PLUGIN_BODY_V1 = (
    "VALUE = 1\n\ndef on_load(ctx):\n    return True\n\ndef get_value():\n    return VALUE\n"
)
PLUGIN_BODY_V2 = (
    "VALUE = 2\n\ndef on_load(ctx):\n    return True\n\ndef get_value():\n    return VALUE\n"
)


@pytest.fixture
def plugin_manager(tmp_path):
    """A PluginManager pointed exclusively at a temp single-plugin dir."""
    pd = tmp_path / "mytest"
    pd.mkdir(parents=True, exist_ok=True)
    (pd / "plugin.json").write_text(json.dumps(PLUGIN_MANIFEST))
    (pd / "plugin.py").write_text(PLUGIN_BODY_V1)
    return PluginManager(config={"plugin_dirs": [str(tmp_path)], "auto_hot_reload": False})


# =============================================================================
# InfraStatus — status_report aggregation & determinism
# =============================================================================


class TestInfraStatusReport:
    def test_status_report_contains_all_core_components(self) -> None:
        s = InfraStatus()
        for c in CORE_COMPONENTS:
            s.update(c, ok=True)
        report = s.status_report()
        comps = report["components"]
        assert set(comps.keys()) == set(CORE_COMPONENTS)
        assert report["module"] == "agent_infra"
        assert report["overall"] == HealthStatus.HEALTHY.value
        assert report["healthy"] is True

    def test_status_report_is_deterministic_json(self) -> None:
        s = InfraStatus()
        for c in CORE_COMPONENTS:
            s.update(c, ok=True)
        r1 = s.status_report()
        r2 = s.status_report()
        # component names sorted deterministically, fixed key order
        assert list(r1["components"].keys()) == sorted(r1["components"].keys())
        assert list(r1.keys()) == ["module", "overall", "healthy", "checked_at", "components"]
        # JSON-serialisable and stable shape on repeat
        parsed = json.loads(s.to_json())
        assert parsed["overall"] == r1["overall"]
        assert list(parsed["components"].keys()) == list(r1["components"].keys())
        assert list(r2["components"].keys()) == list(r1["components"].keys())
        # each component record carries state/ok/last_check/message
        rec = r1["components"]["tui"]
        assert set(rec.keys()) == {"name", "state", "ok", "last_check", "message"}
        assert rec["ok"] is True
        assert rec["state"] == "ok"
        assert rec["last_check"]


# =============================================================================
# InfraStatus — overall mapping & accessor
# =============================================================================


class TestInfraStatusAggregation:
    def test_healthy_requires_all_core_ok(self) -> None:
        s = InfraStatus()
        for c in CORE_COMPONENTS:
            s.update(c, ok=True)
        assert s.healthy() is True
        s.update("server", ok=False)
        assert s.healthy() is False

    def test_overall_healthy_when_all_components_ok(self) -> None:
        s = InfraStatus()
        for c in CORE_COMPONENTS:
            s.update(c, ok=True)
        assert s.overall_status() == HealthStatus.HEALTHY

    def test_overall_degraded_when_single_component_fails(self) -> None:
        s = InfraStatus()
        for c in CORE_COMPONENTS:
            s.update(c, ok=True)
        s.update("voice", ok=False, state=ComponentState.DEGRADED)
        assert s.overall_status() == HealthStatus.DEGRADED

    def test_overall_unhealthy_when_none_ok(self) -> None:
        s = InfraStatus()
        for c in CORE_COMPONENTS:
            s.update(c, ok=False)
        assert s.overall_status() == HealthStatus.UNHEALTHY

    def test_component_accessor_and_inplace_update(self) -> None:
        s = InfraStatus()
        s.update("buddy", ok=True)
        s.update("buddy", ok=False, message="down")
        comp = s.component("buddy")
        assert isinstance(comp, ComponentStatus)
        assert comp.name == "buddy"
        assert comp.ok is False
        assert comp.message == "down"
        assert s.component("does-not-exist") is None


# =============================================================================
# ClaudeCodeInfraModule — health_check migrated onto facade
# =============================================================================


class TestModuleHealthAggregation:
    async def test_module_initialize_populates_infra_status(self) -> None:
        mod = ClaudeCodeInfraModule()
        await mod.initialize()
        report = mod.infra.status_report()
        assert isinstance(mod.infra, InfraStatus)
        assert set(report["components"].keys()) == set(CORE_COMPONENTS)
        assert mod.status == HealthStatus.HEALTHY

    async def test_module_health_check_healthy_when_components_ok(self) -> None:
        mod = ClaudeCodeInfraModule()
        await mod.initialize()
        status = await mod.health_check()
        assert status == HealthStatus.HEALTHY
        assert mod.infra.overall_status() == HealthStatus.HEALTHY

    async def test_module_component_accessor(self) -> None:
        mod = ClaudeCodeInfraModule()
        await mod.initialize()
        comp = mod.component("tui")
        assert comp is not None
        assert comp.name == "tui"
        assert mod.infra.component("server").ok is True

    async def test_module_health_check_degraded_when_component_fails(self, monkeypatch) -> None:
        mod = ClaudeCodeInfraModule()
        await mod.initialize()

        async def _boom() -> bool:
            return False

        monkeypatch.setattr(mod.voice, "health_check", _boom)
        status = await mod.health_check()
        assert status == HealthStatus.DEGRADED
        assert mod.infra.component("voice").ok is False
        assert mod.infra.overall_status() == HealthStatus.DEGRADED


# =============================================================================
# Plugin hot-reload — idempotent lifecycle
# =============================================================================


class TestPluginHotReloadLifecycle:
    async def test_plugin_load_no_double_registration(self, plugin_manager) -> None:
        await plugin_manager.initialize()  # loads once
        names_after_first = set(plugin_manager.plugins.keys())
        # idempotent load again -> still exactly one instance
        ok = await plugin_manager.load_plugin("mytest")
        assert ok is True
        assert set(plugin_manager.plugins.keys()) == names_after_first
        assert len(plugin_manager.plugins) == 1

    async def test_plugin_unload_idempotent(self, plugin_manager) -> None:
        await plugin_manager.initialize()
        assert await plugin_manager.unload_plugin("mytest") is True
        # second unload of an already-unloaded plugin is a safe no-op
        assert await plugin_manager.unload_plugin("mytest") is True
        assert "mytest" not in plugin_manager.plugins

    async def test_plugin_lifecycle_state_tracked(self, plugin_manager) -> None:
        await plugin_manager.initialize()
        inst = plugin_manager.get_plugin("mytest")
        assert inst.state in (PluginState.LOADED, PluginState.ENABLED)
        detail = plugin_manager.list_plugins()[0]
        assert detail["state"] in ("loaded", "enabled")
        assert detail["checksum"]

    async def test_plugin_unload_removes_from_sys_modules(self, plugin_manager) -> None:
        await plugin_manager.initialize()
        assert "agent_plugins.mytest" in sys.modules
        await plugin_manager.unload_plugin("mytest")
        assert "agent_plugins.mytest" not in sys.modules

    async def test_plugin_reload_plugin(self, plugin_manager) -> None:
        await plugin_manager.initialize()
        assert await plugin_manager.reload_plugin("mytest") is True
        assert plugin_manager.get_plugin("mytest") is not None


# =============================================================================
# Plugin hot-reload — change detection
# =============================================================================


class TestPluginHotReloadChangeDetection:
    async def test_changed_plugins_detects_file_change(self, plugin_manager, tmp_path) -> None:
        await plugin_manager.initialize()
        assert plugin_manager.changed_plugins() == {"mytest": False}
        (tmp_path / "mytest" / "plugin.py").write_text(PLUGIN_BODY_V2)
        assert plugin_manager.changed_plugins() == {"mytest": True}

    async def test_reload_changed_reloads_then_idempotent(self, plugin_manager, tmp_path) -> None:
        await plugin_manager.initialize()
        (tmp_path / "mytest" / "plugin.py").write_text(PLUGIN_BODY_V2)
        before = plugin_manager.get_plugin("mytest").loaded_at
        results = await plugin_manager.reload_changed()
        assert results == {"mytest": True}
        after = plugin_manager.get_plugin("mytest").loaded_at
        assert after >= before
        # checksum refreshed -> a second reload_changed is a no-op
        assert await plugin_manager.reload_changed() == {}
