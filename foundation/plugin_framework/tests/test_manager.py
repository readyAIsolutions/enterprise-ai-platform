"""
Comprehensive unit tests for the PluginManager class.

Tests cover:
- Plugin registration and unregistration
- Lifecycle management (load, init, start, stop, unload)
- Dependency resolution and ordering
- Event hooks (subscribe, emit, unsubscribe)
- Capability execution
- Error handling and edge cases
"""

import unittest
from unittest.mock import MagicMock, patch, PropertyMock

from enterprise.foundation.plugin_framework.interface import (
    PluginBase,
    PluginCapability,
    PluginMetadata,
    PluginState,
    PluginVersion,
)
from enterprise.foundation.plugin_framework.registry import PluginRegistry
from enterprise.foundation.plugin_framework.security import PluginSecurity
from enterprise.foundation.plugin_framework.manager import (
    PluginManager,
    LoadResult,
    DependencyError,
    LifecycleError,
    PluginManagerError,
    LifecycleEvent,
)


# ---- Test Plugin Classes ----

class SimplePlugin(PluginBase):
    """A minimal plugin for testing."""

    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        return PluginMetadata(
            name="simple",
            version=PluginVersion(1, 0, 0),
            description="A simple test plugin",
        )

    def get_capabilities(self) -> list:
        return [
            PluginCapability(name="echo", description="Echoes input"),
        ]

    def execute(self, capability: str, *args, **kwargs):
        if capability == "echo":
            return kwargs.get("text", "")
        raise ValueError(f"Unknown capability: {capability}")

    def on_load(self) -> None:
        super().on_load()
        self._loaded_called = True

    def on_unload(self) -> None:
        super().on_unload()
        self._unloaded_called = True

    def on_start(self) -> None:
        super().on_start()
        self._started_called = True

    def on_stop(self) -> None:
        super().on_stop()
        self._state = PluginState.STOPPED
        self._stopped_called = True


class DependentPlugin(PluginBase):
    """A plugin that depends on SimplePlugin."""

    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        return PluginMetadata(
            name="dependent",
            version=PluginVersion(1, 0, 0),
            dependencies={"simple": PluginVersion(1, 0, 0)},
        )

    def get_capabilities(self) -> list:
        return [
            PluginCapability(name="transform", description="Transforms data"),
        ]

    def execute(self, capability: str, *args, **kwargs):
        return f"transformed: {kwargs.get('data', '')}"


class MultiDepPlugin(PluginBase):
    """A plugin with multiple dependencies."""

    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        return PluginMetadata(
            name="multi_dep",
            version=PluginVersion(2, 0, 0),
            dependencies={
                "simple": PluginVersion(1, 0, 0),
                "dependent": PluginVersion(1, 0, 0),
            },
        )

    def get_capabilities(self) -> list:
        return [PluginCapability(name="aggregate", description="Aggregates results")]

    def execute(self, capability: str, *args, **kwargs):
        return "aggregated"


class PriorityPlugin(PluginBase):
    """A plugin with a custom load priority."""

    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        return PluginMetadata(
            name="priority_plugin",
            version=PluginVersion(1, 0, 0),
            load_priority=100,
        )

    def get_capabilities(self) -> list:
        return [PluginCapability("priority", "Priority-based operation")]

    def execute(self, capability: str, *args, **kwargs):
        return "priority_result"


class FailingLoadPlugin(PluginBase):
    """A plugin that fails during on_load()."""

    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        return PluginMetadata(name="failing_load", version=PluginVersion(1, 0, 0))

    def get_capabilities(self) -> list:
        return [PluginCapability("fail", "Always fails")]

    def execute(self, capability: str, *args, **kwargs):
        pass

    def on_load(self) -> None:
        raise RuntimeError("Simulated load failure")


class FailingStartPlugin(PluginBase):
    """A plugin that fails during on_start()."""

    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        return PluginMetadata(name="failing_start", version=PluginVersion(1, 0, 0))

    def get_capabilities(self) -> list:
        return [PluginCapability("fail", "Fails on start")]

    def execute(self, capability: str, *args, **kwargs):
        pass

    def on_start(self) -> None:
        raise RuntimeError("Simulated start failure")


class EventPlugin(PluginBase):
    """A plugin that tracks events for testing the hook system."""

    def __init__(self):
        super().__init__()
        self.received_events = []

    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        return PluginMetadata(name="event_plugin", version=PluginVersion(1, 0, 0))

    def get_capabilities(self) -> list:
        return [PluginCapability("events", "Event handling")]

    def execute(self, capability: str, *args, **kwargs):
        return None

    def on_event(self, event_name: str, event_data=None) -> None:
        self.received_events.append((event_name, event_data))


# ---- Test Suite ----

class TestPluginManagerRegistration(unittest.TestCase):
    """Tests for plugin registration and unregistration."""

    def setUp(self):
        self.manager = PluginManager()

    def test_register_single_plugin(self):
        """Test registering a single plugin."""
        entry = self.manager.register(SimplePlugin)
        self.assertEqual(entry.name, "simple")
        self.assertEqual(entry.version, PluginVersion(1, 0, 0))
        self.assertTrue(self.manager.registry.is_registered("simple"))
        self.assertEqual(self.manager.registry.count(), 1)

    def test_register_multiple_plugins(self):
        """Test registering multiple plugins."""
        self.manager.register(SimplePlugin)
        self.manager.register(DependentPlugin)
        self.assertEqual(self.manager.registry.count(), 2)
        self.assertIn("simple", self.manager.registry.list_plugins())
        self.assertIn("dependent", self.manager.registry.list_plugins())

    def test_register_duplicate_raises(self):
        """Test that registering a duplicate plugin name raises ValueError."""
        self.manager.register(SimplePlugin)
        with self.assertRaises(ValueError):
            self.manager.register(SimplePlugin)

    def test_register_non_plugin_raises(self):
        """Test that registering a non-PluginBase class raises TypeError."""
        with self.assertRaises(TypeError):
            self.manager.register(dict)

    def test_unregister_plugin(self):
        """Test unregistering a plugin."""
        self.manager.register(SimplePlugin)
        self.assertTrue(self.manager.registry.is_registered("simple"))

        self.manager.unregister("simple")
        self.assertFalse(self.manager.registry.is_registered("simple"))
        self.assertEqual(self.manager.registry.count(), 0)

    def test_unregister_nonexistent_raises(self):
        """Test that unregistering a nonexistent plugin raises KeyError."""
        with self.assertRaises(KeyError):
            self.manager.unregister("nonexistent")


class TestPluginManagerLifecycle(unittest.TestCase):
    """Tests for plugin lifecycle operations."""

    def setUp(self):
        self.manager = PluginManager()

    def test_load_plugin(self):
        """Test loading a single plugin."""
        self.manager.register(SimplePlugin)
        result = self.manager.load("simple")

        self.assertTrue(result.success)
        self.assertIsNotNone(result.instance)
        self.assertEqual(
            self.manager.get_plugin_state("simple"),
            PluginState.INITIALIZED,
        )

    def test_load_with_dependency_auto_load(self):
        """Test that loading a plugin auto-loads its dependencies."""
        self.manager.register(SimplePlugin)
        self.manager.register(DependentPlugin)

        result = self.manager.load("dependent")

        self.assertTrue(result.success)
        self.assertEqual(
            self.manager.get_plugin_state("simple"),
            PluginState.INITIALIZED,
        )
        self.assertEqual(
            self.manager.get_plugin_state("dependent"),
            PluginState.INITIALIZED,
        )

    def test_load_fails_on_nonexistent(self):
        """Test that loading a nonexistent plugin raises KeyError."""
        with self.assertRaises(KeyError):
            self.manager.load("ghost")

    def test_load_failing_plugin(self):
        """Test that a plugin that fails on_load returns error result."""
        self.manager.register(FailingLoadPlugin)
        result = self.manager.load("failing_load")

        self.assertFalse(result.success)
        self.assertIn("Simulated load failure", result.error)
        self.assertEqual(
            self.manager.get_plugin_state("failing_load"),
            PluginState.ERROR,
        )

    def test_start_plugin(self):
        """Test starting a loaded plugin."""
        self.manager.register(SimplePlugin)
        self.manager.load("simple")

        result = self.manager.start("simple")
        self.assertTrue(result)
        self.assertEqual(
            self.manager.get_plugin_state("simple"),
            PluginState.RUNNING,
        )
        self.assertTrue(self.manager.is_plugin_running("simple"))

    def test_start_not_loaded(self):
        """Test that starting an unloaded plugin raises LifecycleError."""
        self.manager.register(SimplePlugin)
        with self.assertRaises(LifecycleError):
            self.manager.start("simple")

    def test_start_failing_plugin(self):
        """Test that a plugin that fails on_start returns False."""
        self.manager.register(FailingStartPlugin)
        self.manager.load("failing_start")

        result = self.manager.start("failing_start")
        self.assertFalse(result)
        self.assertEqual(
            self.manager.get_plugin_state("failing_start"),
            PluginState.ERROR,
        )

    def test_stop_plugin(self):
        """Test stopping a running plugin."""
        self.manager.register(SimplePlugin)
        self.manager.load("simple")
        self.manager.start("simple")

        result = self.manager.stop("simple")
        self.assertTrue(result)
        self.assertEqual(
            self.manager.get_plugin_state("simple"),
            PluginState.STOPPED,
        )

    def test_stop_not_running(self):
        """Test stopping a non-running plugin is a no-op."""
        self.manager.register(SimplePlugin)
        self.manager.load("simple")

        result = self.manager.stop("simple")
        self.assertTrue(result)  # No-op success
        self.assertEqual(
            self.manager.get_plugin_state("simple"),
            PluginState.INITIALIZED,
        )

    def test_unload_plugin(self):
        """Test unloading a plugin."""
        self.manager.register(SimplePlugin)
        self.manager.load("simple")

        result = self.manager.unload("simple")
        self.assertTrue(result)
        self.assertEqual(
            self.manager.get_plugin_state("simple"),
            PluginState.UNLOADED,
        )

    def test_unload_running_plugin_auto_stops(self):
        """Test that unloading a running plugin triggers stop then unload."""
        self.manager.register(SimplePlugin)
        self.manager.load("simple")
        self.manager.start("simple")

        result = self.manager.unload("simple")
        self.assertTrue(result)
        self.assertEqual(
            self.manager.get_plugin_state("simple"),
            PluginState.UNLOADED,
        )


class TestPluginManagerBulkOperations(unittest.TestCase):
    """Tests for bulk load/start/stop/unload operations."""

    def setUp(self):
        self.manager = PluginManager()
        self.manager.register(SimplePlugin)
        self.manager.register(DependentPlugin)
        self.manager.register(MultiDepPlugin)

    def test_load_all(self):
        """Test loading all registered plugins."""
        results = self.manager.load_all()

        self.assertEqual(len(results), 3)
        for r in results:
            self.assertTrue(r.success)
        self.assertEqual(self.manager.get_plugin_state("simple"), PluginState.INITIALIZED)
        self.assertEqual(self.manager.get_plugin_state("dependent"), PluginState.INITIALIZED)
        self.assertEqual(self.manager.get_plugin_state("multi_dep"), PluginState.INITIALIZED)

    def test_start_all(self):
        """Test starting all loaded plugins."""
        self.manager.load_all()
        results = self.manager.start_all()

        self.assertEqual(results["simple"], True)
        self.assertEqual(results["dependent"], True)
        self.assertEqual(results["multi_dep"], True)
        self.assertEqual(len(self.manager.get_running_plugins()), 3)

    def test_stop_all(self):
        """Test stopping all running plugins."""
        self.manager.load_all()
        self.manager.start_all()
        self.manager.stop_all()

        self.assertEqual(len(self.manager.get_running_plugins()), 0)

    def test_unload_all(self):
        """Test unloading all plugins."""
        results = self.manager.unload_all()
        self.assertTrue(all(results.values()))


class TestPluginManagerDependencyResolution(unittest.TestCase):
    """Tests for dependency resolution and load ordering."""

    def setUp(self):
        self.manager = PluginManager()

    def test_load_order_dependencies_first(self):
        """Verify dependencies load before dependents."""
        self.manager.register(SimplePlugin)
        self.manager.register(DependentPlugin)
        self.manager.register(MultiDepPlugin)

        load_order = self.manager._compute_load_order()

        # simple must come before dependent, which must come before multi_dep
        simple_idx = load_order.index("simple")
        dep_idx = load_order.index("dependent")
        multi_idx = load_order.index("multi_dep")

        self.assertLess(simple_idx, dep_idx)
        self.assertLess(dep_idx, multi_idx)

    def test_resolve_dependencies_satisfied(self):
        """Test resolving satisfied dependencies."""
        self.manager.register(SimplePlugin)
        self.manager.register(DependentPlugin)

        satisfied, missing = self.manager.resolve_dependencies("dependent")
        self.assertIn("simple", satisfied)
        self.assertEqual(len(missing), 0)

    def test_resolve_dependencies_missing(self):
        """Test resolving dependencies when a dep is missing."""
        self.manager.register(DependentPlugin)

        satisfied, missing = self.manager.resolve_dependencies("dependent")
        self.assertNotIn("simple", satisfied)
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0][0], "simple")

    def test_dependency_graph(self):
        """Test getting the dependency graph."""
        self.manager.register(SimplePlugin)
        self.manager.register(DependentPlugin)

        graph = self.manager.get_dependency_graph()
        self.assertIn("dependent", graph)
        self.assertIn("simple", graph["dependent"])

    def test_plugin_health_check(self):
        """Test health check for a plugin."""
        self.manager.register(SimplePlugin)
        self.manager.load("simple")

        health = self.manager.check_plugin_health("simple")
        self.assertTrue(health["registered"])
        self.assertEqual(health["state"], "initialized")
        self.assertTrue(health["has_instance"])

    def test_health_summary(self):
        """Test overall health summary."""
        self.manager.register(SimplePlugin)
        self.manager.register(DependentPlugin)
        self.manager.load_all()
        self.manager.start_all()

        summary = self.manager.get_health_summary()
        self.assertEqual(summary["total_plugins"], 2)
        self.assertEqual(summary["running_plugins"], 2)


class TestPluginManagerEvents(unittest.TestCase):
    """Tests for event hook system."""

    def setUp(self):
        self.manager = PluginManager()
        self.manager.register(EventPlugin)
        self.manager.load("event_plugin")

    def test_emit_event_to_subscriber(self):
        """Test emitting an event to a subscribed plugin."""
        instance = self.manager.get_plugin_instance("event_plugin")

        def event_callback(name, data):
            instance.received_events.append(("callback", name, data))

        self.manager.subscribe("test.event", "event_plugin", event_callback)
        self.manager.emit_event("test.event", {"key": "value"})

        self.assertEqual(len(instance.received_events), 1)

    def test_global_event_listener(self):
        """Test global event listeners."""
        received = []

        def global_listener(name, data):
            received.append((name, data))

        self.manager.subscribe_global(global_listener)
        self.manager.emit_event("global.event", "payload")

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0], ("global.event", "payload"))

    def test_unsubscribe(self):
        """Test unsubscribing from events."""
        instance = self.manager.get_plugin_instance("event_plugin")
        called = []

        def cb(name, data):
            called.append(1)

        self.manager.subscribe("test.event", "event_plugin", cb)
        self.manager.unsubscribe("test.event", "event_plugin")
        self.manager.emit_event("test.event")

        self.assertEqual(len(called), 0)

    def test_event_subscriptions_map(self):
        """Test getting event subscriptions."""
        self.manager.subscribe("test.a", "event_plugin", lambda n, d: None)
        self.manager.subscribe("test.b", "event_plugin", lambda n, d: None)

        subs = self.manager.get_event_subscriptions()
        self.assertIn("test.a", subs)
        self.assertIn("test.b", subs)
        self.assertIn("event_plugin", subs["test.a"])

    def test_lifecycle_events_emitted(self):
        """Test that lifecycle transitions emit events."""
        received = []

        def listener(name, data):
            received.append(name)

        self.manager.subscribe_global(listener)
        self.manager.register(SimplePlugin)
        self.manager.load("simple")
        self.manager.start("simple")

        self.assertIn("plugin:registered", received)
        self.assertIn("plugin:loaded", received)
        self.assertIn("plugin:started", received)


class TestPluginManagerCapabilityExecution(unittest.TestCase):
    """Tests for capability execution."""

    def setUp(self):
        self.manager = PluginManager()
        self.manager.register(SimplePlugin)
        self.manager.load("simple")
        self.manager.start("simple")

    def test_execute_capability(self):
        """Test executing a capability."""
        result = self.manager.execute_capability("echo", text="hello world")
        self.assertEqual(result, "hello world")

    def test_execute_unknown_capability(self):
        """Test executing a capability that doesn't exist."""
        with self.assertRaises(ValueError):
            self.manager.execute_capability("nonexistent")

    def test_execute_capability_not_running(self):
        """Test executing a capability when plugin isn't running."""
        self.manager.stop("simple")
        with self.assertRaises(RuntimeError):
            self.manager.execute_capability("echo", text="fail")

    def test_execute_capability_preferred_plugin(self):
        """Test executing with a preferred plugin."""
        result = self.manager.execute_capability(
            "echo", text="test", preferred_plugin="simple"
        )
        self.assertEqual(result, "test")


class TestPluginManagerEdgeCases(unittest.TestCase):
    """Tests for edge cases and error handling."""

    def setUp(self):
        self.manager = PluginManager()

    def test_lifecycle_history(self):
        """Test lifecycle event recording."""
        self.manager.register(SimplePlugin)
        self.manager.load("simple")
        self.manager.start("simple")
        self.manager.stop("simple")

        history = self.manager.get_lifecycle_history()
        self.assertGreaterEqual(len(history), 3)

        # Filter by plugin
        simple_history = self.manager.get_lifecycle_history(plugin_name="simple")
        self.assertGreaterEqual(len(simple_history), 3)

    def test_clear_history(self):
        """Test clearing lifecycle history."""
        self.manager.register(SimplePlugin)
        self.manager.clear_history()

        history = self.manager.get_lifecycle_history()
        self.assertEqual(len(history), 0)

    def test_repr(self):
        """Test string representation."""
        self.manager.register(SimplePlugin)
        repr_str = repr(self.manager)
        self.assertIn("PluginManager", repr_str)

    def test_get_plugin_sandbox_config(self):
        """Test getting sandbox config for a loaded plugin."""
        self.manager.register(SimplePlugin)
        self.manager.load("simple")

        config = self.manager.get_plugin_sandbox_config("simple")
        self.assertIsNotNone(config)

    def test_plugin_instance_after_unload(self):
        """Test that plugin instance is None after unload."""
        self.manager.register(SimplePlugin)
        self.manager.load("simple")
        self.assertIsNotNone(self.manager.get_plugin_instance("simple"))

        self.manager.unload("simple")
        self.assertIsNone(self.manager.get_plugin_instance("simple"))


if __name__ == "__main__":
    unittest.main()