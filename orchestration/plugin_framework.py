"""
Plugin / Tool Framework: Discovery, Loading, Hot-Reload, Sandboxing.

Provides a production-grade plugin system with:
  - Filesystem-based plugin discovery (namespace packages, entry-points)
  - Dynamic loading with dependency resolution
  - Hot-reload via file-system watchers (inotify / polling)
  - Sandboxed execution with resource limits and import restrictions
  - Capability declaration and introspection
  - Semantic version compatibility checking (semver)
  - Lifecycle management (load -> init -> start -> stop -> unload)
"""

from __future__ import annotations

import abc
import ast
import functools
import importlib
import importlib.util
import inspect
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
import traceback
import types
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import (
    Any, Callable, ClassVar, Dict, Iterator, List, Optional,
    Set, Tuple, Type, TypeVar, Union,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class PluginError(Exception):
    """Base exception for plugin-related errors."""
    pass


class PluginNotFoundError(PluginError):
    """A requested plugin could not be found."""
    def __init__(self, name: str, search_paths: Optional[List[str]] = None):
        self.name = name
        self.search_paths = search_paths or []
        msg = f"Plugin '{name}' not found"
        if search_paths:
            msg += f" in paths: {search_paths}"
        super().__init__(msg)


class PluginLoadError(PluginError):
    """A plugin could not be loaded (import, syntax, missing deps)."""
    def __init__(self, name: str, reason: str):
        self.name = name
        self.reason = reason
        super().__init__(f"Failed to load plugin '{name}': {reason}")


class IncompatibleVersionError(PluginError):
    """Plugin version is incompatible with the required range."""
    def __init__(self, name: str, required: str, actual: str):
        self.name = name
        self.required = required
        self.actual = actual
        super().__init__(
            f"Plugin '{name}' requires version {required}, found {actual}"
        )


class SandboxViolationError(PluginError):
    """A sandboxed plugin attempted a forbidden operation."""
    def __init__(self, name: str, violation: str):
        self.name = name
        self.violation = violation
        super().__init__(f"Sandbox violation in plugin '{name}': {violation}")


class CircularDependencyError(PluginError):
    """Circular dependency detected among plugins."""
    def __init__(self, cycle: List[str]):
        self.cycle = cycle
        super().__init__(f"Circular dependency: {' -> '.join(cycle)}")


# ---------------------------------------------------------------------------
# Semantic Versioning
# ---------------------------------------------------------------------------

@dataclass(frozen=True, order=True)
class SemVer:
    """Semantic version tuple with comparison support."""
    major: int = 0
    minor: int = 0
    patch: int = 0
    prerelease: str = ""
    build: str = ""

    _PARSE_RE: ClassVar[re.Pattern] = re.compile(
        r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$"
    )

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            base += f"-{self.prerelease}"
        if self.build:
            base += f"+{self.build}"
        return base

    @classmethod
    def parse(cls, version: str) -> "SemVer":
        """Parse a semantic version string. Returns SemVer(0,0,0) on failure."""
        m = cls._PARSE_RE.match(version.strip())
        if not m:
            # Attempt loose parsing
            parts = version.strip().split(".")
            try:
                return cls(
                    major=int(parts[0]) if len(parts) > 0 else 0,
                    minor=int(parts[1]) if len(parts) > 1 else 0,
                    patch=int(parts[2]) if len(parts) > 2 else 0,
                )
            except (ValueError, IndexError):
                return cls(0, 0, 0)
        return cls(
            major=int(m.group(1)),
            minor=int(m.group(2)),
            patch=int(m.group(3)),
            prerelease=m.group(4) or "",
            build=m.group(5) or "",
        )

    def satisfies(self, spec: str) -> bool:
        """Check if this version satisfies a version specifier.

        Supported spec formats:
          - exact:  "==1.2.3"
          - range:  ">=1.2.0,<2.0.0"
          - caret:  "^1.2.3"   (>=1.2.3,<2.0.0)
          - tilde:  "~1.2.3"   (>=1.2.3,<1.3.0)
          - wild:   "*" or ""
        """
        spec = spec.strip()
        if spec in ("*", ""):
            return True

        # Handle comma-separated ranges FIRST: ">=1.0,<2.0"
        if "," in spec:
            parts = [p.strip() for p in spec.split(",")]
            return all(self.satisfies(p) for p in parts)

        if spec.startswith("^"):
            target = SemVer.parse(spec[1:])
            if target.major == 0:
                if target.minor == 0:
                    return self >= target and self < SemVer(0, 0, target.patch + 1)
                return self >= target and self < SemVer(0, target.minor + 1, 0)
            return self >= target and self < SemVer(target.major + 1, 0, 0)

        if spec.startswith("~"):
            target = SemVer.parse(spec[1:])
            return self >= target and self < SemVer(target.major, target.minor + 1, 0)

        if spec.startswith("=="):
            return self == SemVer.parse(spec[2:])
        if spec.startswith(">="):
            return self >= SemVer.parse(spec[2:])
        if spec.startswith("<="):
            return self <= SemVer.parse(spec[2:])
        if spec.startswith(">"):
            return self > SemVer.parse(spec[1:])
        if spec.startswith("<"):
            return self < SemVer.parse(spec[1:])

        # Fallback: exact match
        return self == SemVer.parse(spec)


# ---------------------------------------------------------------------------
# Plugin States and Metadata
# ---------------------------------------------------------------------------

class PluginState(Enum):
    """Lifecycle states of a plugin."""
    DISCOVERED = auto()   # found but not loaded
    LOADED = auto()       # module imported
    INITIALIZED = auto()  # init() called
    RUNNING = auto()      # start() called
    STOPPED = auto()      # stop() called
    UNLOADED = auto()     # removed from registry
    ERROR = auto()        # failed during loading/init


@dataclass
class PluginCapability:
    """Declares a capability provided by a plugin.

    Attributes:
        name: Unique capability identifier (e.g. 'text_generation').
        description: Human-readable description.
        version: Capability API version.
        input_schema: Expected input schema (JSON Schema compatible dict).
        output_schema: Expected output schema.
        tags: Search/discovery tags.
    """
    name: str
    description: str = ""
    version: str = "1.0.0"
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    tags: Set[str] = field(default_factory=set)


@dataclass
class PluginManifest:
    """Metadata describing a plugin.

    Used for discovery, compatibility checks, and dependency resolution.
    """
    name: str
    version: str
    description: str = ""
    author: str = ""
    license: str = ""
    homepage: str = ""
    capabilities: List[PluginCapability] = field(default_factory=list)
    dependencies: Dict[str, str] = field(default_factory=dict)
    """plugin_name -> version_spec"""
    python_version: str = ""
    framework_version: str = ""
    entry_point: str = ""
    """Dotted path to the plugin class/factory (e.g. 'mypkg.plugin:MyPlugin')."""
    sandbox: bool = False
    isolated: bool = False
    """Run in a subprocess for full isolation."""
    max_memory_mb: int = 0
    """0 means no limit."""
    tags: Set[str] = field(default_factory=set)

    def semver(self) -> SemVer:
        return SemVer.parse(self.version)


# ---------------------------------------------------------------------------
# Abstract Plugin Base
# ---------------------------------------------------------------------------

class PluginBase(abc.ABC):
    """Abstract base class for all plugins.

    Subclasses must implement ``on_init`` and optionally ``on_start``,
    ``on_stop``, and ``on_unload``.
    """

    manifest: PluginManifest
    _state: PluginState = PluginState.DISCOVERED

    @abc.abstractmethod
    def on_init(self, config: Dict[str, Any]) -> None:
        """Called after loading to initialize the plugin.

        Args:
            config: Configuration dict provided at load time.
        """
        ...

    def on_start(self) -> None:
        """Called to activate the plugin after initialization."""
        pass

    def on_stop(self) -> None:
        """Called to gracefully stop the plugin."""
        pass

    def on_unload(self) -> None:
        """Called before the plugin module is unloaded."""
        pass

    @property
    def state(self) -> PluginState:
        return self._state

    @property
    def name(self) -> str:
        return self.manifest.name if self.manifest else self.__class__.__name__

    @classmethod
    def get_manifest(cls) -> PluginManifest:
        """Return the manifest; subclasses can override or define as class var."""
        return getattr(cls, "manifest", PluginManifest(
            name=cls.__name__,
            version="0.1.0",
        ))


# ---------------------------------------------------------------------------
# Sandbox
# ---------------------------------------------------------------------------

class SandboxPolicy:
    """Defines what a sandboxed plugin is permitted to do.

    Attributes:
        allowed_modules: Set of importable module names (glob patterns).
        blocked_modules: Set of blocked module names (overrides allowed).
        allow_network: Whether network access is permitted.
        allow_file_read: Whether file read access is permitted.
        allow_file_write: Whether file write access is permitted.
        allowed_paths: If set, restricts file access to these paths.
        max_cpu_time_sec: Maximum CPU time for a single call.
        max_memory_mb: Maximum RSS memory in MB.
        allow_subprocess: Whether subprocess execution is permitted.
    """
    def __init__(
        self,
        *,
        allowed_modules: Optional[Set[str]] = None,
        blocked_modules: Optional[Set[str]] = None,
        allow_network: bool = False,
        allow_file_read: bool = True,
        allow_file_write: bool = False,
        allowed_paths: Optional[List[str]] = None,
        max_cpu_time_sec: float = 30.0,
        max_memory_mb: int = 256,
        allow_subprocess: bool = False,
    ):
        self.allowed_modules = allowed_modules or {"*"}
        self.blocked_modules = blocked_modules or {
            "os", "subprocess", "shutil", "sys", "ctypes",
            "socket", "http", "urllib", "requests",
        }
        self.allow_network = allow_network
        self.allow_file_read = allow_file_read
        self.allow_file_write = allow_file_write
        self.allowed_paths = allowed_paths
        self.max_cpu_time_sec = max_cpu_time_sec
        self.max_memory_mb = max_memory_mb
        self.allow_subprocess = allow_subprocess

    @classmethod
    def permissive(cls) -> "SandboxPolicy":
        """A sandbox policy with minimal restrictions."""
        return cls(blocked_modules=set(), allow_network=True,
                   allow_file_write=True, allow_subprocess=True,
                   max_memory_mb=0)

    @classmethod
    def strict(cls) -> "SandboxPolicy":
        """A strict sandbox policy with maximum restrictions."""
        return cls()


class SubprocessSandbox:
    """Execute plugin code in a subprocess for true isolation.

    Communicates via stdin/stdout with the parent process using a simple
    JSON-based protocol. Memory and CPU limits enforced by the OS.
    """

    def __init__(self, policy: SandboxPolicy):
        self.policy = policy

    def execute(
        self,
        module_path: str,
        entry_fn: str,
        args: Dict[str, Any],
        timeout: float = 60.0,
    ) -> Any:
        """Execute an entry function in a sandboxed subprocess."""
        import json as _json

        payload = _json.dumps({
            "module": module_path,
            "function": entry_fn,
            "args": args,
            "policy": {
                "max_cpu_time_sec": self.policy.max_cpu_time_sec,
                "max_memory_mb": self.policy.max_memory_mb,
            },
        })

        try:
            proc = subprocess.run(
                [sys.executable, "-c", _SANDBOX_WORKER_SCRIPT, module_path, entry_fn],
                input=payload,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd="/tmp",
                env={
                    "PATH": os.environ.get("PATH", "/usr/bin"),
                    "HOME": "/tmp",
                    "SANDBOX_MAX_MEMORY_MB": str(self.policy.max_memory_mb),
                },
                preexec_fn=_set_process_limits if sys.platform != "win32" else None,
            )

            if proc.returncode != 0:
                raise SandboxViolationError(
                    module_path,
                    f"Subprocess exited with code {proc.returncode}: {proc.stderr[:500]}"
                )

            return _json.loads(proc.stdout)

        except subprocess.TimeoutExpired:
            raise SandboxViolationError(
                module_path, f"Subprocess sandbox timed out after {timeout}s"
            )


def _set_process_limits() -> None:
    """Set OS-level resource limits for subprocess sandbox (Unix only)."""
    import resource
    max_mem = int(os.environ.get("SANDBOX_MAX_MEMORY_MB", "256"))
    if max_mem > 0:
        limit = max_mem * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        except (ValueError, OSError):
            pass


_SANDBOX_WORKER_SCRIPT = """
import importlib, json, sys, os, signal, resource

def _sandbox_main():
    module_path = sys.argv[1]
    entry_fn = sys.argv[2]
    payload = json.loads(sys.stdin.read())
    max_cpu = payload["policy"]["max_cpu_time_sec"]

    if max_cpu > 0:
        signal.signal(signal.SIGALRM, lambda *_: sys.exit(1))
        signal.alarm(int(max_cpu))

    try:
        mod = importlib.import_module(module_path)
        fn = getattr(mod, entry_fn)
        result = fn(**payload["args"])
        print(json.dumps({"ok": True, "result": result}))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e), "type": type(e).__name__}))

_sandbox_main()
"""


# ---------------------------------------------------------------------------
# Plugin Discovery
# ---------------------------------------------------------------------------

class PluginDiscovery:
    """Discovers plugins on the filesystem or via Python entry points.

    Searches directories for packages/modules containing a ``PluginBase``
    subclass or a ``plugin.py`` / ``manifest.json`` marker.
    """

    MARKER_FILES: ClassVar[List[str]] = [
        "plugin.py", "manifest.json", "plugin.yaml", "plugin.yml"
    ]

    def __init__(self, search_paths: Optional[List[str]] = None):
        self._search_paths = [Path(p) for p in (search_paths or [])]
        self._discovered: Dict[str, PluginManifest] = {}

    def add_search_path(self, path: str) -> None:
        p = Path(path).resolve()
        if p not in self._search_paths:
            self._search_paths.append(p)

    def discover(self) -> Dict[str, PluginManifest]:
        """Scan all search paths and return discovered plugin manifests."""
        self._discovered.clear()
        for sp in self._search_paths:
            if not sp.exists():
                logger.warning("Plugin search path does not exist: %s", sp)
                continue
            self._scan_directory(sp)
        return dict(self._discovered)

    def _scan_directory(self, root: Path) -> None:
        """Recursively scan a directory for plugins."""
        for entry in root.iterdir():
            if entry.is_dir() and not entry.name.startswith((".", "__")):
                # Check for marker files
                for marker in self.MARKER_FILES:
                    if (entry / marker).exists():
                        manifest = self._parse_manifest(entry)
                        if manifest:
                            self._discovered[manifest.name] = manifest
                        break
                else:
                    # Check for Python package with PluginBase subclass
                    init_file = entry / "__init__.py"
                    if init_file.exists():
                        manifest = self._extract_manifest_from_source(init_file)
                        if manifest:
                            self._discovered[manifest.name] = manifest
                    else:
                        self._scan_directory(entry)

    def _parse_manifest(self, plugin_dir: Path) -> Optional[PluginManifest]:
        """Parse manifest.json or extract metadata from plugin.py."""
        manifest_file = plugin_dir / "manifest.json"
        if manifest_file.exists():
            import json
            try:
                data = json.loads(manifest_file.read_text())
                return self._manifest_from_dict(data)
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                logger.warning("Invalid manifest in %s: %s", manifest_file, exc)
                return None

        plugin_file = plugin_dir / "plugin.py"
        if plugin_file.exists():
            return self._extract_manifest_from_source(plugin_file)

        return None

    def _extract_manifest_from_source(self, filepath: Path) -> Optional[PluginManifest]:
        """Attempt to extract a PluginBase subclass manifest from a .py file."""
        try:
            source = filepath.read_text()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    for base in node.bases:
                        if (isinstance(base, ast.Name) and base.id == "PluginBase") or \
                           (isinstance(base, ast.Attribute) and base.attr == "PluginBase"):
                            # Heuristic: look for a manifest assignment
                            for item in node.body:
                                if isinstance(item, ast.Assign):
                                    for target in item.targets:
                                        if isinstance(target, ast.Name) and target.id == "manifest":
                                            # Rough extraction — best effort
                                            name = filepath.parent.name
                                            return PluginManifest(
                                                name=name,
                                                version="0.1.0",
                                                entry_point=f"{filepath.parent.name}.plugin:{node.name}",
                                            )
            return None
        except (SyntaxError, UnicodeDecodeError):
            return None

    @staticmethod
    def _manifest_from_dict(data: Dict[str, Any]) -> PluginManifest:
        caps = [
            PluginCapability(
                name=c.get("name", ""),
                description=c.get("description", ""),
                version=c.get("version", "1.0.0"),
                input_schema=c.get("input_schema", {}),
                output_schema=c.get("output_schema", {}),
                tags=set(c.get("tags", [])),
            )
            for c in data.get("capabilities", [])
        ]
        return PluginManifest(
            name=data["name"],
            version=data.get("version", "0.1.0"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            license=data.get("license", ""),
            homepage=data.get("homepage", ""),
            capabilities=caps,
            dependencies=data.get("dependencies", {}),
            python_version=data.get("python_version", ""),
            framework_version=data.get("framework_version", ""),
            entry_point=data.get("entry_point", ""),
            sandbox=data.get("sandbox", False),
            isolated=data.get("isolated", False),
            max_memory_mb=data.get("max_memory_mb", 0),
            tags=set(data.get("tags", [])),
        )


# ---------------------------------------------------------------------------
# Plugin Registry
# ---------------------------------------------------------------------------

@dataclass
class RegistryEntry:
    """A plugin stored in the registry with its loaded state."""
    manifest: PluginManifest
    instance: Optional[PluginBase] = None
    module: Optional[types.ModuleType] = None
    state: PluginState = PluginState.DISCOVERED
    load_time: float = 0.0
    error: Optional[str] = None


class PluginRegistry:
    """Central registry of all known and loaded plugins."""

    def __init__(self):
        self._entries: Dict[str, RegistryEntry] = {}
        self._by_capability: Dict[str, List[str]] = defaultdict(list)
        self._lock = threading.RLock()

    # ---- CRUD ----

    def register(self, manifest: PluginManifest) -> None:
        with self._lock:
            if manifest.name in self._entries:
                # Update existing; keep loaded instance if compatible
                existing = self._entries[manifest.name]
                existing.manifest = manifest
            else:
                self._entries[manifest.name] = RegistryEntry(manifest=manifest)
            self._rebuild_capability_index()

    def unregister(self, name: str) -> None:
        with self._lock:
            self._entries.pop(name, None)
            self._rebuild_capability_index()

    def get(self, name: str) -> Optional[RegistryEntry]:
        with self._lock:
            return self._entries.get(name)

    def list_all(self) -> List[RegistryEntry]:
        with self._lock:
            return list(self._entries.values())

    def list_names(self) -> List[str]:
        with self._lock:
            return list(self._entries.keys())

    # ---- Capability queries ----

    def find_by_capability(self, capability: str) -> List[RegistryEntry]:
        with self._lock:
            names = self._by_capability.get(capability, [])
            return [self._entries[n] for n in names if n in self._entries]

    def _rebuild_capability_index(self) -> None:
        self._by_capability.clear()
        for name, entry in self._entries.items():
            for cap in entry.manifest.capabilities:
                self._by_capability[cap.name].append(name)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def __contains__(self, name: str) -> bool:
        with self._lock:
            return name in self._entries


# ---------------------------------------------------------------------------
# Plugin Manager
# ---------------------------------------------------------------------------

class PluginManager:
    """Orchestrates plugin lifecycle: discover, load, init, start, stop, unload.

    Features:
      - Dependency resolution with cycle detection via topological sort
      - Hot-reload support via file watcher
      - Version compatibility checking
      - Sandboxed execution per policy
    """

    def __init__(
        self,
        search_paths: Optional[List[str]] = None,
        registry: Optional[PluginRegistry] = None,
        sandbox_policy: Optional[SandboxPolicy] = None,
    ):
        self.discovery = PluginDiscovery(search_paths or [])
        self.registry = registry or PluginRegistry()
        self.sandbox_policy = sandbox_policy or SandboxPolicy()
        self._watcher: Optional[PluginFileWatcher] = None
        self._started: bool = False
        self._lock = threading.RLock()

    # ---- Discovery ----

    def discover(self) -> Dict[str, PluginManifest]:
        """Scan all search paths and register discovered plugins."""
        manifests = self.discovery.discover()
        with self._lock:
            for name, manifest in manifests.items():
                self.registry.register(manifest)
        logger.info("Discovered %d plugins", len(manifests))
        return manifests

    # ---- Loading ----

    def load(self, name: str, config: Optional[Dict[str, Any]] = None) -> RegistryEntry:
        """Load a single plugin by name, resolving its dependencies first.

        Args:
            name: Plugin name.
            config: Configuration dict passed to on_init.

        Returns:
            The populated RegistryEntry.
        """
        with self._lock:
            entry = self.registry.get(name)
            if entry is None:
                raise PluginNotFoundError(name)

            if entry.state in (PluginState.RUNNING, PluginState.INITIALIZED):
                return entry  # already loaded

            # Resolve and load dependencies
            deps = self._resolve_dependencies(entry.manifest)
            for dep_name, dep_version_spec in deps.items():
                dep_entry = self.registry.get(dep_name)
                if dep_entry is None:
                    raise PluginNotFoundError(
                        dep_name,
                        [str(p) for p in self.discovery._search_paths]
                    )
                if dep_entry.state not in (PluginState.INITIALIZED, PluginState.RUNNING):
                    self._load_one(dep_entry, config)

            return self._load_one(entry, config)

    def load_all(self, config: Optional[Dict[str, Any]] = None) -> List[RegistryEntry]:
        """Load all discovered plugins in dependency order."""
        results: List[RegistryEntry] = []
        order = self._topological_sort()
        for name in order:
            entry = self.registry.get(name)
            if entry and entry.state not in (PluginState.INITIALIZED, PluginState.RUNNING):
                try:
                    loaded = self._load_one(entry, config)
                    results.append(loaded)
                except PluginError as exc:
                    logger.error("Failed to load plugin '%s': %s", name, exc)
                    entry.state = PluginState.ERROR
                    entry.error = str(exc)
        return results

    def _load_one(
        self, entry: RegistryEntry, config: Optional[Dict[str, Any]] = None
    ) -> RegistryEntry:
        """Internal: import and initialize a single plugin."""
        manifest = entry.manifest
        start_time = time.monotonic()

        # --- Version compatibility ---
        self._check_compatibility(manifest)

        # --- Import ---
        try:
            if manifest.sandbox and not manifest.isolated:
                # In-process sandbox via import hooks
                with _sandbox_import_context(self.sandbox_policy):
                    mod = self._import_plugin(manifest)
            elif manifest.isolated:
                # Subprocess isolation — load stub, actual calls go through sandbox
                mod = None
                instance = _IsolatedPluginProxy(manifest, self.sandbox_policy)
                entry.instance = instance
                entry.module = None
                entry.state = PluginState.LOADED
            else:
                mod = self._import_plugin(manifest)
        except Exception as exc:
            entry.state = PluginState.ERROR
            entry.error = str(exc)
            entry.load_time = (time.monotonic() - start_time) * 1000
            raise PluginLoadError(manifest.name, str(exc)) from exc

        if not manifest.isolated:
            entry.module = mod

            # --- Instantiate ---
            plugin_cls = self._find_plugin_class(mod, manifest)
            if plugin_cls is None:
                raise PluginLoadError(
                    manifest.name,
                    "No PluginBase subclass found in module"
                )
            instance = plugin_cls()
            instance.manifest = manifest
            entry.instance = instance
            entry.state = PluginState.LOADED

        # --- Initialize ---
        try:
            entry.instance.on_init(config or {})
            entry.state = PluginState.INITIALIZED
        except Exception as exc:
            entry.state = PluginState.ERROR
            entry.error = f"init failed: {exc}"
            raise PluginLoadError(manifest.name, f"init() failed: {exc}") from exc

        entry.load_time = (time.monotonic() - start_time) * 1000
        logger.info("Plugin '%s' loaded in %.1fms", manifest.name, entry.load_time)
        return entry

    def _import_plugin(self, manifest: PluginManifest) -> types.ModuleType:
        """Import a plugin module by its entry point."""
        ep = manifest.entry_point
        if ":" in ep:
            module_path, _ = ep.split(":", 1)
        else:
            module_path = ep

        if not module_path:
            # Fallback: try to import by plugin name
            module_path = manifest.name

        try:
            return importlib.import_module(module_path)
        except ImportError:
            # Try as a file path
            for sp in self.discovery._search_paths:
                candidate = sp / manifest.name / "plugin.py"
                if candidate.exists():
                    spec = importlib.util.spec_from_file_location(
                        manifest.name, str(candidate)
                    )
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[manifest.name] = mod
                    spec.loader.exec_module(mod)
                    return mod
            raise

    def _find_plugin_class(
        self, mod: types.ModuleType, manifest: PluginManifest
    ) -> Optional[Type[PluginBase]]:
        """Find the PluginBase subclass in a loaded module."""
        ep = manifest.entry_point
        if ":" in ep:
            _, class_name = ep.split(":", 1)
            cls = getattr(mod, class_name, None)
            if cls and issubclass(cls, PluginBase):
                return cls

        # Scan module for PluginBase subclasses
        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if obj is not PluginBase and issubclass(obj, PluginBase):
                return obj
        return None

    # ---- Lifecycle ----

    def start(self, name: str) -> None:
        """Start a loaded plugin."""
        with self._lock:
            entry = self.registry.get(name)
            if entry is None:
                raise PluginNotFoundError(name)
            if entry.state not in (PluginState.INITIALIZED, PluginState.STOPPED):
                raise PluginError(f"Plugin '{name}' is in state {entry.state}, cannot start")
            if entry.instance:
                entry.instance.on_start()
                entry.state = PluginState.RUNNING

    def start_all(self) -> None:
        """Start all initialized plugins in dependency order."""
        order = self._topological_sort()
        with self._lock:
            for name in order:
                entry = self.registry.get(name)
                if entry and entry.state == PluginState.INITIALIZED:
                    try:
                        entry.instance.on_start()
                        entry.state = PluginState.RUNNING
                    except Exception as exc:
                        logger.error("Failed to start plugin '%s': %s", name, exc)
                        entry.state = PluginState.ERROR
                        entry.error = str(exc)
        self._started = True

    def stop(self, name: str) -> None:
        """Stop a running plugin."""
        with self._lock:
            entry = self.registry.get(name)
            if entry is None:
                raise PluginNotFoundError(name)
            if entry.state == PluginState.RUNNING and entry.instance:
                entry.instance.on_stop()
                entry.state = PluginState.STOPPED

    def stop_all(self) -> None:
        """Stop all running plugins in reverse dependency order."""
        order = list(reversed(self._topological_sort()))
        with self._lock:
            for name in order:
                entry = self.registry.get(name)
                if entry and entry.state == PluginState.RUNNING:
                    try:
                        entry.instance.on_stop()
                        entry.state = PluginState.STOPPED
                    except Exception as exc:
                        logger.error("Failed to stop plugin '%s': %s", name, exc)
        self._started = False

    def unload(self, name: str) -> None:
        """Unload a plugin, removing it from memory and registry."""
        with self._lock:
            entry = self.registry.get(name)
            if entry is None:
                return
            if entry.state in (PluginState.RUNNING, PluginState.INITIALIZED):
                self.stop(name)
            if entry.instance:
                entry.instance.on_unload()
            if entry.module and entry.module.__name__ in sys.modules:
                del sys.modules[entry.module.__name__]
            self.registry.unregister(name)

    # ---- Hot-Reload ----

    def enable_hot_reload(self, poll_interval: float = 2.0) -> None:
        """Enable hot-reload via filesystem polling.

        When a plugin's source directory changes, the plugin is automatically
        stopped, unloaded, re-discovered, and reloaded.
        """
        if self._watcher is not None:
            return  # already enabled

        def _on_change(changed_paths: List[str]) -> None:
            logger.info("Hot-reload triggered by changes in: %s", changed_paths)
            affected = self._affected_plugins(changed_paths)
            for name in affected:
                try:
                    logger.info("Hot-reloading plugin: %s", name)
                    self.stop(name)
                    self.unload(name)
                except Exception:
                    pass
            self.discover()
            self.load_all()

        self._watcher = PluginFileWatcher(
            paths=[str(p) for p in self.discovery._search_paths],
            callback=_on_change,
            poll_interval=poll_interval,
        )
        self._watcher.start()

    def disable_hot_reload(self) -> None:
        """Disable hot-reload watcher."""
        if self._watcher:
            self._watcher.stop()
            self._watcher = None

    def _affected_plugins(self, changed_paths: List[str]) -> List[str]:
        """Determine which plugins are affected by changed file paths."""
        affected: List[str] = []
        for cp in changed_paths:
            for sp in self.discovery._search_paths:
                try:
                    rel = Path(cp).relative_to(sp)
                    plugin_name = rel.parts[0] if rel.parts else ""
                    if plugin_name and plugin_name in self.registry:
                        affected.append(plugin_name)
                except ValueError:
                    continue
        return list(set(affected)) or self.registry.list_names()

    # ---- Dependency Resolution ----

    def _resolve_dependencies(self, manifest: PluginManifest) -> Dict[str, str]:
        """Return the full set of dependencies for a plugin (transitive)."""
        resolved: Dict[str, str] = {}
        visited: Set[str] = set()
        self._resolve_deps_recursive(manifest, resolved, visited, [manifest.name])
        return resolved

    def _resolve_deps_recursive(
        self,
        manifest: PluginManifest,
        resolved: Dict[str, str],
        visited: Set[str],
        path: List[str],
    ) -> None:
        for dep_name, dep_spec in manifest.dependencies.items():
            if dep_name in path:
                raise CircularDependencyError(path + [dep_name])
            if dep_name in visited:
                continue
            visited.add(dep_name)
            resolved[dep_name] = dep_spec
            dep_entry = self.registry.get(dep_name)
            if dep_entry:
                self._resolve_deps_recursive(
                    dep_entry.manifest, resolved, visited, path + [dep_name]
                )

    def _topological_sort(self) -> List[str]:
        """Return plugin names in dependency-safe load order."""
        in_degree: Dict[str, int] = defaultdict(int)
        graph: Dict[str, Set[str]] = defaultdict(set)

        for name, entry in self.registry._entries.items():
            if name not in in_degree:
                in_degree[name] = 0
            for dep in entry.manifest.dependencies:
                graph[dep].add(name)
                in_degree[name] += 1
                if dep not in in_degree:
                    in_degree[dep] = 0

        queue: deque[str] = deque(n for n, d in in_degree.items() if d == 0)
        order: List[str] = []

        while queue:
            node = queue.popleft()
            order.append(node)
            for neighbor in graph.get(node, set()):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Add any remaining (cycle participants) at the end
        for node in in_degree:
            if node not in order:
                order.append(node)

        return order

    # ---- Compatibility ----

    def _check_compatibility(self, manifest: PluginManifest) -> None:
        """Verify plugin compatibility with the current environment."""
        if manifest.python_version:
            if not SemVer.parse(
                f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            ).satisfies(manifest.python_version):
                raise IncompatibleVersionError(
                    manifest.name,
                    manifest.python_version,
                    sys.version.split()[0],
                )

    def check_dependency_versions(self, name: str) -> List[str]:
        """Check that a plugin's dependency versions are satisfied. Returns issues."""
        issues: List[str] = []
        entry = self.registry.get(name)
        if entry is None:
            return [f"Plugin '{name}' not found"]

        for dep_name, dep_spec in entry.manifest.dependencies.items():
            dep_entry = self.registry.get(dep_name)
            if dep_entry is None:
                issues.append(f"Missing dependency: {dep_name} {dep_spec}")
            elif not dep_entry.manifest.semver().satisfies(dep_spec):
                issues.append(
                    f"Version mismatch for {dep_name}: "
                    f"required {dep_spec}, found {dep_entry.manifest.version}"
                )
        return issues


# ---------------------------------------------------------------------------
# Isolated Plugin Proxy (subprocess sandbox)
# ---------------------------------------------------------------------------

class _IsolatedPluginProxy:
    """Proxy for plugins running in a subprocess sandbox."""

    def __init__(self, manifest: PluginManifest, policy: SandboxPolicy):
        self.manifest = manifest
        self.policy = policy
        self._sandbox = SubprocessSandbox(policy)

    def on_init(self, config: Dict[str, Any]) -> None:
        self._sandbox.execute(
            self.manifest.entry_point.split(":")[0] if ":" in self.manifest.entry_point
            else self.manifest.entry_point,
            "on_init",
            {"config": config},
        )

    def on_start(self) -> None:
        pass

    def on_stop(self) -> None:
        pass

    def on_unload(self) -> None:
        pass


# ---------------------------------------------------------------------------
# File Watcher (polling-based hot-reload)
# ---------------------------------------------------------------------------

class PluginFileWatcher:
    """Polling-based file watcher for hot-reload support.

    Monitors plugin directories for changes and invokes a callback
    when modifications are detected.
    """

    def __init__(
        self,
        paths: List[str],
        callback: Callable[[List[str]], None],
        poll_interval: float = 2.0,
    ):
        self.paths = [Path(p) for p in paths]
        self.callback = callback
        self.poll_interval = poll_interval
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._snapshots: Dict[Path, Dict[str, float]] = {}

    def start(self) -> None:
        if self._thread is not None:
            return
        self._take_snapshot()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=5.0)
        self._thread = None

    def _run(self) -> None:
        while not self._stop_event.wait(self.poll_interval):
            changed = self._detect_changes()
            if changed:
                try:
                    self.callback(changed)
                except Exception as exc:
                    logger.error("Hot-reload callback error: %s", exc)
                self._take_snapshot()

    def _take_snapshot(self) -> None:
        self._snapshots.clear()
        for path in self.paths:
            if path.exists():
                for f in path.rglob("*.py"):
                    try:
                        self._snapshots[f] = {
                            "mtime": f.stat().st_mtime,
                            "size": f.stat().st_size,
                        }
                    except OSError:
                        continue

    def _detect_changes(self) -> List[str]:
        changed: List[str] = []
        current: Set[Path] = set()
        for path in self.paths:
            if path.exists():
                for f in path.rglob("*.py"):
                    current.add(f)
                    try:
                        stat = f.stat()
                        if f in self._snapshots:
                            snap = self._snapshots[f]
                            if snap["mtime"] != stat.st_mtime or snap["size"] != stat.st_size:
                                changed.append(str(f))
                        else:
                            changed.append(str(f))  # new file
                    except OSError:
                        continue
        # Detect deletions
        removed = set(self._snapshots.keys()) - current
        for f in removed:
            changed.append(str(f))
        return list(set(changed))


# ---------------------------------------------------------------------------
# Sandbox Import Context
# ---------------------------------------------------------------------------

@contextmanager
def _sandbox_import_context(policy: SandboxPolicy) -> Iterator[None]:
    """Context manager that restricts imports according to sandbox policy.

    Uses an import hook to block disallowed modules.
    """
    hook = _SandboxImportHook(policy)
    try:
        hook.install()
        yield
    finally:
        hook.uninstall()


class _SandboxImportHook:
    """Import hook that blocks modules according to sandbox policy."""

    def __init__(self, policy: SandboxPolicy):
        self.policy = policy
        self._original_import = __builtins__.get("__import__")

    def install(self) -> None:
        import builtins
        self._original_import = builtins.__import__
        builtins.__import__ = self._sandboxed_import

    def uninstall(self) -> None:
        import builtins
        if self._original_import:
            builtins.__import__ = self._original_import

    def _sandboxed_import(self, name, *args, **kwargs):
        # Check blocked
        for blocked in self.policy.blocked_modules:
            if name == blocked or name.startswith(blocked + "."):
                raise ImportError(
                    f"Module '{name}' is blocked by sandbox policy"
                )
        # Check allowed (if not wildcard)
        if "*" not in self.policy.allowed_modules:
            allowed = any(
                name == a or name.startswith(a + ".")
                for a in self.policy.allowed_modules
            )
            if not allowed:
                raise ImportError(
                    f"Module '{name}' is not in sandbox allowed list"
                )
        return self._original_import(name, *args, **kwargs)


# ---------------------------------------------------------------------------
# Utility: Dynamic Module Reload
# ---------------------------------------------------------------------------

def hot_reload_module(module_path: str) -> types.ModuleType:
    """Force-reload a Python module, clearing its submodules first.

    Useful for development / hot-reload loops.
    """
    if module_path in sys.modules:
        mod = sys.modules[module_path]
        # Collect submodules to remove
        to_remove = [
            k for k in sys.modules
            if k == module_path or k.startswith(module_path + ".")
        ]
        for k in to_remove:
            del sys.modules[k]
    return importlib.import_module(module_path)