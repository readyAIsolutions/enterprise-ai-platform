"""
Comprehensive unit tests for the PluginRegistry class.

Tests cover:
- Plugin registration and unregistration
- Capability discovery and indexing
- Tag-based search
- Version tracking
- Compatibility matrix
- Dependency resolution
- Search functionality
"""

import unittest

from enterprise.foundation.plugin_framework.interface import (
    PluginBase,
    PluginCapability,
    PluginMetadata,
    PluginState,
    PluginVersion,
)
from enterprise.foundation.plugin_framework.registry import (
    PluginRegistry,
    RegistryEntry,
    CompatibilityRecord,
)


# ---- Test Plugin Classes ----

class SearchPlugin(PluginBase):
    """Plugin providing search capabilities."""

    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        return PluginMetadata(
            name="search_plugin",
            version=PluginVersion(1, 2, 3),
            description="Full-text search engine",
            tags={"search", "indexing"},
        )

    def get_capabilities(self) -> list:
        return [
            PluginCapability(
                name="search",
                description="Search documents",
                tags={"fulltext"},
            ),
            PluginCapability(
                name="index",
                description="Index documents",
                tags={"indexing"},
            ),
        ]

    def execute(self, capability: str, *args, **kwargs):
        return {"capability": capability, "args": args, "kwargs": kwargs}


class StoragePlugin(PluginBase):
    """Plugin providing storage capabilities."""

    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        return PluginMetadata(
            name="storage_plugin",
            version=PluginVersion(2, 0, 0),
            description="Data storage backend",
            tags={"storage", "persistence"},
        )

    def get_capabilities(self) -> list:
        return [
            PluginCapability(name="store", description="Store data"),
            PluginCapability(name="retrieve", description="Retrieve data"),
            PluginCapability(
                name="search",
                description="Search stored data",
                tags={"storage", "metadata"},
            ),
        ]

    def execute(self, capability: str, *args, **kwargs):
        return {"capability": capability}


class AnalyticsPlugin(PluginBase):
    """Plugin providing analytics, depending on other plugins."""

    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        return PluginMetadata(
            name="analytics_plugin",
            version=PluginVersion(3, 1, 0),
            description="Data analytics engine",
            tags={"analytics", "processing"},
            dependencies={"search_plugin": PluginVersion(1, 0, 0)},
            optional_dependencies={"storage_plugin": PluginVersion(2, 0, 0)},
        )

    def get_capabilities(self) -> list:
        return [
            PluginCapability(name="analyze", description="Analyze data"),
            PluginCapability(name="report", description="Generate reports"),
        ]

    def execute(self, capability: str, *args, **kwargs):
        return f"analytics: {capability}"


class VersionedPluginV1(PluginBase):
    """Version 1.0.0 of a plugin."""

    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        return PluginMetadata(
            name="versioned",
            version=PluginVersion(1, 0, 0),
        )

    def get_capabilities(self) -> list:
        return [PluginCapability(name="process", description="Process data")]

    def execute(self, capability: str, *args, **kwargs):
        pass


# ---- Tests ----

class TestPluginRegistryRegistration(unittest.TestCase):
    """Tests for registration/unregistration."""

    def setUp(self):
        self.registry = PluginRegistry()
        self.registry.register(SearchPlugin)

    def test_register_plugin(self):
        """Test registering a single plugin."""
        self.assertTrue(self.registry.is_registered("search_plugin"))
        self.assertEqual(self.registry.count(), 1)

    def test_register_multiple(self):
        """Test registering multiple plugins."""
        self.registry.register(StoragePlugin)
        self.registry.register(AnalyticsPlugin)
        self.assertEqual(self.registry.count(), 3)

    def test_register_duplicate_raises(self):
        """Test registering duplicate raises ValueError."""
        with self.assertRaises(ValueError):
            self.registry.register(SearchPlugin)

    def test_register_non_plugin_raises(self):
        """Test registering non-PluginBase raises TypeError."""
        with self.assertRaises(TypeError):
            self.registry.register(str)

    def test_unregister_plugin(self):
        """Test unregistering a plugin."""
        self.registry.unregister("search_plugin")
        self.assertFalse(self.registry.is_registered("search_plugin"))
        self.assertEqual(self.registry.count(), 0)

    def test_unregister_nonexistent_raises(self):
        """Test unregistering nonexistent raises KeyError."""
        with self.assertRaises(KeyError):
            self.registry.unregister("ghost")

    def test_list_plugins(self):
        """Test listing registered plugins."""
        self.registry.register(StoragePlugin)
        plugins = self.registry.list_plugins()
        self.assertEqual(plugins, ["search_plugin", "storage_plugin"])

    def test_get_entry(self):
        """Test getting a registry entry."""
        entry = self.registry.get_entry("search_plugin")
        self.assertIsInstance(entry, RegistryEntry)
        self.assertEqual(entry.name, "search_plugin")
        self.assertEqual(entry.version, PluginVersion(1, 2, 3))

    def test_get_entry_nonexistent_raises(self):
        """Test getting nonexistent entry raises KeyError."""
        with self.assertRaises(KeyError):
            self.registry.get_entry("nope")

    def test_get_plugin_instance_none(self):
        """Test that plugin instance is None until loaded."""
        instance = self.registry.get_plugin("search_plugin")
        self.assertIsNone(instance)

    def test_get_all_entries(self):
        """Test getting all entries."""
        self.registry.register(StoragePlugin)
        all_entries = self.registry.get_all_entries()
        self.assertEqual(len(all_entries), 2)
        self.assertIn("search_plugin", all_entries)
        self.assertIn("storage_plugin", all_entries)

    def test_clear(self):
        """Test clearing the registry."""
        self.registry.register(StoragePlugin)
        self.registry.clear()
        self.assertEqual(self.registry.count(), 0)
        self.assertEqual(len(self.registry.list_plugins()), 0)


class TestPluginRegistryCapabilities(unittest.TestCase):
    """Tests for capability discovery."""

    def setUp(self):
        self.registry = PluginRegistry()
        self.registry.register(SearchPlugin)
        self.registry.register(StoragePlugin)

    def test_find_by_capability_single(self):
        """Test finding plugins by a capability only one provides."""
        entries = self.registry.find_by_capability("index")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].name, "search_plugin")

    def test_find_by_capability_shared(self):
        """Test finding plugins by a capability multiple provide."""
        entries = self.registry.find_by_capability("search")
        self.assertEqual(len(entries), 2)
        names = {e.name for e in entries}
        self.assertIn("search_plugin", names)
        self.assertIn("storage_plugin", names)

    def test_find_by_capability_nonexistent(self):
        """Test finding by nonexistent capability returns empty list."""
        entries = self.registry.find_by_capability("nonexistent")
        self.assertEqual(len(entries), 0)

    def test_has_capability(self):
        """Test checking if a capability exists."""
        self.assertTrue(self.registry.has_capability("search"))
        self.assertTrue(self.registry.has_capability("store"))
        self.assertFalse(self.registry.has_capability("frobnicate"))

    def test_get_all_capabilities(self):
        """Test getting all capabilities map."""
        caps = self.registry.get_all_capabilities()
        self.assertIn("search", caps)
        self.assertIn("index", caps)
        self.assertIn("store", caps)
        self.assertIn("retrieve", caps)

    def test_search_capabilities_by_name(self):
        """Test searching capabilities by name pattern."""
        results = self.registry.search_capabilities(name_pattern="search")
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertIn("search", r.capability.name.lower())

    def test_search_capabilities_by_tags(self):
        """Test searching capabilities by tags."""
        self.registry.register(AnalyticsPlugin)
        results = self.registry.search_capabilities(
            tags={"storage"}
            # This should match storage_plugin but not search_plugin
        )
        # storage_plugin has tags={"storage", "persistence"}
        matching_plugins = {r.plugin_name for r in results}
        self.assertIn("storage_plugin", matching_plugins)
        self.assertNotIn("search_plugin", matching_plugins)


class TestPluginRegistryTags(unittest.TestCase):
    """Tests for tag-based discovery."""

    def setUp(self):
        self.registry = PluginRegistry()
        self.registry.register(SearchPlugin)
        self.registry.register(StoragePlugin)
        self.registry.register(AnalyticsPlugin)

    def test_find_by_tag(self):
        """Test finding plugins by a single tag."""
        entries = self.registry.find_by_tag("storage")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].name, "storage_plugin")

    def test_find_by_tag_multiple_matches(self):
        """Test finding by a tag that matches multiple plugins."""
        entries = self.registry.find_by_tag("processing")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].name, "analytics_plugin")

    def test_find_by_tag_nonexistent(self):
        """Test finding by nonexistent tag returns empty list."""
        entries = self.registry.find_by_tag("nonexistent")
        self.assertEqual(len(entries), 0)

    def test_find_by_tags_and(self):
        """Test finding plugins by ALL tags (AND)."""
        # storage_plugin has tags={"storage", "persistence"}
        entries = self.registry.find_by_tags({"storage", "persistence"}, require_all=True)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].name, "storage_plugin")

    def test_find_by_tags_and_none(self):
        """Test AND search where no plugin has all tags."""
        entries = self.registry.find_by_tags(
            {"storage", "search"}, require_all=True
        )
        self.assertEqual(len(entries), 0)

    def test_find_by_tags_or(self):
        """Test finding plugins by ANY tag (OR)."""
        entries = self.registry.find_by_tags(
            {"storage", "search"}, require_all=False
        )
        names = {e.name for e in entries}
        self.assertIn("search_plugin", names)
        self.assertIn("storage_plugin", names)

    def test_find_by_tags_empty(self):
        """Test finding by empty tags returns empty."""
        entries = self.registry.find_by_tags([])
        self.assertEqual(len(entries), 0)


class TestPluginRegistryVersions(unittest.TestCase):
    """Tests for version tracking."""

    def setUp(self):
        self.registry = PluginRegistry()
        self.registry.register(SearchPlugin)
        self.registry.register(StoragePlugin)

    def test_get_version(self):
        """Test getting a single plugin version."""
        version = self.registry.get_version("search_plugin")
        self.assertEqual(version, PluginVersion(1, 2, 3))

    def test_get_version_nonexistent_raises(self):
        """Test getting version of nonexistent raises KeyError."""
        with self.assertRaises(KeyError):
            self.registry.get_version("ghost")

    def test_get_all_versions(self):
        """Test getting all versions."""
        versions = self.registry.get_all_versions()
        self.assertIn("search_plugin", versions)
        self.assertIn("storage_plugin", versions)
        self.assertEqual(versions["search_plugin"], PluginVersion(1, 2, 3))
        self.assertEqual(versions["storage_plugin"], PluginVersion(2, 0, 0))


class TestPluginRegistryCompatibility(unittest.TestCase):
    """Tests for compatibility matrix."""

    def setUp(self):
        self.registry = PluginRegistry()
        self.registry.register(SearchPlugin)
        self.registry.register(StoragePlugin)

    def test_record_compatibility(self):
        """Test recording a compatibility relationship."""
        record = self.registry.record_compatibility(
            "search_plugin", PluginVersion(1, 2, 3),
            "storage_plugin", PluginVersion(2, 0, 0),
            compatible=True,
            notes="Tested together",
        )
        self.assertIsInstance(record, CompatibilityRecord)
        self.assertTrue(record.compatible)

    def test_check_compatibility_compatible(self):
        """Test checking known compatible plugins."""
        self.registry.record_compatibility(
            "search_plugin", PluginVersion(1, 2, 3),
            "storage_plugin", PluginVersion(2, 0, 0),
            compatible=True,
        )
        result = self.registry.check_compatibility(
            "search_plugin", "storage_plugin"
        )
        self.assertTrue(result)

    def test_check_compatibility_incompatible(self):
        """Test checking known incompatible plugins."""
        self.registry.record_compatibility(
            "search_plugin", PluginVersion(1, 2, 3),
            "storage_plugin", PluginVersion(2, 0, 0),
            compatible=False,
        )
        result = self.registry.check_compatibility(
            "search_plugin", "storage_plugin"
        )
        self.assertFalse(result)

    def test_check_compatibility_unknown(self):
        """Test checking compatibility for unknown pair."""
        result = self.registry.check_compatibility(
            "search_plugin", "storage_plugin"
        )
        self.assertIsNone(result)

    def test_check_compatibility_reverse(self):
        """Test compatibility check works in reverse order too."""
        self.registry.record_compatibility(
            "search_plugin", PluginVersion(1, 2, 3),
            "storage_plugin", PluginVersion(2, 0, 0),
            compatible=True,
        )
        result = self.registry.check_compatibility(
            "storage_plugin", "search_plugin"
        )
        self.assertTrue(result)

    def test_get_compatibility_matrix(self):
        """Test getting the compatibility matrix."""
        self.registry.record_compatibility(
            "search_plugin", PluginVersion(1, 2, 3),
            "storage_plugin", PluginVersion(2, 0, 0),
            compatible=True,
        )
        matrix = self.registry.get_compatibility_matrix()
        self.assertIn(("search_plugin", "storage_plugin"), matrix)
        self.assertTrue(matrix[("search_plugin", "storage_plugin")])


class TestPluginRegistryDependencies(unittest.TestCase):
    """Tests for dependency resolution."""

    def setUp(self):
        self.registry = PluginRegistry()
        self.registry.register(SearchPlugin)
        self.registry.register(StoragePlugin)
        self.registry.register(AnalyticsPlugin)

    def test_resolve_dependencies_all_present(self):
        """Test resolving when all deps are present."""
        satisfied, missing = self.registry.resolve_dependencies("analytics_plugin")
        self.assertIn("search_plugin", satisfied)
        self.assertEqual(len(missing), 0)

    def test_resolve_dependencies_missing(self):
        """Test resolving when hard deps are missing."""
        # Create a registry without search_plugin
        registry = PluginRegistry()
        registry.register(AnalyticsPlugin)

        satisfied, missing = registry.resolve_dependencies("analytics_plugin")
        self.assertEqual(len(satisfied), 0)
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0][0], "search_plugin")

    def test_resolve_dependencies_nonexistent_raises(self):
        """Test resolving for nonexistent plugin raises KeyError."""
        with self.assertRaises(KeyError):
            self.registry.resolve_dependencies("ghost")


class TestPluginRegistryEdgeCases(unittest.TestCase):
    """Tests for edge cases."""

    def test_count_on_empty(self):
        """Test count on empty registry."""
        registry = PluginRegistry()
        self.assertEqual(registry.count(), 0)

    def test_clear_empty(self):
        """Test clearing an empty registry doesn't raise."""
        registry = PluginRegistry()
        registry.clear()
        self.assertEqual(registry.count(), 0)

    def test_registry_entry_properties(self):
        """Test RegistryEntry convenience properties."""
        registry = PluginRegistry()
        registry.register(SearchPlugin)
        entry = registry.get_entry("search_plugin")

        self.assertEqual(entry.name, "search_plugin")
        self.assertEqual(entry.version, PluginVersion(1, 2, 3))
        self.assertEqual(entry.state, PluginState.REGISTERED)
        self.assertTrue(entry.has_capability("search"))
        self.assertTrue(entry.has_capability("index"))
        self.assertFalse(entry.has_capability("frobnicate"))
        self.assertEqual(entry.capability_names, {"search", "index"})


if __name__ == "__main__":
    unittest.main()