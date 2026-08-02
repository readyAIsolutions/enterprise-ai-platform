"""
Tests for the Plugin / Tool Framework module.

Covers:
  - SemVer parsing and compatibility checks
  - Plugin discovery from filesystem
  - Plugin loading, initialization, lifecycle
  - Dependency resolution and cycle detection
  - Hot reload
  - Sandbox policies
"""

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from enterprise.orchestration.plugin_framework import (
    PluginBase,
    PluginManager,
    PluginRegistry,
    PluginDiscovery,
    PluginManifest,
    PluginCapability,
    RegistryEntry,
    SemVer,
    SandboxPolicy,
    SubprocessSandbox,
    PluginState,
    PluginFileWatcher,
    PluginError,
    PluginNotFoundError,
    PluginLoadError,
    IncompatibleVersionError,
    SandboxViolationError,
    CircularDependencyError,
    hot_reload_module,
)


# ---------------------------------------------------------------------------
# SemVer Tests
# ---------------------------------------------------------------------------

class TestSemVer:
    """Tests for semantic version parsing and comparison."""

    def test_parse_simple(self):
        v = SemVer.parse("1.2.3")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3
        assert str(v) == "1.2.3"

    def test_parse_with_prerelease(self):
        v = SemVer.parse("2.0.0-alpha.1")
        assert v.major == 2
        assert v.prerelease == "alpha.1"
        assert "alpha.1" in str(v)

    def test_parse_with_build(self):
        v = SemVer.parse("1.0.0+build.123")
        assert v.build == "build.123"

    def test_parse_loose(self):
        v = SemVer.parse("1.2")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 0

    def test_parse_invalid(self):
        v = SemVer.parse("not.a.version")
        assert v == SemVer(0, 0, 0)

    def test_ordering(self):
        assert SemVer(1, 0, 0) < SemVer(2, 0, 0)
        assert SemVer(1, 2, 0) < SemVer(1, 3, 0)
        assert SemVer(1, 0, 5) < SemVer(1, 0, 10)
        assert SemVer(2, 0, 0) > SemVer(1, 9, 9)

    def test_satisfies_exact(self):
        v = SemVer(1, 2, 3)
        assert v.satisfies("==1.2.3")
        assert not v.satisfies("==1.2.4")

    def test_satisfies_caret(self):
        v = SemVer(1, 5, 2)
        assert v.satisfies("^1.0.0")
        assert not v.satisfies("^2.0.0")

    def test_satisfies_tilde(self):
        v = SemVer(1, 2, 5)
        assert v.satisfies("~1.2.0")
        assert not v.satisfies("~1.3.0")

    def test_satisfies_range(self):
        v = SemVer(1, 5, 0)
        assert v.satisfies(">=1.0.0,<2.0.0")
        assert not v.satisfies(">=2.0.0,<3.0.0")

    def test_satisfies_wildcard(self):
        v = SemVer(9, 9, 9)
        assert v.satisfies("*")
        assert v.satisfies("")


# ---------------------------------------------------------------------------
# PluginBase Tests
# ---------------------------------------------------------------------------

class TestPluginBase:
    """Tests for the PluginBase abstract class."""

    def test_concrete_plugin(self):
        class MyPlugin(PluginBase):
            manifest = PluginManifest(
                name="my-plugin",
                version="1.0.0",
                description="Test plugin",
            )

            def on_init(self, config):
                self._config = config

            def on_start(self):
                self._started = True

        plugin = MyPlugin()
        assert plugin.name == "my-plugin"
        assert plugin.manifest.version == "1.0.0"

        plugin.on_init({"key": "val"})
        assert plugin._config == {"key": "val"}

    def test_manifest_from_classmethod(self):
        class DefaultPlugin(PluginBase):
            def on_init(self, config):
                pass

        manifest = DefaultPlugin.get_manifest()
        assert manifest.name == "DefaultPlugin"
        assert manifest.version == "0.1.0"


# ---------------------------------------------------------------------------
# Plugin Discovery Tests
# ---------------------------------------------------------------------------

class TestPluginDiscovery:
    """Tests for filesystem-based plugin discovery."""

    def test_discover_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            discovery = PluginDiscovery([tmp])
            manifests = discovery.discover()
            assert len(manifests) == 0

    def test_discover_plugin_with_manifest_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin_dir = Path(tmp) / "test_plugin"
            plugin_dir.mkdir()
            manifest_data = {
                "name": "test-plugin",
                "version": "2.1.0",
                "description": "A test plugin",
                "author": "tester",
                "capabilities": [
                    {
                        "name": "text_gen",
                        "description": "Generates text",
                        "version": "1.0.0",
                    }
                ],
                "dependencies": {"core": ">=1.0.0"},
                "entry_point": "test_plugin.plugin:TestPlugin",
                "sandbox": True,
                "tags": ["ai", "text"],
            }
            (plugin_dir / "manifest.json").write_text(json.dumps(manifest_data))

            discovery = PluginDiscovery([tmp])
            manifests = discovery.discover()
            assert "test-plugin" in manifests
            m = manifests["test-plugin"]
            assert m.version == "2.1.0"
            assert m.sandbox is True
            assert len(m.capabilities) == 1
            assert m.capabilities[0].name == "text_gen"
            assert "ai" in m.tags

    def test_discover_plugin_with_plugin_py(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin_dir = Path(tmp) / "my_plugin"
            plugin_dir.mkdir()
            (plugin_dir / "plugin.py").write_text("""
from enterprise.orchestration.plugin_framework import PluginBase, PluginManifest

class MyPlugin(PluginBase):
    manifest = PluginManifest(
        name="my-custom-plugin",
        version="3.0.0",
    )
    def on_init(self, config):
        pass
""")
            discovery = PluginDiscovery([tmp])
            manifests = discovery.discover()
            # AST-based discovery uses directory name; validates entry_point is found
            assert "my_plugin" in manifests
            assert manifests["my_plugin"].entry_point == "my_plugin.plugin:MyPlugin"

    def test_discover_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "group" / "nested_plugin"
            nested.mkdir(parents=True)
            (nested / "manifest.json").write_text(json.dumps({
                "name": "nested-plugin",
                "version": "0.5.0",
            }))

            discovery = PluginDiscovery([tmp])
            manifests = discovery.discover()
            assert "nested-plugin" in manifests


# ---------------------------------------------------------------------------
# Plugin Registry Tests
# ---------------------------------------------------------------------------

class TestPluginRegistry:
    """Tests for the PluginRegistry."""

    def test_register_and_get(self):
        registry = PluginRegistry()
        manifest = PluginManifest(name="p1", version="1.0.0")
        registry.register(manifest)

        entry = registry.get("p1")
        assert entry is not None
        assert entry.manifest.name == "p1"
        assert entry.state == PluginState.DISCOVERED

    def test_capability_indexing(self):
        registry = PluginRegistry()
        m1 = PluginManifest(
            name="plugin-a", version="1.0.0",
            capabilities=[PluginCapability(name="greet", description="Greeting")],
        )
        m2 = PluginManifest(
            name="plugin-b", version="1.0.0",
            capabilities=[PluginCapability(name="farewell", description="Farewell")],
        )
        registry.register(m1)
        registry.register(m2)

        results = registry.find_by_capability("greet")
        assert len(results) == 1
        assert results[0].manifest.name == "plugin-a"

        results = registry.find_by_capability("nonexistent")
        assert len(results) == 0

    def test_list_all(self):
        registry = PluginRegistry()
        registry.register(PluginManifest(name="a", version="1.0.0"))
        registry.register(PluginManifest(name="b", version="1.0.0"))
        assert len(registry.list_all()) == 2
        assert "a" in registry
        assert "c" not in registry

    def test_unregister(self):
        registry = PluginRegistry()
        registry.register(PluginManifest(name="a", version="1.0.0"))
        registry.unregister("a")
        assert registry.get("a") is None
        assert len(registry) == 0


# ---------------------------------------------------------------------------
# Plugin Manager Tests
# ---------------------------------------------------------------------------

class TestPluginManager:
    """Tests for the PluginManager lifecycle and dependency resolution."""

    def test_load_simple_plugin(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin_dir = Path(tmp) / "hello"
            plugin_dir.mkdir()
            (plugin_dir / "manifest.json").write_text(json.dumps({
                "name": "hello",
                "version": "1.0.0",
                "entry_point": "hello.plugin:HelloPlugin",
            }))
            (plugin_dir / "plugin.py").write_text("""
from enterprise.orchestration.plugin_framework import PluginBase, PluginManifest

class HelloPlugin(PluginBase):
    manifest = PluginManifest(name="hello", version="1.0.0")
    def on_init(self, config):
        self.greeting = config.get("greeting", "hello")
    def on_start(self):
        self.started = True
""")
            # Make it importable
            sys.path.insert(0, tmp)

            try:
                mgr = PluginManager(search_paths=[tmp])
                mgr.discover()
                mgr.load("hello", config={"greeting": "hi"})
                entry = mgr.registry.get("hello")
                assert entry.state == PluginState.INITIALIZED
                assert entry.instance.greeting == "hi"

                mgr.start("hello")
                assert entry.state == PluginState.RUNNING
            finally:
                sys.path.remove(tmp)

    def test_load_nonexistent_plugin_raises(self):
        mgr = PluginManager()
        with pytest.raises(PluginNotFoundError):
            mgr.load("nonexistent")

    def test_dependency_resolution(self):
        registry = PluginRegistry()
        registry.register(PluginManifest(
            name="base", version="2.0.0",
        ))
        registry.register(PluginManifest(
            name="dependent", version="1.0.0",
            dependencies={"base": ">=1.0.0"},
        ))

        mgr = PluginManager(registry=registry)
        deps = mgr._resolve_dependencies(
            PluginManifest(name="dependent", version="1.0.0",
                           dependencies={"base": ">=1.0.0"})
        )
        assert "base" in deps

    def test_circular_dependency_detection(self):
        registry = PluginRegistry()
        registry.register(PluginManifest(
            name="a", version="1.0.0", dependencies={"b": "*"},
        ))
        registry.register(PluginManifest(
            name="b", version="1.0.0", dependencies={"a": "*"},
        ))

        mgr = PluginManager(registry=registry)
        with pytest.raises(CircularDependencyError):
            mgr._resolve_dependencies(
                PluginManifest(name="a", version="1.0.0",
                               dependencies={"b": "*"})
            )

    def test_version_incompatibility(self):
        registry = PluginRegistry()
        registry.register(PluginManifest(name="old", version="0.5.0"))

        mgr = PluginManager(registry=registry)
        manifest = PluginManifest(
            name="consumer", version="1.0.0",
            dependencies={"old": ">=1.0.0"},
        )
        issues = mgr.check_dependency_versions("consumer")
        # consumer isn't registered, but we can test the check logic
        registry.register(manifest)
        issues = mgr.check_dependency_versions("consumer")
        assert any("Version mismatch" in i for i in issues)

    def test_topological_sort(self):
        registry = PluginRegistry()
        registry.register(PluginManifest(name="core", version="1.0.0"))
        registry.register(PluginManifest(
            name="middleware", version="1.0.0",
            dependencies={"core": "*"},
        ))
        registry.register(PluginManifest(
            name="app", version="1.0.0",
            dependencies={"core": "*", "middleware": "*"},
        ))

        mgr = PluginManager(registry=registry)
        order = mgr._topological_sort()
        assert order.index("core") < order.index("middleware")
        assert order.index("middleware") < order.index("app")


# ---------------------------------------------------------------------------
# Hot Reload Tests
# ---------------------------------------------------------------------------

class TestHotReload:
    """Tests for hot-reload file watching."""

    def test_file_watcher_detects_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            changed_paths = []

            def callback(paths):
                changed_paths.extend(paths)

            test_file = Path(tmp) / "plugin.py"
            test_file.write_text("# initial content")

            watcher = PluginFileWatcher([tmp], callback, poll_interval=0.1)
            watcher.start()

            time.sleep(0.2)
            # Modify file
            test_file.write_text("# updated content")
            time.sleep(0.3)

            watcher.stop()
            assert len(changed_paths) > 0
            assert any("plugin.py" in p for p in changed_paths)

    def test_watcher_stop(self):
        watcher = PluginFileWatcher(["/tmp/nonexistent"], lambda p: None)
        watcher.start()
        assert watcher._thread is not None
        watcher.stop()
        assert watcher._thread is None

    # Need to import PluginFileWatcher from the module
    # It's defined in plugin_framework.py but not publicly exported
    # Will test through PluginManager.enable_hot_reload instead


# ---------------------------------------------------------------------------
# Sandbox Tests
# ---------------------------------------------------------------------------

class TestSandbox:
    """Tests for sandbox policies."""

    def test_permissive_policy(self):
        policy = SandboxPolicy.permissive()
        assert policy.allow_network is True
        assert policy.allow_file_write is True
        assert policy.allow_subprocess is True

    def test_strict_policy(self):
        policy = SandboxPolicy.strict()
        assert policy.allow_network is False
        assert policy.allow_file_write is False
        assert "os" in policy.blocked_modules

    def test_custom_policy(self):
        policy = SandboxPolicy(
            allowed_modules={"json", "math"},
            blocked_modules={"os", "subprocess"},
            allow_network=False,
            max_memory_mb=128,
        )
        assert policy.max_memory_mb == 128
        assert "os" in policy.blocked_modules
        assert "json" in policy.allowed_modules


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge case tests for the plugin framework."""

    def test_hot_reload_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod_path = Path(tmp) / "dynamic_mod.py"
            mod_path.write_text("VALUE = 1\n")
            sys.path.insert(0, tmp)

            try:
                import dynamic_mod
                dynamic_mod = hot_reload_module("dynamic_mod")
                assert dynamic_mod.VALUE == 1

                mod_path.write_text("VALUE = 42\n")
                dynamic_mod = hot_reload_module("dynamic_mod")
                assert dynamic_mod.VALUE == 42
            finally:
                sys.path.remove(tmp)
                sys.modules.pop("dynamic_mod", None)

    def test_load_error_propagates(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin_dir = Path(tmp) / "bad_plugin"
            plugin_dir.mkdir()
            (plugin_dir / "manifest.json").write_text(json.dumps({
                "name": "bad",
                "version": "1.0.0",
                "entry_point": "nonexistent.module:BadClass",
            }))

            mgr = PluginManager(search_paths=[tmp])
            mgr.discover()
            with pytest.raises(PluginLoadError):
                mgr.load("bad")

            entry = mgr.registry.get("bad")
            assert entry.state == PluginState.ERROR
            assert entry.error is not None