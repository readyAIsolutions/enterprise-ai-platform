"""
Standardized Plugin Interface for the Eni Builder Plugin Framework.

Defines the PluginBase abstract base class that all plugins must implement,
along with version compatibility checking and plugin metadata.
"""

from __future__ import annotations

import abc
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type


class PluginState(Enum):
    """Lifecycle states of a plugin."""

    UNREGISTERED = "unregistered"
    REGISTERED = "registered"
    LOADED = "loaded"        # Module imported
    INITIALIZED = "initialized"  # on_load() called, ready to start
    RUNNING = "running"      # started, actively serving
    STOPPING = "stopping"    # mid-shutdown
    STOPPED = "stopped"      # stopped but still initialized
    UNLOADED = "unloaded"    # fully unloaded
    ERROR = "error"          # error state


@dataclass
class PluginVersion:
    """
    Semantic version representation for plugins.

    Supports comparisons for compatibility checks.
    Format: MAJOR.MINOR.PATCH[-prerelease][+build]
    """

    major: int = 0
    minor: int = 0
    patch: int = 0
    prerelease: str = ""
    build: str = ""

    @classmethod
    def parse(cls, version_str: str) -> "PluginVersion":
        """Parse a version string into a PluginVersion instance.

        Args:
            version_str: Version string like '1.2.3-alpha+build001'.

        Returns:
            A PluginVersion instance.

        Raises:
            ValueError: If the version string is invalid.
        """
        pattern = (
            r"^(?P<major>0|[1-9]\d*)"
            r"\.(?P<minor>0|[1-9]\d*)"
            r"\.(?P<patch>0|[1-9]\d*)"
            r"(?:-(?P<prerelease>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
            r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
        )
        match = re.match(pattern, version_str.strip())
        if not match:
            raise ValueError(f"Invalid version string: {version_str}")
        return cls(
            major=int(match.group("major")),
            minor=int(match.group("minor")),
            patch=int(match.group("patch")),
            prerelease=match.group("prerelease") or "",
            build=match.group("build") or "",
        )

    def is_compatible_with(self, required: "PluginVersion", allow_prerelease: bool = False) -> bool:
        """Check if this version is compatible with a required version.

        Same major version and at least same minor.patch.

        Args:
            required: The minimum required version.
            allow_prerelease: Whether prerelease versions are acceptable.

        Returns:
            True if compatible, False otherwise.
        """
        if self.major != required.major:
            return False
        if self.minor < required.minor:
            return False
        if self.minor == required.minor and self.patch < required.patch:
            return False
        if self.prerelease and not allow_prerelease:
            # Stable > prerelease checks; if required is stable and we're prerelease, reject
            if not required.prerelease:
                return False
        return True

    def to_tuple(self) -> Tuple[int, int, int, str, str]:
        """Return version as a comparable tuple."""
        return (self.major, self.minor, self.patch, self.prerelease, self.build)

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            base += f"-{self.prerelease}"
        if self.build:
            base += f"+{self.build}"
        return base

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PluginVersion):
            return NotImplemented
        return self.to_tuple() == other.to_tuple()

    def __lt__(self, other: "PluginVersion") -> bool:
        return self._cmp(other) < 0

    def __le__(self, other: "PluginVersion") -> bool:
        return self._cmp(other) <= 0

    def __gt__(self, other: "PluginVersion") -> bool:
        return self._cmp(other) > 0

    def __ge__(self, other: "PluginVersion") -> bool:
        return self._cmp(other) >= 0

    def __hash__(self) -> int:
        return hash(self.to_tuple())

    def _cmp(self, other: "PluginVersion") -> int:
        """Compare two versions, accounting for prerelease rules per semver."""
        # Compare numeric parts
        if self.major != other.major:
            return 1 if self.major > other.major else -1
        if self.minor != other.minor:
            return 1 if self.minor > other.minor else -1
        if self.patch != other.patch:
            return 1 if self.patch > other.patch else -1
        # Prerelease has lower precedence than normal release
        if not self.prerelease and other.prerelease:
            return 1
        if self.prerelease and not other.prerelease:
            return -1
        # Both prerelease or both normal: lexicographic on prerelease
        if self.prerelease != other.prerelease:
            # Compare each dot-separated identifier
            a_parts = self.prerelease.split(".")
            b_parts = other.prerelease.split(".")
            for a, b in zip(a_parts, b_parts):
                a_is_num = a.isdigit()
                b_is_num = b.isdigit()
                if a_is_num and b_is_num:
                    result = int(a) - int(b)
                elif a_is_num:
                    return -1  # numeric < alphanumeric
                elif b_is_num:
                    return 1
                else:
                    result = (a > b) - (a < b)
                if result != 0:
                    return result
            return len(a_parts) - len(b_parts)
        return 0


@dataclass
class PluginCapability:
    """Describes a single capability offered by a plugin.

    Used for registration in the PluginRegistry and for discovery.
    """

    name: str
    description: str = ""
    tags: Set[str] = field(default_factory=set)
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PluginCapability):
            return NotImplemented
        return self.name == other.name


@dataclass
class PluginMetadata:
    """Metadata describing a plugin.

    Includes identity, version, dependencies, and lifecycle configuration.
    """

    name: str
    version: PluginVersion
    description: str = ""
    author: str = ""
    website: str = ""
    license: str = ""
    dependencies: Dict[str, PluginVersion] = field(default_factory=dict)
    """Mapping of plugin_name -> minimum version required."""
    optional_dependencies: Dict[str, PluginVersion] = field(default_factory=dict)
    """Dependencies that are optional; plugin can function without them."""
    auto_start: bool = False
    """Whether the plugin should auto-start after initialization."""
    load_priority: int = 0
    """Higher priority plugins load first."""
    framework_version: PluginVersion = field(default_factory=lambda: PluginVersion(1, 0, 0))
    entry_point: str = ""
    """Fully qualified entry point, e.g. 'my_package.my_plugin:PluginClass'."""
    tags: Set[str] = field(default_factory=set)


class PluginBase(abc.ABC):
    """Abstract base class for all plugins in the Eni Builder framework.

    Every plugin must subclass this and implement all abstract methods.
    Plugins follow a strict lifecycle:
        registered -> loaded -> initialized -> running -> stopping -> stopped -> unloaded

    State transitions:
        - registered -> loaded: Module is imported
        - loaded -> initialized: on_load() is called
        - initialized -> running: start() / on_start() called
        - running -> stopping: stop() / on_stop() called
        - stopping -> stopped: Cleanup complete
        - stopped -> unloaded: on_unload() called
    """

    def __init__(self) -> None:
        self._state: PluginState = PluginState.REGISTERED
        self._metadata: Optional[PluginMetadata] = None

    # ---- Metadata ----

    @classmethod
    @abc.abstractmethod
    def get_metadata(cls) -> PluginMetadata:
        """Return the plugin's metadata.

        Subclasses must implement this to provide identity, version, and
        dependency information.

        Returns:
            PluginMetadata instance describing this plugin.
        """
        ...

    @property
    def metadata(self) -> Optional[PluginMetadata]:
        """Get the cached metadata for this plugin instance."""
        if self._metadata is None:
            self._metadata = self.get_metadata()
        return self._metadata

    @property
    def state(self) -> PluginState:
        """Current lifecycle state of the plugin."""
        return self._state

    # ---- Capabilities ----

    @abc.abstractmethod
    def get_capabilities(self) -> List[PluginCapability]:
        """Return the list of capabilities this plugin provides.

        Capabilities are used by the PluginRegistry for discovery.

        Returns:
            List of PluginCapability objects.
        """
        ...

    # ---- Execution ----

    @abc.abstractmethod
    def execute(
        self,
        capability: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute a named capability provided by this plugin.

        Args:
            capability: Name of the capability to execute.
            *args: Positional arguments for the capability.
            **kwargs: Keyword arguments for the capability.

        Returns:
            The result of the capability execution.

        Raises:
            ValueError: If the capability is not supported.
            RuntimeError: If the plugin is not in the running state.
        """
        ...

    # ---- Lifecycle Hooks ----

    def on_load(self) -> None:
        """Called after the plugin module is imported and dependencies resolved.

        Use this to perform one-time setup: connecting to databases,
        allocating resources, etc. After this returns successfully,
        the plugin transitions to INITIALIZED state.

        Called by the PluginManager during the load phase.
        """
        self._state = PluginState.INITIALIZED

    def on_unload(self) -> None:
        """Called when the plugin is being fully unloaded from the system.

        Use this for final cleanup: closing connections, releasing resources,
        removing temporary files. After this returns, the plugin transitions
        to UNLOADED state and may be garbage-collected.

        Called by the PluginManager during the unload phase.
        """
        self._state = PluginState.UNLOADED

    def on_start(self) -> None:
        """Called when the plugin is starting active operation.

        The plugin transitions to RUNNING state. Use this to begin
        background tasks, open listeners, etc.

        Called by the PluginManager start phase.
        """
        self._state = PluginState.RUNNING

    def on_stop(self) -> None:
        """Called when the plugin is stopping active operation.

        The plugin transitions through STOPPING to STOPPED.
        Use this to pause work, close listeners, flush buffers.

        Called by the PluginManager stop phase.
        """
        self._state = PluginState.STOPPING
        # Subclasses should perform cleanup then set:
        # self._state = PluginState.STOPPED

    def on_error(self, error: Exception) -> None:
        """Called when the plugin encounters an error during operation.

        The plugin transitions to ERROR state. Implementors should log
        the error and attempt recovery if possible.

        Args:
            error: The exception that was raised.
        """
        self._state = PluginState.ERROR

    # ---- Version Compatibility ----

    @classmethod
    def check_framework_compatibility(cls, framework_version: PluginVersion) -> bool:
        """Check if this plugin is compatible with the given framework version.

        Args:
            framework_version: The version of the plugin framework.

        Returns:
            True if compatible, False otherwise.
        """
        metadata = cls.get_metadata()
        return framework_version.is_compatible_with(
            metadata.framework_version, allow_prerelease=False
        )

    @classmethod
    def check_plugin_compatibility(
        cls, other_version: PluginVersion, required: PluginVersion
    ) -> bool:
        """Check if another plugin's version satisfies a dependency requirement.

        Args:
            other_version: The version of the other plugin.
            required: The minimum required version.

        Returns:
            True if the other version is compatible.
        """
        return other_version.is_compatible_with(required)

    # ---- Event Hooks ----

    def on_event(self, event_name: str, event_data: Any = None) -> None:
        """Receive and handle an event from the PluginManager event system.

        Override this in plugins that need to react to system events
        (e.g., config changes, other plugins starting/stopping).

        Args:
            event_name: Name of the event.
            event_data: Optional payload for the event.
        """
        pass  # Default: no-op

    def __repr__(self) -> str:
        meta = self.metadata
        name = meta.name if meta else self.__class__.__name__
        return f"<{self.__class__.__name__}({name}) state={self._state.value}>"


# ---- Utility type aliases ----

PluginConstructor = Callable[..., PluginBase]
"""Type alias for a plugin constructor/factory callable."""


EventCallback = Callable[[str, Any], None]
"""Type alias for an event handler callback: (event_name, event_data) -> None."""


class PluginInterfaceError(Exception):
    """Base exception for errors related to plugin interface violations."""

    pass


class IncompatibleVersionError(PluginInterfaceError):
    """Raised when a plugin's version is incompatible with requirements."""

    def __init__(
        self,
        plugin_name: str,
        current: PluginVersion,
        required: PluginVersion,
    ) -> None:
        self.plugin_name = plugin_name
        self.current = current
        self.required = required
        super().__init__(
            f"Plugin '{plugin_name}' version {current} is incompatible "
            f"with required version {required}"
        )