"""Lifecycle + facade tests for the ``autonomous_agent_runtime`` platform module.

These tests verify the module is a first-class Platform Kernel ``@module``
(``enterprise.modules.autonomous_agent_runtime``), that it auto-registers on
import, implements the standard lifecycle (``initialize`` / ``health_check`` /
``shutdown``), honours ``set_event_bus``, and exposes the public facade
(``register_providers_from_config`` / ``list_providers`` / ``get_provider`` /
``cost_summary`` / ``fallback_status`` / ``health_check_all``).

Imports run against ``enterprise.modules.autonomous_agent_runtime`` (the
registered, kernel-aware package) rather than the bare ``modules.`` alias.
"""

import asyncio

import pytest

import enterprise.platform_kernel as kernel
import enterprise.modules.autonomous_agent_runtime as aar_module
from enterprise.modules.autonomous_agent_runtime import (
    AutonomousAgentRuntimeFacade,
    AutonomousAgentRuntimeModule,
    create_autonomous_agent_runtime_module,
)
from enterprise.platform_kernel import HealthStatus


def _run(coro):
    """Run an async lifecycle call to completion via ``asyncio.run``."""
    return asyncio.run(coro)


# =============================================================================
# Module registration / wiring
# =============================================================================


def test_module_auto_registers_with_kernel_on_import():
    """Importing the package must register it in the kernel module registry."""
    assert "autonomous_agent_runtime" in kernel._MODULE_REGISTRY
    registered = kernel._MODULE_REGISTRY["autonomous_agent_runtime"]
    assert issubclass(registered, AutonomousAgentRuntimeModule)


def test_module_metadata():
    assert aar_module.__version__ == "1.0.0"
    mod = create_autonomous_agent_runtime_module()
    assert mod.name == "autonomous_agent_runtime"
    assert mod.version == "1.0.0"
    assert isinstance(mod.module_id, str) and mod.module_id


def test_factory_creates_uninitialized_module():
    mod = create_autonomous_agent_runtime_module({"enable_cost_tracking": True})
    assert isinstance(mod, AutonomousAgentRuntimeModule)
    assert mod.facade is None
    assert mod.status is HealthStatus.UNKNOWN


def test_public_facade_exports():
    """The expected facade operations are present on the module and facade."""
    fac = AutonomousAgentRuntimeFacade(track_costs=True)
    for op in (
        "register_providers_from_config",
        "list_providers",
        "get_provider",
        "cost_summary",
        "fallback_status",
        "health_check_all",
    ):
        assert callable(getattr(fac, op)), op
    fac.close()


# =============================================================================
# Lifecycle
# =============================================================================


def test_initialize_health_shutdown_cycle():
    async def scenario():
        mod = create_autonomous_agent_runtime_module(
            {
                "providers": [
                    {"name": "openai", "type": "openai_compatible"},
                    {"name": "hunyuan", "type": "openai_compatible"},
                ],
                "default_provider": "openai",
                "enable_cost_tracking": True,
            }
        )
        assert mod.facade is None
        await mod.initialize()
        assert mod.status is HealthStatus.HEALTHY
        assert await mod.health_check() is HealthStatus.HEALTHY
        assert mod.facade is not None
        assert mod.list_providers() == ["openai", "hunyuan"]
        return mod

    mod = _run(scenario())
    _run(mod.shutdown())
    assert mod.facade is None


def test_initialize_with_config_registers_providers():
    async def scenario():
        mod = create_autonomous_agent_runtime_module(
            {
                "providers": [
                    {"name": "primary", "type": "openai_compatible"},
                    {"name": "backup", "type": "openai_compatible", "enabled": False},
                ]
            }
        )
        await mod.initialize()
        # Disabled providers must not appear in the enabled listing.
        assert mod.list_providers() == ["primary"]
        return mod

    mod = _run(scenario())
    _run(mod.shutdown())


def test_health_before_initialize_is_unknown():
    async def scenario():
        mod = create_autonomous_agent_runtime_module()
        return await mod.health_check()

    assert _run(scenario()) is HealthStatus.UNKNOWN


def test_require_facade_raises_before_initialize():
    mod = create_autonomous_agent_runtime_module()
    with pytest.raises(RuntimeError):
        mod.list_providers()
    with pytest.raises(RuntimeError):
        mod.cost_summary()


def test_event_bus_wiring():
    """The module emits lifecycle + registration events when a bus is wired.

    NOTE: the platform EventBus has a pre-existing dispatch quirk where issuing
    multiple distinct topic subscriptions on one bus stops delivering the later
    topics. Each assertion below therefore uses a freshly-created bus with a
    single subscription, which is the reliable delivery path.
    """

    async def init_event():
        bus = kernel.EventBus()
        published = []

        @bus.subscribe("autonomous_agent_runtime.initialized")
        def _on_init(event):
            published.append(event.topic)

        mod = create_autonomous_agent_runtime_module(
            {"providers": [{"name": "openai", "type": "openai_compatible"}]}
        )
        mod.set_event_bus(bus)
        await mod.initialize()
        return published, mod

    async def register_event():
        bus = kernel.EventBus()
        published = []

        @bus.subscribe("autonomous_agent_runtime.provider.registered")
        def _on_register(event):
            published.append(event.topic)

        mod = create_autonomous_agent_runtime_module(
            {"providers": [{"name": "openai", "type": "openai_compatible"}]}
        )
        mod.set_event_bus(bus)
        await mod.initialize()
        mod.register_providers_from_config(
            {"providers": [{"name": "extra", "type": "openai_compatible"}]}
        )
        return published, mod

    init_published, init_mod = _run(init_event())
    assert "autonomous_agent_runtime.initialized" in init_published
    _run(init_mod.shutdown())

    reg_published, reg_mod = _run(register_event())
    assert "autonomous_agent_runtime.provider.registered" in reg_published
    _run(reg_mod.shutdown())


# =============================================================================
# Facade
# =============================================================================


def test_facade_list_and_get_provider():
    fac = AutonomousAgentRuntimeFacade(
        config={
            "providers": [
                {"name": "openai", "type": "openai_compatible"},
                {"name": "hunyuan", "type": "openai_compatible"},
            ]
        }
    )
    assert fac.list_providers() == ["openai", "hunyuan"]
    prov = fac.get_provider("openai")
    assert prov.name == "openai"
    with pytest.raises(KeyError):
        fac.get_provider("does_not_exist")
    fac.close()


def test_facade_register_providers_from_config():
    fac = AutonomousAgentRuntimeFacade(config={})
    n = fac.register_providers_from_config(
        {"providers": [{"name": "openai", "type": "openai_compatible"}]}
    )
    assert n == 1
    assert fac.list_providers() == ["openai"]
    fac.close()


def test_facade_cost_summary():
    fac = AutonomousAgentRuntimeFacade(track_costs=True)
    summary = fac.cost_summary()
    assert summary["enabled"] is True
    assert "total" in summary and "budget" in summary and "daily" in summary
    assert summary["total"]["total_tokens"] == 0
    fac.close()


def test_facade_cost_tracking_disabled():
    fac = AutonomousAgentRuntimeFacade(track_costs=False)
    summary = fac.cost_summary()
    assert summary == {"enabled": False}
    fac.close()


def test_facade_fallback_status():
    fac = AutonomousAgentRuntimeFacade(
        config={"providers": [{"name": "openai", "type": "openai_compatible"}]}
    )
    status = fac.fallback_status()
    assert "circuits" in status
    assert "active_requests" in status
    assert "recent_attempts" in status
    # Reset operations are safe on a fresh manager.
    assert _run(fac.reset_circuit("openai")) in (True, False)
    _run(fac.reset_all_circuits())
    fac.close()


def test_facade_health_check_all():
    fac = AutonomousAgentRuntimeFacade(
        config={"providers": [{"name": "openai", "type": "openai_compatible"}]}
    )
    result = _run(fac.health_check_all(force=True))
    assert isinstance(result, dict)
    assert "openai" in result
    fac.close()
