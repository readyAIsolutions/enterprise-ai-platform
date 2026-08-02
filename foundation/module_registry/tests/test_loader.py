"""
Tests for ModuleLoader
======================
"""

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

from enterprise.foundation.module_registry.loader import (
    DiscoveryResult,
    LazyModule,
    ModuleLoadError,
    ModuleLoader,
)
from enterprise.foundation.module_registry.registry import (
    ModuleMeta,
    ModuleRegistry,
    ModuleState,
)


class TestLazyModule(unittest.TestCase):
    """Tests for the LazyModule proxy."""

    def test_lazy_defers_load(self) -> None:
        called: list[str] = []

        class FakeModule:
            value = 42

        def loader() -> FakeModule:
            called.append("loaded")
            return FakeModule()

        lazy = LazyModule("fakemod", loader)
        self.assertEqual(len(called), 0)
        self.assertFalse(lazy._loaded)

    def test_lazy_attr_access_triggers_load(self) -> None:
        called: list[str] = []

        class FakeModule:
            value = 42

        def loader() -> FakeModule:
            called.append("loaded")
            return FakeModule()

        lazy = LazyModule("fakemod", loader)
        val = lazy.value
        self.assertEqual(val, 42)
        self.assertEqual(called, ["loaded"])
        self.assertTrue(lazy._loaded)

    def test_lazy_repr(self) -> None:
        lazy = LazyModule("test", lambda: None)
        self.assertIn("lazy", repr(lazy))
        lazy._load()
        self.assertIn("loaded", repr(lazy))

    def test_lazy_caches_module(self) -> None:
        called: list[str] = []

        class FakeModule:
            value = 7

        def loader() -> FakeModule:
            called.append("loaded")
            return FakeModule()

        lazy = LazyModule("fakemod", loader)
        _ = lazy.value
        _ = lazy.value
        self.assertEqual(called, ["loaded"])  # Only loaded once


class TestDiscoveryResult(unittest.TestCase):
    """Tests for the DiscoveryResult dataclass."""

    def test_create_discovery_result(self) -> None:
        dr = DiscoveryResult(
            path=Path("/fake/path.py"),
            module_name="test_mod",
            meta=ModuleMeta(module_id="test_mod"),
        )
        self.assertEqual(dr.module_name, "test_mod")
        self.assertIsInstance(dr.path, Path)
        self.assertEqual(dr.errors, [])

    def test_discovery_result_with_errors(self) -> None:
        dr = DiscoveryResult(
            path=Path("/fake/path.py"),
            module_name="test.mod",
            errors=["Entry point not found"],
        )
        self.assertEqual(len(dr.errors), 1)


class TestModuleLoaderBasic(unittest.TestCase):
    """Basic tests for ModuleLoader initialization and properties."""

    def setUp(self) -> None:
        self.registry = ModuleRegistry()
        self.loader = ModuleLoader(self.registry)

    def test_default_search_paths(self) -> None:
        self.assertGreaterEqual(len(self.loader.search_paths), 1)

    def test_custom_search_paths(self) -> None:
        loader = ModuleLoader(self.registry, search_paths=["/tmp", "/var"])
        self.assertEqual(len(loader.search_paths), 2)
        self.assertEqual(loader.search_paths[0], Path("/tmp"))

    def test_is_loaded_initially_false(self) -> None:
        self.assertFalse(self.loader.is_loaded("anything"))

    def test_is_lazy_initially_false(self) -> None:
        self.assertFalse(self.loader.is_lazy("anything"))

    def test_loaded_modules_empty_initially(self) -> None:
        self.assertEqual(self.loader.loaded_modules(), [])

    def test_load_unregistered_raises(self) -> None:
        with self.assertRaises(ModuleLoadError):
            self.loader.load("not_there")

    def test_unload(self) -> None:
        self.loader._loaded["fake"] = (object(), None)
        self.loader._lazy["fake"] = LazyModule("fake", lambda: None)
        self.loader._file_mtimes["fake"] = 1.0
        self.loader.unload("fake")
        self.assertFalse(self.loader.is_loaded("fake"))
        self.assertFalse(self.loader.is_lazy("fake"))


class TestModuleLoaderWithTempFiles(unittest.TestCase):
    """Tests that require temp filesystem modules."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        # Ensure it's on sys.path for imports
        self._was_on_path = str(self.temp_path) in sys.path
        if not self._was_on_path:
            sys.path.insert(0, str(self.temp_path))

        self.registry = ModuleRegistry()
        self.loader = ModuleLoader(self.registry, search_paths=[str(self.temp_path)])

    def tearDown(self) -> None:
        self.temp_dir.cleanup()
        if not self._was_on_path:
            try:
                sys.path.remove(str(self.temp_path))
            except ValueError:
                pass

    def _create_module(self, name: str, content: str) -> Path:
        """Write a temp .py file and return its path."""
        file_path = self.temp_path / f"{name}.py"
        file_path.write_text(content)
        # Remove from sys.modules if already imported
        sys.modules.pop(name, None)
        return file_path

    def _create_package(self, name: str, init_content: str = "") -> Path:
        """Create a basic package with __init__.py."""
        pkg_dir = self.temp_path / name
        pkg_dir.mkdir(exist_ok=True)
        init_file = pkg_dir / "__init__.py"
        init_file.write_text(init_content)
        sys.modules.pop(name, None)
        return init_file

    def test_load_simple_module(self) -> None:
        self._create_module("hello", "GREETING = 'Hello, world!'")
        self.registry.register(ModuleMeta(module_id="hello"))
        mod = self.loader.load("hello")
        self.assertEqual(mod.GREETING, "Hello, world!")
        self.assertTrue(self.loader.is_loaded("hello"))

    def test_load_returns_cached(self) -> None:
        self._create_module("hello", "GREETING = 'Hello, world!'")
        self.registry.register(ModuleMeta(module_id="hello"))
        mod1 = self.loader.load("hello")
        mod2 = self.loader.load("hello")
        self.assertIs(mod1, mod2)

    def test_load_lazy(self) -> None:
        self._create_module("lazy_test", "VALUE = 99")
        self.registry.register(ModuleMeta(module_id="lazy_test"))

        lazy = self.loader.load_lazy("lazy_test")
        self.assertTrue(self.loader.is_lazy("lazy_test"))
        self.assertFalse(self.loader.is_loaded("lazy_test"))

        val = lazy.VALUE
        self.assertEqual(val, 99)
        self.assertTrue(self.loader.is_loaded("lazy_test"))
        self.assertFalse(self.loader.is_lazy("lazy_test"))

    def test_load_lazy_already_loaded(self) -> None:
        self._create_module("eager", "X = 10")
        self.registry.register(ModuleMeta(module_id="eager"))
        mod = self.loader.load("eager")
        lazy = self.loader.load_lazy("eager")
        self.assertEqual(lazy.X, 10)
        # Should be the same module object
        self.assertIs(lazy._module, mod)

    def test_load_all(self) -> None:
        self._create_module("mod_a", "A = 1")
        self._create_module("mod_b", "B = 2")
        self.registry.register(ModuleMeta(module_id="mod_a"))
        self.registry.register(ModuleMeta(module_id="mod_b"))
        mods = self.loader.load_all()
        self.assertEqual(len(mods), 2)

    def test_hot_reload(self) -> None:
        path = self._create_module("reloadable", "V = 1")
        self.registry.register(ModuleMeta(module_id="reloadable"))
        mod1 = self.loader.load("reloadable")
        self.assertEqual(mod1.V, 1)

        # Update the file
        path.write_text("V = 999")
        mod2 = self.loader.hot_reload("reloadable")
        self.assertEqual(mod2.V, 999)

    def test_hot_reload_not_loaded_raises(self) -> None:
        self.registry.register(ModuleMeta(module_id="not_loaded"))
        with self.assertRaises(ModuleLoadError):
            self.loader.hot_reload("not_loaded")

    def test_hot_reload_if_changed_detects_change(self) -> None:
        import time
        path = self._create_module("change_detect", "MSG = 'old'")
        self.registry.register(ModuleMeta(module_id="change_detect"))
        self.loader.load("change_detect")

        # No change yet
        result = self.loader.hot_reload_if_changed("change_detect")
        self.assertIsNone(result)

        # Sleep briefly then change the file to ensure mtime difference
        time.sleep(0.02)
        path.write_text("MSG = 'new'")
        time.sleep(0.02)
        result = self.loader.hot_reload_if_changed("change_detect")
        self.assertIsNotNone(result)
        self.assertEqual(result.MSG, "new")

    def test_discover_modules(self) -> None:
        self._create_module("plugins_auth", "# auth module")
        self._create_module("plugins_db", "# db module")
        results = self.loader.discover()
        mod_names = {r.module_name for r in results}
        self.assertIn("plugins_auth", mod_names)
        self.assertIn("plugins_db", mod_names)

    def test_discover_with_package(self) -> None:
        self._create_package("mypackage", "# package init")
        results = self.loader.discover()
        mod_names = {r.module_name for r in results}
        self.assertIn("mypackage", mod_names)

    def test_discover_registered_module_matches(self) -> None:
        path = self._create_module("reg_mod", "def run(): return 'ok'")
        self.registry.register(ModuleMeta(
            module_id="reg_mod",
            entry_point="run",
        ))
        results = self.loader.discover()
        for r in results:
            if r.module_name == "reg_mod":
                self.assertEqual(r.meta.module_id, "reg_mod")
                return
        self.fail("Registered module not found in discover results")

    def test_call_entry_point(self) -> None:
        self._create_module("entry_mod", "def start(x, y): return x + y")
        self.registry.register(ModuleMeta(
            module_id="entry_mod",
            entry_point="start",
        ))
        result = self.loader.call_entry_point("entry_mod", 3, 4)
        self.assertEqual(result, 7)

    def test_call_entry_point_no_entry_raises(self) -> None:
        self._create_module("no_entry", "x = 1")
        self.registry.register(ModuleMeta(module_id="no_entry"))
        with self.assertRaises(ModuleLoadError):
            self.loader.call_entry_point("no_entry")

    def test_call_entry_point_not_callable_raises(self) -> None:
        self._create_module("not_callable", "X = 42")
        self.registry.register(ModuleMeta(
            module_id="not_callable",
            entry_point="X",
        ))
        with self.assertRaises(ModuleLoadError):
            self.loader.call_entry_point("not_callable")

    def test_call_entry_point_module_entry(self) -> None:
        self._create_module("callable_mod", "def __call__(): return 'called'")
        self.registry.register(ModuleMeta(
            module_id="callable_mod",
            entry_point="module",
        ))
        # The module itself needs to be callable
        # We're testing the code path, though our test module isn't callable as a ModuleType
        # This will raise because the ModuleType itself isn't callable
        with self.assertRaises(ModuleLoadError):
            self.loader.call_entry_point("callable_mod")

    def test_validate_entry_point_static(self) -> None:
        """Test that static validation catches missing entry point targets."""
        path = self._create_module("static_check", "def valid_func(): pass")
        meta = ModuleMeta(module_id="static_check", entry_point="missing_func")
        _, errors = self.loader._validate_entry_point_safe(path, meta)
        self.assertGreater(len(errors), 0)


if __name__ == "__main__":
    unittest.main()