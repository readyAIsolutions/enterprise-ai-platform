"""
Tests for the ENI Enterprise Platform Kernel.

Covers:
  - Singleton pattern
  - Module registration via @module decorator
  - Event pub/sub
  - Health checks
  - Lifecycle transitions
  - ModuleRegistry discovery
  - MetricsCollector
  - LoggingBridge
  - ConfigurationLoader
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

from platform_kernel import (
    ConfigurationLoader,
    Event,
    EventBus,
    EventPriority,
    HealthChecker,
    HealthReport,
    HealthStatus,
    LifecycleState,
    LoggingBridge,
    MetricPoint,
    MetricsCollector,
    Module,
    ModuleRecord,
    ModuleRegistry,
    PlatformOS,
    Subscription,
    create_platform,
    module,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_platform_singleton():
    """Ensure each test starts with a clean PlatformOS singleton."""
    PlatformOS.reset_instance()
    yield
    PlatformOS.reset_instance()


@pytest.fixture
def event_bus():
    """Create a fresh EventBus for each test."""
    return EventBus()


@pytest.fixture
def metrics_collector():
    """Create a fresh MetricsCollector for each test."""
    return MetricsCollector()


@pytest.fixture
def temp_config_file(tmp_path):
    """Create a temporary config YAML file."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("""
platform:
  name: "Test Platform"
  version: "0.0.0"
  environment: "testing"

modules:
  test_module_a:
    enabled: true
    priority: 1
    required: true
    config:
      key: "value_a"
  test_module_b:
    enabled: true
    priority: 2
    required: false
    config:
      key: "value_b"

logging:
  level: "DEBUG"
  outputs:
    - type: "console"
      level: "DEBUG"

health:
  failure_threshold: 2
  recovery_threshold: 1
  timeout_sec: 5

event_bus:
  async_dispatch: false
""")
    return config_path


@pytest.fixture
def temp_modules_path(tmp_path):
    """Create a temporary modules directory with mock __init__.py files."""
    modules_dir = tmp_path / "modules"
    modules_dir.mkdir()

    for mod_name in ("test_a", "test_b", "test_c"):
        mod_dir = modules_dir / mod_name
        mod_dir.mkdir()
        init = mod_dir / "__init__.py"
        init.write_text(f'__version__ = "1.0.0"\n')

    return modules_dir


# =============================================================================
# Tests — Singleton Pattern
# =============================================================================


class TestSingletonPattern:
    """Verify PlatformOS singleton behavior."""

    def test_instance_returns_same_object(self):
        """PlatformOS.instance() should return the same object each time."""
        p1 = PlatformOS.instance()
        p2 = PlatformOS.instance()
        assert p1 is p2
        assert p1.platform_id == p2.platform_id

    def test_direct_construction_raises(self):
        """Direct construction of PlatformOS should raise RuntimeError."""
        with pytest.raises(RuntimeError, match="Use PlatformOS.instance()"):
            PlatformOS()

    def test_reset_instance_clears_singleton(self):
        """reset_instance() should clear the singleton."""
        p1 = PlatformOS.instance()
        PlatformOS.reset_instance()
        p2 = PlatformOS.instance()
        assert p1 is not p2
        assert p1.platform_id != p2.platform_id

    def test_singleton_thread_safety(self):
        """Multiple threads calling instance() should all get the same object."""
        instances: list = []

        def get_instance():
            instances.append(PlatformOS.instance())

        threads = [threading.Thread(target=get_instance) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        first = instances[0]
        for inst in instances:
            assert inst is first


# =============================================================================
# Tests — Module Decorator & Registration
# =============================================================================


class TestModuleDecorator:
    """Verify the @module decorator and module registration."""

    def test_decorator_registers_module(self):
        """The @module decorator should register the class."""

        @module(name="test_decorator_mod", version="2.0.0")
        class TestMod(Module):
            async def initialize(self) -> None:
                pass

            async def health_check(self) -> HealthStatus:
                return HealthStatus.HEALTHY

            async def shutdown(self) -> None:
                pass

        from platform_kernel import _MODULE_REGISTRY

        assert "test_decorator_mod" in _MODULE_REGISTRY
        assert _MODULE_REGISTRY["test_decorator_mod"] is TestMod
        assert TestMod._meta_name == "test_decorator_mod"
        assert TestMod._meta_version == "2.0.0"

    def test_decorator_defaults_name(self):
        """If no name is given, the class name is used."""

        @module()
        class DefaultNameModule(Module):
            async def initialize(self) -> None:
                pass

            async def health_check(self) -> HealthStatus:
                return HealthStatus.HEALTHY

            async def shutdown(self) -> None:
                pass

        assert DefaultNameModule._meta_name == "DefaultNameModule"

    def test_module_instance_properties(self):
        """Module instances should expose name, version, status, module_id."""

        @module(name="prop_test", version="1.2.3")
        class PropModule(Module):
            async def initialize(self) -> None:
                pass

            async def health_check(self) -> HealthStatus:
                return HealthStatus.HEALTHY

            async def shutdown(self) -> None:
                pass

        inst = PropModule()
        assert inst.name == "prop_test"
        assert inst.version == "1.2.3"
        assert inst.status == HealthStatus.UNKNOWN
        assert len(inst.module_id) == 36  # UUID4

    def test_module_config_passed_through(self):
        """Module should receive config via constructor."""

        @module(name="cfg_test")
        class CfgModule(Module):
            async def initialize(self) -> None:
                pass

            async def health_check(self) -> HealthStatus:
                return HealthStatus.HEALTHY

            async def shutdown(self) -> None:
                pass

        inst = CfgModule(config={"key": "val"})
        assert inst.config == {"key": "val"}


# =============================================================================
# Tests — ModuleRegistry
# =============================================================================


class TestModuleRegistry:
    """Verify ModuleRegistry discovery and lifecycle."""

    def test_discover_finds_modules(self, temp_modules_path):
        """ModuleRegistry.discover() should find all modules."""
        registry = ModuleRegistry(modules_path=temp_modules_path, config={})
        discovered = registry.discover()

        assert "test_a" in discovered
        assert "test_b" in discovered
        assert "test_c" in discovered
        assert len(discovered) == 3

    def test_discover_reads_version(self, temp_modules_path):
        """ModuleRegistry should read __version__ from __init__.py."""
        registry = ModuleRegistry(modules_path=temp_modules_path, config={})
        registry.discover()

        record = registry.get_record("test_a")
        assert record is not None
        assert record.version == "1.0.0"

    def test_discover_defaults_when_missing(self, tmp_path):
        """ModuleRegistry should not crash if modules path doesn't exist."""
        bad_path = tmp_path / "nonexistent"
        registry = ModuleRegistry(modules_path=bad_path)
        discovered = registry.discover()
        assert discovered == []

    def test_list_modules_returns_records(self, temp_modules_path):
        """list_modules() should return all ModuleRecords."""
        registry = ModuleRegistry(modules_path=temp_modules_path, config={})
        registry.discover()
        records = registry.list_modules()
        assert len(records) == 3
        assert all(isinstance(r, ModuleRecord) for r in records)

    def test_get_record_returns_none_for_unknown(self, temp_modules_path):
        """get_record() should return None for unknown modules."""
        registry = ModuleRegistry(modules_path=temp_modules_path, config={})
        registry.discover()
        assert registry.get_record("nonexistent") is None

    def test_initialize_all_with_decorated_modules(self, temp_modules_path):
        """initialize_all() should create instances for @module-decorated classes."""

        @module(name="test_a", version="1.0.0")
        class TestAModule(Module):
            async def initialize(self) -> None:
                self.status = HealthStatus.HEALTHY

            async def health_check(self) -> HealthStatus:
                return HealthStatus.HEALTHY

            async def shutdown(self) -> None:
                pass

        @module(name="test_b", version="1.0.0")
        class TestBModule(Module):
            async def initialize(self) -> None:
                self.status = HealthStatus.HEALTHY

            async def health_check(self) -> HealthStatus:
                return HealthStatus.HEALTHY

            async def shutdown(self) -> None:
                pass

        registry = ModuleRegistry(modules_path=temp_modules_path, config={})
        registry.discover()

        async def _run():
            results = await registry.initialize_all()
            assert results["test_a"] == HealthStatus.HEALTHY
            assert results["test_b"] == HealthStatus.HEALTHY
            inst_a = registry.get_instance("test_a")
            assert inst_a is not None
            assert inst_a.status == HealthStatus.HEALTHY

        asyncio.run(_run())

    def test_shutdown_all_calls_shutdown(self, temp_modules_path):
        """shutdown_all() should call shutdown() on each instance."""
        shutdown_calls = []

        @module(name="test_a", version="1.0.0")
        class ShutdownModule(Module):
            async def initialize(self) -> None:
                pass

            async def health_check(self) -> HealthStatus:
                return HealthStatus.HEALTHY

            async def shutdown(self) -> None:
                shutdown_calls.append("test_a")

        registry = ModuleRegistry(modules_path=temp_modules_path, config={})
        registry.discover()

        async def _run():
            await registry.initialize_all()
            results = await registry.shutdown_all()
            assert "test_a" in shutdown_calls
            assert results.get("test_a") is True

        asyncio.run(_run())

    def test_config_enabled_flag_works(self, temp_modules_path):
        """Modules with enabled=false should not be initialized."""
        config = {
            "modules": {
                "test_a": {"enabled": False},
            }
        }
        registry = ModuleRegistry(modules_path=temp_modules_path, config=config)
        registry.discover()
        record = registry.get_record("test_a")
        assert record is not None
        assert record.enabled is False

    def test_config_required_flag_works(self, temp_modules_path):
        """Required flag should be read from config."""
        config = {
            "modules": {
                "test_a": {"required": True},
            }
        }
        registry = ModuleRegistry(modules_path=temp_modules_path, config=config)
        registry.discover()
        record = registry.get_record("test_a")
        assert record is not None
        assert record.required is True


# =============================================================================
# Tests — EventBus
# =============================================================================


class TestEventBus:
    """Verify EventBus pub/sub functionality."""

    def test_subscribe_and_publish(self, event_bus):
        """Subscribers should receive published events."""
        received: list = []

        @event_bus.subscribe("test.topic")
        def handler(event: Event) -> None:
            received.append(event)

        evt = Event.create("test.topic", "test_source", {"data": 42})
        event_bus.publish(evt)

        assert len(received) == 1
        assert received[0].payload["data"] == 42

    def test_unsubscribe_removes_handler(self, event_bus):
        """After unsubscribe, handler should not receive events."""
        received: list = []

        @event_bus.subscribe("test.topic")
        def handler(event: Event) -> None:
            received.append(event)

        # Get subscription ID from internal state
        sub_id = next(
            s.id for s in event_bus._subscriptions.get("test.topic", [])
        )
        event_bus.unsubscribe(sub_id)

        event_bus.publish(Event.create("test.topic", "s", {}))
        assert len(received) == 0

    def test_wildcard_subscription(self, event_bus):
        """Wildcard '*' should match all topics."""
        event_bus._async_dispatch = False
        received: list = []

        @event_bus.subscribe("*")
        def handler(event: Event) -> None:
            received.append(event)

        event_bus.publish(Event.create("foo.bar", "s", {}))
        event_bus.publish(Event.create("baz.qux", "s", {}))
        assert len(received) == 2

    def test_once_subscription(self, event_bus):
        """Once subscriptions should auto-unsubscribe after first delivery."""
        received: list = []

        @event_bus.subscribe("test.once", once=True)
        def handler(event: Event) -> None:
            received.append(event)

        event_bus.publish(Event.create("test.once", "s", {}))
        event_bus.publish(Event.create("test.once", "s", {}))
        assert len(received) == 1

    def test_priority_filter(self, event_bus):
        """Priority filter should only deliver events at or above threshold."""
        received: list = []

        @event_bus.subscribe("test.prio", priority_filter=EventPriority.HIGH)
        def handler(event: Event) -> None:
            received.append(event)

        # LOW should not be delivered
        event_bus.publish(
            Event.create("test.prio", "s", {}, priority=EventPriority.LOW)
        )
        assert len(received) == 0

        # HIGH should be delivered
        event_bus.publish(
            Event.create("test.prio", "s", {}, priority=EventPriority.HIGH)
        )
        assert len(received) == 1

    def test_event_history(self, event_bus):
        """EventBus should maintain event history."""
        for i in range(5):
            event_bus.publish(Event.create("test.history", "s", {"i": i}))
        history = event_bus.get_history()
        assert len(history) == 5

    def test_history_topic_filter(self, event_bus):
        """get_history() should filter by topic."""
        event_bus.publish(Event.create("topic.a", "s", {}))
        event_bus.publish(Event.create("topic.b", "s", {}))

        history_a = event_bus.get_history(topic="topic.a")
        assert len(history_a) == 1
        assert history_a[0].topic == "topic.a"

    def test_get_stats(self, event_bus):
        """get_stats() should return meaningful statistics."""
        event_bus._async_dispatch = False
        event_bus.publish(Event.create("test.stats", "s", {}))
        stats = event_bus.get_stats()
        assert stats["total_published"] >= 1
        assert "active_subscriptions" in stats
        assert "uptime_seconds" in stats

    def test_event_properties(self):
        """Event.create() should set all properties correctly."""
        evt = Event.create(
            "test.prop",
            "source_mod",
            {"key": "val"},
            correlation_id="corr-123",
            metadata={"trace": "abc"},
        )
        assert evt.topic == "test.prop"
        assert evt.source == "source_mod"
        assert evt.payload == {"key": "val"}
        assert evt.correlation_id == "corr-123"
        assert evt.metadata == {"trace": "abc"}
        assert len(evt.event_id) == 36
        assert isinstance(evt.timestamp, datetime)

    def test_shutdown_stops_executor(self, event_bus):
        """shutdown() should stop the thread pool."""
        event_bus.shutdown()
        assert event_bus._executor is None


# =============================================================================
# Tests — Health Check System
# =============================================================================


class TestHealthChecker:
    """Verify HealthChecker functionality."""

    @pytest.fixture
    def mock_registry(self):
        """Create a mock ModuleRegistry with test modules."""
        registry = MagicMock(spec=ModuleRegistry)

        @module(name="healthy_mod", version="1.0.0")
        class HealthyMod(Module):
            async def initialize(self) -> None:
                pass

            async def health_check(self) -> HealthStatus:
                return HealthStatus.HEALTHY

            async def shutdown(self) -> None:
                pass

        @module(name="unhealthy_mod", version="1.0.0")
        class UnhealthyMod(Module):
            async def initialize(self) -> None:
                pass

            async def health_check(self) -> HealthStatus:
                return HealthStatus.UNHEALTHY

            async def shutdown(self) -> None:
                pass

        healthy_rec = ModuleRecord(
            name="healthy_mod",
            path=Path("/fake/healthy_mod"),
            version="1.0.0",
            instance=HealthyMod(),
        )
        unhealthy_rec = ModuleRecord(
            name="unhealthy_mod",
            path=Path("/fake/unhealthy_mod"),
            version="1.0.0",
            instance=UnhealthyMod(),
        )

        registry.list_modules.return_value = [healthy_rec, unhealthy_rec]
        registry.get_instance = lambda name: {
            "healthy_mod": healthy_rec.instance,
            "unhealthy_mod": unhealthy_rec.instance,
        }.get(name)
        return registry

    def test_run_all_checks(self, mock_registry):
        """run_all_checks() should check all modules and return reports."""
        checker = HealthChecker(mock_registry)
        reports = asyncio.run(checker.run_all_checks())

        # Should have 2 module reports + 1 platform aggregate = 3
        assert len(reports) == 3

        healthy_report = next(r for r in reports if r.module_name == "healthy_mod")
        assert healthy_report.status == HealthStatus.HEALTHY

        unhealthy_report = next(
            r for r in reports if r.module_name == "unhealthy_mod"
        )
        assert unhealthy_report.status == HealthStatus.UNHEALTHY

        platform_report = next(r for r in reports if r.module_name == "platform")
        assert platform_report.status == HealthStatus.DEGRADED

    def test_consecutive_failure_tracking(self, mock_registry):
        """HealthChecker should track consecutive failures."""
        checker = HealthChecker(mock_registry, config={"failure_threshold": 3})
        # Run checks 3 times
        for _ in range(3):
            asyncio.run(checker.run_all_checks())

        assert checker.get_failure_count("unhealthy_mod") == 3
        assert checker.get_failure_count("healthy_mod") == 0
        assert checker.is_degraded("unhealthy_mod") is True
        assert checker.is_degraded("healthy_mod") is False

    def test_get_latest_report(self, mock_registry):
        """get_latest_report() should return the most recent report."""
        checker = HealthChecker(mock_registry)
        asyncio.run(checker.run_all_checks())

        report = checker.get_latest_report("healthy_mod")
        assert report is not None
        assert report.module_name == "healthy_mod"
        assert report.status == HealthStatus.HEALTHY

    def test_health_report_serialization(self, mock_registry):
        """HealthReport.to_dict() should serialize correctly."""
        checker = HealthChecker(mock_registry)
        reports = asyncio.run(checker.run_all_checks())
        report = reports[0]
        d = report.to_dict()
        assert d["module_name"] == report.module_name
        assert d["status"] == report.status.value
        assert isinstance(d["response_time_ms"], float)
        assert "timestamp" in d


# =============================================================================
# Tests — Metrics Collector
# =============================================================================


class TestMetricsCollector:
    """Verify MetricsCollector functionality."""

    def test_increment_counter(self, metrics_collector):
        """increment() should increase counter values."""
        metrics_collector.increment("requests", value=1, module="api")
        metrics_collector.increment("requests", value=2, module="api")
        assert metrics_collector.get_counter("requests") == 3.0

    def test_increment_with_tags(self, metrics_collector):
        """increment() should respect tag partitioning."""
        metrics_collector.increment("requests", tags={"method": "GET"})
        metrics_collector.increment("requests", tags={"method": "POST"})
        assert metrics_collector.get_counter("requests", tags={"method": "GET"}) == 1.0
        assert metrics_collector.get_counter("requests", tags={"method": "POST"}) == 1.0

    def test_set_gauge(self, metrics_collector):
        """set_gauge() should set a gauge value."""
        metrics_collector.set_gauge("memory_bytes", 1024)
        assert metrics_collector.get_gauge("memory_bytes") == 1024

        metrics_collector.set_gauge("memory_bytes", 2048)
        assert metrics_collector.get_gauge("memory_bytes") == 2048

    def test_observe_histogram(self, metrics_collector):
        """observe() should record histogram values and compute stats."""
        metrics_collector.observe("latency", 10.0)
        metrics_collector.observe("latency", 20.0)
        metrics_collector.observe("latency", 30.0)

        stats = metrics_collector.get_histogram_stats("latency")
        assert stats["count"] == 3
        assert stats["sum"] == 60.0
        assert stats["min"] == 10.0
        assert stats["max"] == 30.0
        assert stats["avg"] == 20.0

    def test_snapshot(self, metrics_collector):
        """snapshot() should return a full metrics snapshot."""
        metrics_collector.increment("counter_a", 5)
        metrics_collector.set_gauge("gauge_a", 42)
        metrics_collector.observe("hist_a", 100)

        snap = metrics_collector.snapshot()
        assert "counters" in snap
        assert "gauges" in snap
        assert "histograms" in snap
        assert "history_count" in snap

    def test_get_recent(self, metrics_collector):
        """get_recent() should filter by name and limit."""
        for i in range(10):
            metrics_collector.increment("metric_x", i)
        for i in range(5):
            metrics_collector.increment("metric_y", i)

        recent_x = metrics_collector.get_recent(name="metric_x", limit=5)
        assert len(recent_x) == 5
        assert all(p.name == "metric_x" for p in recent_x)

    def test_reset(self, metrics_collector):
        """reset() should clear all metrics."""
        metrics_collector.increment("counter", 100)
        metrics_collector.set_gauge("gauge", 1.0)
        metrics_collector.reset()

        assert metrics_collector.get_counter("counter") == 0.0
        assert metrics_collector.get_gauge("gauge") == 0.0
        assert metrics_collector.snapshot()["history_count"] == 0

    def test_disabled_metrics(self):
        """When disabled, metrics operations should be no-ops."""
        mc = MetricsCollector(config={"enabled": False})
        mc.increment("test", 1)
        mc.set_gauge("test", 1)
        mc.observe("test", 1)
        assert mc.get_counter("test") == 0.0
        assert mc.get_gauge("test") == 0.0
        assert mc.get_histogram_stats("test")["count"] == 0


# =============================================================================
# Tests — Logging Bridge
# =============================================================================


class TestLoggingBridge:
    """Verify LoggingBridge functionality."""

    def test_get_logger_returns_adapter(self):
        """get_logger() should return a LoggerAdapter."""
        bridge = LoggingBridge()
        logger = bridge.get_logger("test_mod")
        assert logger is not None

    def test_get_logger_includes_correlation_id(self):
        """Logger extra should include correlation_id."""
        bridge = LoggingBridge()
        logger = bridge.get_logger("test_mod", correlation_id="corr-123")
        assert logger.extra.get("module_correlation") == "corr-123"

    def test_set_level(self):
        """set_level() should change the log level."""
        bridge = LoggingBridge()
        bridge.set_level("WARNING")
        assert bridge.level == "WARNING"

        bridge.set_level("DEBUG")
        assert bridge.level == "DEBUG"

    def test_bridge_module_logger(self):
        """bridge_module_logger() should return a logger in the eni.modules tree."""
        bridge = LoggingBridge()
        logger = bridge.bridge_module_logger("test_mod")
        assert logger.name == "eni.modules.test_mod"


# =============================================================================
# Tests — Configuration Loader
# =============================================================================


class TestConfigurationLoader:
    """Verify ConfigurationLoader functionality."""

    def test_load_from_file(self, temp_config_file):
        """Load should read from a YAML config file."""
        loader = ConfigurationLoader(temp_config_file)
        config = loader.load()
        assert config["platform"]["name"] == "Test Platform"
        assert config["platform"]["environment"] == "testing"

    def test_load_returns_defaults_when_file_missing(self, tmp_path):
        """Load should return defaults when config file doesn't exist."""
        loader = ConfigurationLoader(tmp_path / "nonexistent.yaml")
        config = loader.load()
        assert "platform" in config
        assert "modules" in config
        assert "logging" in config
        assert "health" in config

    def test_get_dot_notation(self, temp_config_file):
        """get() should support dot notation for nested keys."""
        loader = ConfigurationLoader(temp_config_file)
        assert loader.get("platform.name") == "Test Platform"
        assert loader.get("platform.environment") == "testing"
        assert loader.get("modules.test_module_a.enabled") is True
        assert loader.get("nonexistent.key", "default") == "default"

    def test_reload(self, temp_config_file):
        """reload() should re-read the config file."""
        loader = ConfigurationLoader(temp_config_file)
        config1 = loader.load()

        # Reload (same file, but verifies reload works)
        config2 = loader.reload()
        assert config2["platform"]["name"] == config1["platform"]["name"]

    def test_env_overrides(self, temp_config_file, monkeypatch):
        """Environment variables should override config values."""
        monkeypatch.setenv("ENI_ENV", "staging")
        monkeypatch.setenv("ENI_LOG_LEVEL", "WARNING")

        loader = ConfigurationLoader(temp_config_file)
        config = loader.load()
        assert config["platform"]["environment"] == "staging"
        assert config["logging"]["level"] == "WARNING"


# =============================================================================
# Tests — Lifecycle Transitions
# =============================================================================


class TestLifecycleState:
    """Verify LifecycleState enum transitions."""

    def test_valid_transitions(self):
        """Valid transitions should be allowed."""
        assert LifecycleState.UNINITIALIZED.can_transition_to(LifecycleState.INITIALIZING)
        assert LifecycleState.INITIALIZING.can_transition_to(LifecycleState.DISCOVERING)
        assert LifecycleState.DISCOVERING.can_transition_to(LifecycleState.CONFIGURING)
        assert LifecycleState.CONFIGURING.can_transition_to(LifecycleState.STARTING)
        assert LifecycleState.STARTING.can_transition_to(LifecycleState.RUNNING)
        assert LifecycleState.RUNNING.can_transition_to(LifecycleState.DEGRADED)
        assert LifecycleState.DEGRADED.can_transition_to(LifecycleState.RUNNING)
        assert LifecycleState.DEGRADED.can_transition_to(LifecycleState.RECOVERING)

    def test_invalid_transitions(self):
        """Invalid transitions should be rejected."""
        assert not LifecycleState.STOPPED.can_transition_to(LifecycleState.RUNNING)
        assert not LifecycleState.RUNNING.can_transition_to(LifecycleState.UNINITIALIZED)
        assert not LifecycleState.UNINITIALIZED.can_transition_to(LifecycleState.RUNNING)

    def test_terminal_state_has_no_exits(self):
        """STOPPED should have no valid transitions."""
        assert not LifecycleState.STOPPED.can_transition_to(LifecycleState.RUNNING)
        assert not LifecycleState.STOPPED.can_transition_to(LifecycleState.UNINITIALIZED)
        assert not LifecycleState.STOPPED.can_transition_to(LifecycleState.CRASHED)

    def test_crash_recovery_path(self):
        """CRASHED -> RECOVERING -> RUNNING should be valid."""
        assert LifecycleState.CRASHED.can_transition_to(LifecycleState.RECOVERING)
        assert LifecycleState.RECOVERING.can_transition_to(LifecycleState.RUNNING)
        assert LifecycleState.RECOVERING.can_transition_to(LifecycleState.DEGRADED)


# =============================================================================
# Tests — PlatformOS Lifecycle
# =============================================================================


class TestPlatformOSLifecycle:
    """Verify PlatformOS lifecycle management."""

    def test_initial_state(self, reset_platform_singleton):
        """Platform starts in UNINITIALIZED state."""
        p = PlatformOS.instance()
        assert p.state == LifecycleState.UNINITIALIZED

    def test_initialize_transitions(self, reset_platform_singleton, temp_modules_path):
        """initialize() should transition through states."""
        p = PlatformOS.instance()
        p.initialize(modules_path=temp_modules_path)

        # Should end in CONFIGURING state after initialize
        assert p.state == LifecycleState.CONFIGURING
        assert p.module_registry is not None
        assert p.event_bus is not None
        assert p.health_checker is not None
        assert p.metrics is not None
        assert p.logging is not None

    def test_initialize_and_start(self, reset_platform_singleton, temp_modules_path):
        """Full initialize + start should reach RUNNING state."""

        @module(name="test_a", version="1.0.0")
        class TestModule(Module):
            async def initialize(self) -> None:
                pass

            async def health_check(self) -> HealthStatus:
                return HealthStatus.HEALTHY

            async def shutdown(self) -> None:
                pass

        p = PlatformOS.instance()
        p.initialize(modules_path=temp_modules_path)

        async def _run():
            await p.start()
            assert p.state == LifecycleState.RUNNING

        asyncio.run(_run())

    def test_start_fails_without_initialize(self, reset_platform_singleton):
        """start() should raise if initialize() wasn't called."""
        p = PlatformOS.instance()

        async def _run():
            with pytest.raises(RuntimeError, match="Cannot start"):
                await p.start()

        asyncio.run(_run())

    def test_shutdown_transitions_to_stopped(self, reset_platform_singleton, temp_modules_path):
        """shutdown() should transition to STOPPED."""

        @module(name="test_a", version="1.0.0")
        class TestModule(Module):
            async def initialize(self) -> None:
                pass

            async def health_check(self) -> HealthStatus:
                return HealthStatus.HEALTHY

            async def shutdown(self) -> None:
                pass

        p = PlatformOS.instance()
        p.initialize(modules_path=temp_modules_path)

        async def _run():
            await p.start()
            assert p.state == LifecycleState.RUNNING
            await p.shutdown()
            assert p.state == LifecycleState.STOPPED

        asyncio.run(_run())

    def test_status_report(self, reset_platform_singleton, temp_modules_path):
        """status_report() should return comprehensive platform state."""
        p = PlatformOS.instance()
        p.initialize(modules_path=temp_modules_path)

        report = p.status_report()
        assert report["platform_id"] == p.platform_id
        assert "state" in report
        assert "modules" in report
        assert "events" in report
        assert "metrics" in report

    def test_state_history(self, reset_platform_singleton, temp_modules_path):
        """state_history should record all transitions."""

        @module(name="test_a", version="1.0.0")
        class TestModule(Module):
            async def initialize(self) -> None:
                pass

            async def health_check(self) -> HealthStatus:
                return HealthStatus.HEALTHY

            async def shutdown(self) -> None:
                pass

        p = PlatformOS.instance()
        p.initialize(modules_path=temp_modules_path)

        async def _run():
            await p.start()
            await p.shutdown()

        asyncio.run(_run())

        history = p.state_history
        assert len(history) >= 4  # INITIALIZING, DISCOVERING, CONFIGURING, STARTING, RUNNING, STOPPING, STOPPED
        assert history[0][0] == LifecycleState.INITIALIZING
        assert history[-1][0] == LifecycleState.STOPPED


# =============================================================================
# Tests — HealthStatus Enum
# =============================================================================


class TestHealthStatus:
    """Verify HealthStatus enum helpers."""

    def test_is_operational(self):
        assert HealthStatus.HEALTHY.is_operational()
        assert HealthStatus.DEGRADED.is_operational()
        assert not HealthStatus.UNHEALTHY.is_operational()
        assert not HealthStatus.UNKNOWN.is_operational()

    def test_is_terminal(self):
        assert HealthStatus.UNHEALTHY.is_terminal()
        assert HealthStatus.UNKNOWN.is_terminal()
        assert not HealthStatus.HEALTHY.is_terminal()


# =============================================================================
# Tests — create_platform convenience
# =============================================================================


class TestCreatePlatform:
    """Verify create_platform convenience function."""

    def test_create_platform_returns_initialized_instance(self, temp_modules_path):
        """create_platform() should return an initialized PlatformOS."""
        p = create_platform(modules_path=temp_modules_path)
        assert isinstance(p, PlatformOS)
        assert p.state == LifecycleState.CONFIGURING
        assert p.module_registry is not None


# =============================================================================
# Integration Test — Full Platform Lifecycle
# =============================================================================


class TestPlatformIntegration:
    """End-to-end integration test of the platform kernel."""

    def test_full_lifecycle(self, tmp_path):
        """Test the full platform lifecycle with decorated modules."""
        # Create temp modules structure
        modules_dir = tmp_path / "modules"
        modules_dir.mkdir()
        for mod_name in ("integration_a", "integration_b"):
            mod_dir = modules_dir / mod_name
            mod_dir.mkdir()
            (mod_dir / "__init__.py").write_text(f'__version__ = "1.0.0"\n')

        # Create config
        config_dir = tmp_path / "config.yaml"
        config_dir.write_text("""
platform:
  name: "Integration Test"
modules:
  integration_a:
    enabled: true
    priority: 1
    required: true
  integration_b:
    enabled: true
    priority: 2
    required: false
logging:
  level: "WARNING"
event_bus:
  async_dispatch: false
health:
  failure_threshold: 3
  timeout_sec: 5
""")

        events_received: list = []

        @module(name="integration_a", version="1.0.0")
        class IntegrationAModule(Module):
            async def initialize(self) -> None:
                self.status = HealthStatus.HEALTHY

            async def health_check(self) -> HealthStatus:
                return HealthStatus.HEALTHY

            async def shutdown(self) -> None:
                pass

        @module(name="integration_b", version="1.0.0")
        class IntegrationBModule(Module):
            async def initialize(self) -> None:
                self.status = HealthStatus.HEALTHY

            async def health_check(self) -> HealthStatus:
                return HealthStatus.HEALTHY

            async def shutdown(self) -> None:
                pass

        async def _run():
            p = PlatformOS.instance()
            p.initialize(config_path=config_dir, modules_path=modules_dir)

            # Subscribe to events
            if p.event_bus:

                @p.event_bus.subscribe("platform.*")
                def handler(event: Event) -> None:
                    events_received.append(event.topic)

            # Start
            await p.start()
            assert p.state == LifecycleState.RUNNING

            # Verify modules initialized
            assert p.module_registry is not None
            inst_a = p.module_registry.get_instance("integration_a")
            assert inst_a is not None
            assert inst_a.status == HealthStatus.HEALTHY

            # Run health check
            reports = await p.run_health_check()
            platform_report = next(
                r for r in reports if r.module_name == "platform"
            )
            assert platform_report.status == HealthStatus.HEALTHY

            # Verify event bus
            assert any("platform.state_change" in t or "platform.started" in t for t in events_received)

            # Metrics
            if p.metrics:
                p.metrics.increment("test.metric", 1, module="integration")
                assert p.metrics.get_counter("test.metric") == 1.0

            # Status report
            report = p.status_report()
            assert report["state"] == "running"
            assert report["modules"]["total_discovered"] == 2
            assert report["modules"]["initialized"] == 2

            # Shutdown
            await p.shutdown()
            assert p.state == LifecycleState.STOPPED

        asyncio.run(_run())

    def test_degraded_startup(self, tmp_path):
        """Platform should start DEGRADED if a required module fails."""
        modules_dir = tmp_path / "modules"
        modules_dir.mkdir()
        mod_dir = modules_dir / "failing_mod"
        mod_dir.mkdir()
        (mod_dir / "__init__.py").write_text('__version__ = "1.0.0"\n')

        @module(name="failing_mod", version="1.0.0")
        class FailingModule(Module):
            async def initialize(self) -> None:
                raise RuntimeError("Intentional init failure")

            async def health_check(self) -> HealthStatus:
                return HealthStatus.UNHEALTHY

            async def shutdown(self) -> None:
                pass

        async def _run():
            p = PlatformOS.instance()
            config = {
                "modules": {
                    "failing_mod": {"enabled": True, "required": True},
                },
                "logging": {"level": "CRITICAL"},
            }
            p._config = config  # Bypass config loading for test
            p._config_loader = MagicMock()
            p._logging_bridge = LoggingBridge()
            p._event_bus = EventBus({"async_dispatch": False})
            p._metrics_collector = MetricsCollector()
            p._state = LifecycleState.CONFIGURING
            p._module_registry = ModuleRegistry(
                modules_path=modules_dir, config=config
            )
            p._module_registry.discover()
            p._health_checker = HealthChecker(
                registry=p._module_registry,
                event_bus=p._event_bus,
                config={},
            )

            await p.start()
            assert p.state == LifecycleState.DEGRADED

        asyncio.run(_run())