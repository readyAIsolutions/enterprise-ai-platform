"""
Plugin Registry for the Eni Builder Plugin Framework.

Maintains a catalog of all registered plugins with their capabilities,
versions, and compatibility information. Supports discovery by capability,
version tracking, and dependency resolution assistance.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Type

from .interface import (
    PluginBase,
    PluginCapability,
    PluginMetadata,
    PluginVersion,
    PluginState,
)


@dataclass
class RegistryEntry:
    """A single entry in the PluginRegistry.

    Tracks a registered plugin along with its metadata, capabilities,
    and registration information.
    """

    plugin_class: Type[PluginBase]
    """The plugin class (not instance) registered."""
    metadata: PluginMetadata
    capabilities: List[PluginCapability] = field(default_factory=list)
    registered_at: str = ""
    """ISO 8601 timestamp of registration."""
    instance: Optional[PluginBase] = None
    """The plugin instance, if loaded."""
    state: PluginState = PluginState.REGISTERED

    @property
    def name(self) -> str:
        """Convenience accessor for the plugin name."""
        return self.metadata.name

    @property
    def version(self) -> PluginVersion:
        """Convenience accessor for the plugin version."""
        return self.metadata.version

    @property
    def capability_names(self) -> Set[str]:
        """Get the set of capability names this plugin provides."""
        return {c.name for c in self.capabilities}

    def has_capability(self, name: str) -> bool:
        """Check if this plugin provides a specific capability.

        Args:
            name: The capability name to check.

        Returns:
            True if the plugin provides this capability.
        """
        return name in self.capability_names


@dataclass
class CompatibilityRecord:
    """Records compatibility between two plugins at specific versions."""

    plugin_a: str
    version_a: PluginVersion
    plugin_b: str
    version_b: PluginVersion
    compatible: bool = True
    notes: str = ""


class PluginRegistry:
    """Central registry for all plugins in the system.

    Manages plugin registration, discovery by capability, version
    tracking, and maintains a compatibility matrix between plugins.

    This is the single source of truth for what plugins are available
    and what they can do.
    """

    def __init__(self) -> None:
        self._entries: Dict[str, RegistryEntry] = {}
        self._capability_index: Dict[str, List[str]] = defaultdict(list)
        """Maps capability name -> list of plugin names that provide it."""
        self._tag_index: Dict[str, List[str]] = defaultdict(list)
        """Maps tag -> list of plugin names with that tag."""
        self._compatibility_matrix: List[CompatibilityRecord] = []
        """List of known compatibility records between plugins."""

    # ---- Registration ----

    def register(self, plugin_class: Type[PluginBase]) -> RegistryEntry:
        """Register a plugin class with the registry.

        Args:
            plugin_class: The plugin class to register (must subclass PluginBase).

        Returns:
            The RegistryEntry created for this plugin.

        Raises:
            ValueError: If a plugin with the same name is already registered.
            TypeError: If plugin_class does not subclass PluginBase.
        """
        if not issubclass(plugin_class, PluginBase):
            raise TypeError(
                f"{plugin_class.__name__} must be a subclass of PluginBase"
            )

        metadata = plugin_class.get_metadata()

        if metadata.name in self._entries:
            raise ValueError(
                f"Plugin '{metadata.name}' is already registered"
            )

        # Check version compatibility with framework
        temp_instance = plugin_class()
        capabilities = temp_instance.get_capabilities()

        import datetime
        entry = RegistryEntry(
            plugin_class=plugin_class,
            metadata=metadata,
            capabilities=capabilities,
            registered_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            state=PluginState.REGISTERED,
        )

        self._entries[metadata.name] = entry

        # Index capabilities
        for cap in capabilities:
            self._capability_index[cap.name].append(metadata.name)

        # Index tags
        for tag in metadata.tags:
            self._tag_index[tag].append(metadata.name)

        return entry

    def unregister(self, plugin_name: str) -> None:
        """Remove a plugin from the registry.

        Args:
            plugin_name: Name of the plugin to unregister.

        Raises:
            KeyError: If the plugin is not registered.
        """
        if plugin_name not in self._entries:
            raise KeyError(f"Plugin '{plugin_name}' is not registered")

        entry = self._entries[plugin_name]

        # Remove capability index entries
        for cap in entry.capabilities:
            self._capability_index[cap.name].remove(plugin_name)
            if not self._capability_index[cap.name]:
                del self._capability_index[cap.name]

        # Remove tag index entries
        for tag in entry.metadata.tags:
            self._tag_index[tag].remove(plugin_name)
            if not self._tag_index[tag]:
                del self._tag_index[tag]

        del self._entries[plugin_name]

    # ---- Lookup ----

    def get_entry(self, plugin_name: str) -> RegistryEntry:
        """Get a plugin's registry entry by name.

        Args:
            plugin_name: Name of the plugin.

        Returns:
            The RegistryEntry for the plugin.

        Raises:
            KeyError: If the plugin is not registered.
        """
        if plugin_name not in self._entries:
            raise KeyError(f"Plugin '{plugin_name}' is not registered")
        return self._entries[plugin_name]

    def get_plugin(self, plugin_name: str) -> Optional[PluginBase]:
        """Get the plugin instance if it's been loaded.

        Args:
            plugin_name: Name of the plugin.

        Returns:
            The plugin instance, or None if not loaded.
        """
        entry = self.get_entry(plugin_name)
        return entry.instance

    def is_registered(self, plugin_name: str) -> bool:
        """Check if a plugin is registered.

        Args:
            plugin_name: Name of the plugin.

        Returns:
            True if registered.
        """
        return plugin_name in self._entries

    def list_plugins(self) -> List[str]:
        """List all registered plugin names.

        Returns:
            Sorted list of plugin names.
        """
        return sorted(self._entries.keys())

    def get_all_entries(self) -> Dict[str, RegistryEntry]:
        """Get all registry entries.

        Returns:
            Dict mapping plugin names to RegistryEntry objects.
        """
        return dict(self._entries)

    # ---- Capability Discovery ----

    def find_by_capability(self, capability_name: str) -> List[RegistryEntry]:
        """Find all plugins that provide a specific capability.

        Args:
            capability_name: Name of the capability to search for.

        Returns:
            List of RegistryEntry objects for matching plugins.
        """
        plugin_names = self._capability_index.get(capability_name, [])
        return [self._entries[name] for name in plugin_names]

    def has_capability(self, capability_name: str) -> bool:
        """Check if any plugin provides a specific capability.

        Args:
            capability_name: Name of the capability.

        Returns:
            True if at least one plugin provides it.
        """
        return capability_name in self._capability_index

    def get_all_capabilities(self) -> Dict[str, List[str]]:
        """Get a mapping of all capabilities to the plugins that provide them.

        Returns:
            Dict mapping capability name to list of plugin names.
        """
        return dict(self._capability_index)

    def search_capabilities(
        self,
        name_pattern: str = "",
        tags: Optional[Set[str]] = None,
    ) -> List[CapabilitySearchResult]:
        """Search for capabilities matching criteria.

        Args:
            name_pattern: Substring pattern to match in capability names.
            tags: Optional set of tags that must all be present.

        Returns:
            List of CapabilitySearchResult objects sorted by relevance.
        """
        results: List[CapabilitySearchResult] = []

        for cap_name, plugin_list in self._capability_index.items():
            # Filter by name pattern
            if name_pattern and name_pattern.lower() not in cap_name.lower():
                continue

            for pname in plugin_list:
                entry = self._entries[pname]

                # Filter by tags
                if tags and not tags.issubset(entry.metadata.tags):
                    continue

                # Find the matching capability
                for cap in entry.capabilities:
                    if cap.name == cap_name:
                        results.append(CapabilitySearchResult(
                            capability=cap,
                            plugin_name=pname,
                            plugin_version=entry.version,
                            plugin_tags=entry.metadata.tags.copy(),
                        ))
                        break

        return results

    # ---- Tag Discovery ----

    def find_by_tag(self, tag: str) -> List[RegistryEntry]:
        """Find all plugins with a specific tag.

        Args:
            tag: The tag to search for.

        Returns:
            List of RegistryEntry objects with the tag.
        """
        plugin_names = self._tag_index.get(tag, [])
        return [self._entries[name] for name in plugin_names]

    def find_by_tags(self, tags: Iterable[str], require_all: bool = True) -> List[RegistryEntry]:
        """Find plugins matching multiple tags.

        Args:
            tags: The tags to search for.
            require_all: If True, plugins must have ALL tags (AND).
                         If False, plugins must have ANY tag (OR).

        Returns:
            List of matching RegistryEntry objects.
        """
        tag_set = set(tags)
        if not tag_set:
            return []

        if require_all:
            # Intersection of all tag matches
            result_names: Optional[Set[str]] = None
            for tag in tag_set:
                names = set(self._tag_index.get(tag, []))
                if result_names is None:
                    result_names = names
                else:
                    result_names &= names
                if not result_names:
                    return []
            return [self._entries[n] for n in (result_names or set())]
        else:
            # Union of all tag matches
            result_names: Set[str] = set()
            for tag in tag_set:
                result_names.update(self._tag_index.get(tag, []))
            return [self._entries[n] for n in result_names]

    # ---- Version Tracking ----

    def get_version(self, plugin_name: str) -> PluginVersion:
        """Get the version of a registered plugin.

        Args:
            plugin_name: Name of the plugin.

        Returns:
            The PluginVersion.

        Raises:
            KeyError: If the plugin is not registered.
        """
        return self.get_entry(plugin_name).version

    def get_all_versions(self) -> Dict[str, PluginVersion]:
        """Get a mapping of all plugin names to their versions.

        Returns:
            Dict of plugin_name -> PluginVersion.
        """
        return {name: entry.version for name, entry in self._entries.items()}

    # ---- Compatibility Matrix ----

    def record_compatibility(
        self,
        plugin_a: str,
        version_a: PluginVersion,
        plugin_b: str,
        version_b: PluginVersion,
        compatible: bool = True,
        notes: str = "",
    ) -> CompatibilityRecord:
        """Record a compatibility relationship between two plugin versions.

        Args:
            plugin_a: Name of first plugin.
            version_a: Version of first plugin.
            plugin_b: Name of second plugin.
            version_b: Version of second plugin.
            compatible: Whether they are compatible.
            notes: Optional notes about the compatibility.

        Returns:
            The created CompatibilityRecord.
        """
        record = CompatibilityRecord(
            plugin_a=plugin_a,
            version_a=version_a,
            plugin_b=plugin_b,
            version_b=version_b,
            compatible=compatible,
            notes=notes,
        )
        self._compatibility_matrix.append(record)
        return record

    def check_compatibility(
        self,
        plugin_name: str,
        target_plugin: str,
    ) -> Optional[bool]:
        """Check if two registered plugins are known to be compatible.

        Args:
            plugin_name: Name of the first plugin.
            target_plugin: Name of the second plugin.

        Returns:
            True if compatible, False if incompatible, None if unknown.
        """
        a_entry = self.get_entry(plugin_name)
        b_entry = self.get_entry(target_plugin)

        for record in self._compatibility_matrix:
            if (
                record.plugin_a == plugin_name
                and record.plugin_b == target_plugin
                and record.version_a == a_entry.version
                and record.version_b == b_entry.version
            ):
                return record.compatible
            # Also check reverse
            if (
                record.plugin_a == target_plugin
                and record.plugin_b == plugin_name
                and record.version_a == b_entry.version
                and record.version_b == a_entry.version
            ):
                return record.compatible

        return None  # Unknown

    def get_compatibility_matrix(self) -> Dict[Tuple[str, str], bool]:
        """Get a simplified compatibility matrix for all registered plugins.

        Returns:
            Dict of (plugin_a, plugin_b) -> compatible, for all pairs.
        """
        result: Dict[Tuple[str, str], bool] = {}
        names = sorted(self._entries.keys())

        for i, a in enumerate(names):
            for b in names[i + 1:]:
                status = self.check_compatibility(a, b)
                if status is not None:
                    result[(a, b)] = status

        return result

    def resolve_dependencies(
        self,
        plugin_name: str,
    ) -> Tuple[List[str], List[Tuple[str, str, str]]]:
        """Resolve dependencies for a plugin, checking version compatibility.

        Args:
            plugin_name: Name of the plugin to resolve.

        Returns:
            Tuple of (satisfied_deps, missing_or_incompatible_deps).
            Each missing/incompatible dep is (dep_name, required_version, details).

        Raises:
            KeyError: If the plugin is not registered.
        """
        entry = self.get_entry(plugin_name)
        satisfied: List[str] = []
        missing: List[Tuple[str, str, str]] = []

        for dep_name, required_version in entry.metadata.dependencies.items():
            if not self.is_registered(dep_name):
                missing.append((dep_name, str(required_version), "Not registered"))
                continue

            dep_version = self.get_version(dep_name)
            if dep_version.is_compatible_with(required_version):
                satisfied.append(dep_name)
            else:
                missing.append((
                    dep_name,
                    str(required_version),
                    f"Found version {dep_version}, need >= {required_version}",
                ))

        return satisfied, missing

    def count(self) -> int:
        """Get the total number of registered plugins.

        Returns:
            Number of registered plugins.
        """
        return len(self._entries)

    def clear(self) -> None:
        """Remove all entries from the registry."""
        self._entries.clear()
        self._capability_index.clear()
        self._tag_index.clear()
        self._compatibility_matrix.clear()


@dataclass
class CapabilitySearchResult:
    """Result from a capability search in the registry."""

    capability: PluginCapability
    plugin_name: str
    plugin_version: PluginVersion
    plugin_tags: Set[str] = field(default_factory=set)