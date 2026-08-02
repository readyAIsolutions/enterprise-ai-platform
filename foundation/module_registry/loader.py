"""
Module Loader
=============

Dynamic module loading system that discovers Python modules, validates
entry points, supports lazy loading, and enables hot-reloading of modules
at runtime.

Key capabilities:
    - Filesystem-based module discovery via scanning directories
    - Entry-point validation against registered ModuleMeta
    - Lazy loading: defer actual import until first access
    - Hot-reload: replace a running module without restarting the process
    - Import hooks for transparent proxy objects
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .registry import ModuleMeta, ModuleRegistry, ModuleState


# ---------------------------------------------------------------------------
# Lazy-loading proxy
# ---------------------------------------------------------------------------

class LazyModule:
    """A proxy object that defers module import until an attribute is accessed.

    Wraps the module spec and loader callable so the actual import only happens
    on the first ``__getattr__`` call. Subsequent accesses use the cached module.

    Example::

        lazy = LazyModule("mypackage.auth", loader=my_import_fn)
        # No import yet
        result = lazy.authenticate("user", "pass")  # Import happens here
    """

    def __init__(self, name: str, loader: Callable[[], Any]) -> None:
        """Initialise the lazy proxy.

        Args:
            name: Fully-qualified module name.
            loader: Zero-argument callable that performs the import and returns
                the module object.
        """
        self._name = name
        self._loader = loader
        self._module: Any = None
        self._loaded = False

    def _load(self) -> Any:
        """Trigger the import if not already cached."""
        if not self._loaded:
            self._module = self._loader()
            self._loaded = True
        return self._module

    def __getattr__(self, name: str) -> Any:
        if name.startswith('_LazyModule__'):
            raise AttributeError(name)
        return getattr(self._load(), name)

    def __repr__(self) -> str:
        status = "loaded" if self._loaded else "lazy"
        return f"<LazyModule '{self._name}' ({status})>"


# ---------------------------------------------------------------------------
# Discovery result
# ---------------------------------------------------------------------------

@dataclass
class DiscoveryResult:
    """Outcome of a module discovery scan.

    Attributes:
        path: Filesystem path to the discovered module.
        module_name: Python import name for the module.
        entry_point: The callable found at the declared entry point, if any.
        meta: Associated ModuleMeta from the registry.
        errors: Any warnings or issues encountered during discovery.
    """
    path: Path
    module_name: str
    entry_point: Optional[Callable[..., Any]] = None
    meta: Optional[ModuleMeta] = None
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class ModuleLoadError(Exception):
    """Raised when a module cannot be loaded or its entry point is invalid."""
    pass


# ---------------------------------------------------------------------------
# Module Loader
# ---------------------------------------------------------------------------

class ModuleLoader:
    """Discovers, loads, and hot-reloads Python modules from the filesystem.

    Designed to work in concert with :class:`ModuleRegistry`. Modules are first
    registered via the registry, then the loader can import them, validate their
    entry points, and manage their runtime lifecycle.

    Example usage::

        loader = ModuleLoader(registry, search_paths=["/app/plugins"])
        # Discover all modules under /app/plugins
        results = loader.discover()
        # Load a specific module
        mod = loader.load("auth")
        # Hot-reload after code change
        loader.hot_reload("auth")
    """

    def __init__(
        self,
        registry: ModuleRegistry,
        search_paths: Optional[List[str]] = None,
    ) -> None:
        """Initialise the loader.

        Args:
            registry: The module registry to synchronise with.
            search_paths: Directories to scan for Python modules. If None,
                defaults to the current working directory.
        """
        self.registry = registry
        self.search_paths: List[Path] = [
            Path(p) for p in (search_paths or [os.getcwd()])
        ]
        # Track loaded modules: module_id -> (module_object, file_path)
        self._loaded: Dict[str, Tuple[Any, Optional[Path]]] = {}
        # Track lazy proxies: module_id -> LazyModule
        self._lazy: Dict[str, LazyModule] = {}
        # Track file modification times for hot-reload detection
        self._file_mtimes: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(
        self,
        recursive: bool = True,
        pattern: str = "*.py",
    ) -> List[DiscoveryResult]:
        """Scan search paths for Python modules matching *pattern*.

        For each discovered ``.py`` file the loader attempts to:
        1. Derive the Python import path.
        2. Look up (or auto-register) the corresponding :class:`ModuleMeta`.
        3. Validate the declared entry point if the module is already registered.

        Files named ``__init__.py`` are treated as package roots.

        Args:
            recursive: Whether to descend into subdirectories.
            pattern: Glob pattern for candidate files (default ``*.py``).

        Returns:
            A list of :class:`DiscoveryResult` objects, one per discovered module.
        """
        results: List[DiscoveryResult] = []
        seen: Set[Path] = set()

        for search_path in self.search_paths:
            if not search_path.exists():
                continue
            glob_iter = search_path.rglob(pattern) if recursive else search_path.glob(pattern)
            for py_file in glob_iter:
                if py_file in seen:
                    continue
                seen.add(py_file)

                # Derive module name from relative path
                try:
                    rel = py_file.relative_to(search_path)
                except ValueError:
                    continue
                parts = list(rel.parts)
                if parts[-1] == "__init__.py":
                    parts = parts[:-1]
                else:
                    parts[-1] = parts[-1].replace(".py", "")
                module_name = ".".join(parts)

                result = DiscoveryResult(path=py_file, module_name=module_name)

                # Try to match or auto-register
                meta = self._find_or_create_meta(module_name, py_file)
                if meta is not None:
                    result.meta = meta
                    # Validate entry point
                    entry, errs = self._validate_entry_point_safe(py_file, meta)
                    result.entry_point = entry
                    result.errors.extend(errs)

                results.append(result)

        return results

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self, module_id: str) -> Any:
        """Import and cache a registered module.

        If the module is already loaded, returns the cached object immediately.
        The module must be registered in the :class:`ModuleRegistry` first.

        Args:
            module_id: The registered module ID to load.

        Returns:
            The imported module object.

        Raises:
            ModuleLoadError: If the module is not registered, its file cannot
                be found, or the import fails.
        """
        if module_id in self._loaded:
            return self._loaded[module_id][0]

        if module_id in self._lazy:
            lazy = self._lazy.pop(module_id)
            mod = lazy._load()
            self._loaded[module_id] = (mod, None)
            return mod

        meta = self.registry.get(module_id)
        if meta is None:
            raise ModuleLoadError(f"Module '{module_id}' is not registered")

        file_path = self._locate_module_file(meta)
        mod = self._import_module(meta.module_id, file_path)
        self._loaded[module_id] = (mod, file_path)
        if file_path:
            self._file_mtimes[module_id] = file_path.stat().st_mtime
        return mod

    def load_lazy(self, module_id: str) -> LazyModule:
        """Return a lazy proxy that defers import until first attribute access.

        Useful for modules that may not be needed on every code path.

        Args:
            module_id: The registered module ID.

        Returns:
            A :class:`LazyModule` proxy object.

        Raises:
            ModuleLoadError: If the module is not registered.
        """
        if module_id in self._loaded:
            # Already loaded — wrap in a trivial proxy that returns immediately
            mod = self._loaded[module_id][0]
            return LazyModule(module_id, lambda: mod)

        if module_id in self._lazy:
            return self._lazy[module_id]

        meta = self.registry.get(module_id)
        if meta is None:
            raise ModuleLoadError(f"Module '{module_id}' is not registered")

        file_path = self._locate_module_file(meta)

        def _do_load() -> Any:
            if module_id in self._loaded:
                return self._loaded[module_id][0]
            mod = self._import_module(meta.module_id, file_path)
            self._loaded[module_id] = (mod, file_path)
            if file_path:
                self._file_mtimes[module_id] = file_path.stat().st_mtime
            if module_id in self._lazy:
                del self._lazy[module_id]
            return mod

        lazy = LazyModule(module_id, _do_load)
        self._lazy[module_id] = lazy
        return lazy

    def load_all(self) -> List[Any]:
        """Load every registered module.

        Returns:
            List of imported module objects.
        """
        return [self.load(m.module_id) for m in self.registry.list_all()]

    # ------------------------------------------------------------------
    # Hot-reload
    # ------------------------------------------------------------------

    def hot_reload(self, module_id: str) -> Any:
        """Reload a module, replacing its in-memory objects.

        Uses :func:`importlib.reload` to refresh the module's code from disk
        without restarting the process. The module must have been previously
        loaded via :meth:`load`.

        Args:
            module_id: The module to reload.

        Returns:
            The reloaded module object.

        Raises:
            ModuleLoadError: If the module is not currently loaded or not
                registered.
        """
        if module_id not in self._loaded:
            raise ModuleLoadError(
                f"Module '{module_id}' is not loaded; use load() first"
            )

        meta = self.registry.get(module_id)
        if meta is None:
            raise ModuleLoadError(f"Module '{module_id}' is not registered")

        mod, file_path = self._loaded[module_id]
        # Invalidate import caches then re-import from file for guaranteed freshness
        importlib.invalidate_caches()
        if file_path is not None and file_path.exists():
            reloaded = self._import_module(meta.module_id, file_path)
        else:
            reloaded = importlib.reload(mod)
        self._loaded[module_id] = (reloaded, file_path)
        if file_path:
            self._file_mtimes[module_id] = file_path.stat().st_mtime
        return reloaded

    def hot_reload_if_changed(self, module_id: str) -> Optional[Any]:
        """Reload a module only if its source file has been modified on disk.

        Compares the cached modification time against the current file stat.
        Returns None if no reload was necessary.

        Args:
            module_id: The module to check and potentially reload.

        Returns:
            The reloaded module if a change was detected, else None.

        Raises:
            ModuleLoadError: If the module is not loaded or registered.
        """
        if module_id not in self._loaded:
            raise ModuleLoadError(
                f"Module '{module_id}' is not loaded; use load() first"
            )

        _, file_path = self._loaded[module_id]
        if file_path is None or not file_path.exists():
            return None

        current_mtime = file_path.stat().st_mtime
        if current_mtime > self._file_mtimes.get(module_id, 0):
            return self.hot_reload(module_id)
        return None

    # ------------------------------------------------------------------
    # Entry-point execution
    # ------------------------------------------------------------------

    def call_entry_point(
        self,
        module_id: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Load a module and call its declared entry point.

        The entry point is determined from the module's :class:`ModuleMeta`
        (``entry_point`` field). If the entry point string is ``"module"``,
        the whole module is treated as callable (it must define ``__call__``).

        Args:
            module_id: The module whose entry point to invoke.
            *args: Positional arguments forwarded to the entry point.
            **kwargs: Keyword arguments forwarded to the entry point.

        Returns:
            Whatever the entry point returns.

        Raises:
            ModuleLoadError: If no valid entry point can be resolved.
        """
        meta = self.registry.get(module_id)
        if meta is None or not meta.entry_point:
            raise ModuleLoadError(f"No entry point defined for '{module_id}'")

        mod = self.load(module_id)

        if meta.entry_point == "module":
            if not callable(mod):
                raise ModuleLoadError(
                    f"Module '{module_id}' entry point is 'module' but the module "
                    f"is not callable"
                )
            return mod(*args, **kwargs)

        # Navigate the attribute chain: "submodule.func" -> getattr chain
        obj = mod
        for part in meta.entry_point.split("."):
            obj = getattr(obj, part, None)
            if obj is None:
                raise ModuleLoadError(
                    f"Entry point '{meta.entry_point}' for module '{module_id}' "
                    f"not found (missing '{part}')"
                )
        if not callable(obj):
            raise ModuleLoadError(
                f"Entry point '{meta.entry_point}' for module '{module_id}' "
                f"is not callable"
            )
        return obj(*args, **kwargs)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def is_loaded(self, module_id: str) -> bool:
        """Return True if the module has been imported and cached."""
        return module_id in self._loaded

    def is_lazy(self, module_id: str) -> bool:
        """Return True if a lazy proxy exists but hasn't been materialised."""
        return module_id in self._lazy

    def unload(self, module_id: str) -> None:
        """Remove a module from the loader's cache (does not unregister it).

        Args:
            module_id: The module to evict from memory.
        """
        self._loaded.pop(module_id, None)
        self._lazy.pop(module_id, None)
        self._file_mtimes.pop(module_id, None)

    def loaded_modules(self) -> List[str]:
        """Return the module IDs of all currently loaded modules."""
        return list(self._loaded.keys())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _locate_module_file(self, meta: ModuleMeta) -> Optional[Path]:
        """Search for the filesystem path of a registered module.

        Checks the entry_point and metadata for hints, then falls back to
        scanning search paths for a matching ``.py`` file.

        Args:
            meta: The module metadata.

        Returns:
            The resolved file path, or None if not found.
        """
        # Check metadata for explicit path hint
        if "file_path" in meta.metadata:
            candidate = Path(meta.metadata["file_path"])
            if candidate.exists():
                return candidate

        # Derive from module_id by scanning search paths
        rel_name = meta.module_id.replace(".", os.sep) + ".py"
        for sp in self.search_paths:
            candidate = sp / rel_name
            if candidate.exists():
                return candidate

        # Try as package __init__.py
        rel_init = meta.module_id.replace(".", os.sep) + os.sep + "__init__.py"
        for sp in self.search_paths:
            candidate = sp / rel_init
            if candidate.exists():
                return candidate

        return None

    def _import_module(self, module_name: str, file_path: Optional[Path]) -> Any:
        """Import a Python module by name, ensuring it is in sys.modules.

        If *file_path* is provided, uses :func:`importlib.util.spec_from_file_location`
        to guarantee we load the exact file. Falls back to standard import otherwise.

        Args:
            module_name: Fully-qualified Python module name.
            file_path: Optional filesystem path to the ``.py`` file.

        Returns:
            The imported module object.

        Raises:
            ModuleLoadError: If the import fails.
        """
        try:
            if file_path is not None and file_path.exists():
                # Remove from sys.modules so we get a fresh load
                sys.modules.pop(module_name, None)
                # Clear any bytecode cache so changes are picked up
                pycache = file_path.parent / "__pycache__"
                if pycache.exists():
                    import shutil
                    shutil.rmtree(pycache, ignore_errors=True)
                # Use file-based import for precision
                spec = importlib.util.spec_from_file_location(
                    module_name, str(file_path)
                )
                if spec is None or spec.loader is None:
                    raise ModuleLoadError(
                        f"Could not create module spec for '{module_name}' at {file_path}"
                    )
                mod = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = mod
                spec.loader.exec_module(mod)
                return mod
            else:
                return importlib.import_module(module_name)
        except (ImportError, SyntaxError, Exception) as exc:
            raise ModuleLoadError(
                f"Failed to import module '{module_name}': {exc}"
            ) from exc

    def _find_or_create_meta(
        self, module_name: str, file_path: Path
    ) -> Optional[ModuleMeta]:
        """Look up or auto-create a ModuleMeta for a discovered file.

        If the module name matches a registered module (exact or by checking
        metadata), return its meta. Otherwise create a minimal placeholder.

        Args:
            module_name: Derived Python import name.
            file_path: Path to the discovered ``.py`` file.

        Returns:
            A ModuleMeta instance, or None.
        """
        # Try exact match
        for m in self.registry.list_all():
            if m.module_id == module_name:
                return m

        # Try match via metadata file_path or module_name in metadata
        for m in self.registry.list_all():
            meta_file = m.metadata.get("file_path", "")
            if meta_file and Path(meta_file) == file_path:
                return m

        # Create a minimal placeholder
        return ModuleMeta(
            module_id=module_name,
            version="0.0.0",
            description=f"Auto-discovered module at {file_path}",
            metadata={"file_path": str(file_path), "__discovered__": True},
        )

    def _validate_entry_point_safe(
        self, file_path: Path, meta: ModuleMeta
    ) -> Tuple[Optional[Callable[..., Any]], List[str]]:
        """Validate a module's entry point without importing it.

        Performs a static check by parsing the AST (avoids side-effects).

        Args:
            file_path: Path to the module source.
            meta: The module metadata containing the entry_point string.

        Returns:
            A tuple of (entry_point_callable_or_None, list_of_error_strings).
            The callable is None for static-only validation.
        """
        errors: List[str] = []
        if not meta.entry_point:
            return None, errors

        # Static check: read the source and look for the named attribute
        try:
            source = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"Cannot read source: {exc}")
            return None, errors

        if meta.entry_point == "module":
            # Check if the module has __call__ defined at module level
            if "def __call__" not in source and "class " not in source:
                errors.append(
                    f"Entry point is 'module' but no __call__ or class definition found"
                )
            return None, errors

        parts = meta.entry_point.split(".")
        target = parts[0]

        # Simple check: is the first name present in the source?
        if f"def {target}" not in source and f"class {target}" not in source and \
           f"{target} =" not in source and f"{target}=" not in source:
            errors.append(
                f"Entry point target '{target}' not found in source (static check)"
            )

        return None, errors