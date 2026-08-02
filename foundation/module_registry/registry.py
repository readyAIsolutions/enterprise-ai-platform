"""
Module Registry
===============

Core module registry providing module tracking, dependency resolution,
version management, and lifecycle control for the enterprise system.

Key capabilities:
    - Module registration with inputs, outputs, dependencies, and permissions
    - Topological sort for correct dependency ordering
    - Enable/disable toggling with dependency awareness
    - Version tracking and semantic version comparison
    - Activation condition evaluation
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Optional, Set, Tuple


class ModuleState(Enum):
    """Lifecycle states for a registered module."""
    REGISTERED = "registered"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ACTIVE = "active"
    ERROR = "error"


class ActivationCondition(Enum):
    """Types of conditions required before a module can activate."""
    ALWAYS = "always"                 # Activate unconditionally
    DEPENDENCIES_READY = "dep_ready"  # All dependencies must be active
    ON_DEMAND = "on_demand"           # Only when explicitly requested
    CONDITIONAL = "conditional"       # Evaluated via a custom callable
    NEVER = "never"                   # Never auto-activate (manual only)


@dataclass
class ModulePermission:
    """Permission definition for a module.

    Attributes:
        name: Unique permission identifier (e.g. 'read:config', 'write:filesystem')
        description: Human-readable description of what the permission grants
        category: Broad grouping for the permission (e.g. 'io', 'network', 'admin')
        level: Severity/risk level from 0 (safe) to 10 (critical)
    """
    name: str
    description: str = ""
    category: str = "general"
    level: int = 0

    def __post_init__(self) -> None:
        if self.level < 0 or self.level > 10:
            raise ValueError(f"Permission level must be between 0 and 10, got {self.level}")

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ModulePermission):
            return NotImplemented
        return self.name == other.name


@dataclass
class ModuleMeta:
    """Metadata descriptor for a module registered in the system.

    Attributes:
        module_id: Unique module identifier (e.g. 'auth', 'logging', 'database')
        version: Semantic version string (e.g. '1.2.3')
        display_name: Human-readable module name
        description: Module purpose and behaviour summary
        author: Module author or maintainer
        state: Current lifecycle state of the module
        dependencies: Set of module IDs this module depends on
        inputs: Data inputs consumed by this module
        outputs: Data outputs produced by this module
        permissions: Permissions required by this module
        required_permissions: Permissions that must be granted (subset of permissions)
        activation_condition: When the module should be activated
        activation_callable: Custom callable for CONDITIONAL activation
        entry_point: Python import path for the module's main class/function
        metadata: Arbitrary key-value metadata
    """
    module_id: str
    version: str = "0.1.0"
    display_name: str = ""
    description: str = ""
    author: str = ""
    state: ModuleState = ModuleState.REGISTERED
    dependencies: FrozenSet[str] = field(default_factory=frozenset)
    inputs: FrozenSet[str] = field(default_factory=frozenset)
    outputs: FrozenSet[str] = field(default_factory=frozenset)
    permissions: FrozenSet[ModulePermission] = field(default_factory=frozenset)
    required_permissions: FrozenSet[str] = field(default_factory=frozenset)
    activation_condition: ActivationCondition = ActivationCondition.ALWAYS
    activation_callable: Optional[Callable[[], bool]] = None
    entry_point: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', self.module_id):
            raise ValueError(
                f"Invalid module_id '{self.module_id}': must be a valid Python identifier"
            )
        if self.activation_condition == ActivationCondition.CONDITIONAL and self.activation_callable is None:
            raise ValueError(
                f"Module '{self.module_id}': CONDITIONAL activation requires an activation_callable"
            )
        # Validate required_permissions are a subset of permissions
        perm_names = frozenset(p.name for p in self.permissions)
        for rp in self.required_permissions:
            if rp not in perm_names:
                raise ValueError(
                    f"Module '{self.module_id}': required_permission '{rp}' not in declared permissions"
                )

    def __hash__(self) -> int:
        return hash(self.module_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ModuleMeta):
            return NotImplemented
        return self.module_id == other.module_id

    @property
    def version_tuple(self) -> Tuple[int, ...]:
        """Parse the version string into a tuple of integers for comparison."""
        try:
            return tuple(int(x) for x in self.version.split("."))
        except (ValueError, TypeError):
            return (0, 0, 0)


class ModuleRegistry:
    """Central registry for managing enterprise modules.

    Provides the authoritative source of truth for all module metadata,
    dependency graphs, and lifecycle states. Supports topological sorting
    for safe activation ordering and cycle detection.

    Example usage::

        registry = ModuleRegistry()
        registry.register(ModuleMeta(module_id="logger", version="1.0.0"))
        registry.register(ModuleMeta(
            module_id="auth",
            version="1.0.0",
            dependencies=frozenset({"logger"})
        ))
        registry.enable("logger")
        registry.enable("auth")
        order = registry.resolve_activation_order()
        # order -> [ModuleMeta(logger), ModuleMeta(auth)]
    """

    def __init__(self) -> None:
        """Initialize an empty module registry."""
        self._modules: Dict[str, ModuleMeta] = {}
        self._reverse_deps: Dict[str, Set[str]] = defaultdict(set)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, module: ModuleMeta) -> None:
        """Register a module in the registry.

        Args:
            module: The module metadata to register.

        Raises:
            ValueError: If a module with the same ID already exists.

        Example::

            registry.register(ModuleMeta(module_id="core", version="1.0.0"))
        """
        if module.module_id in self._modules:
            raise ValueError(
                f"Module '{module.module_id}' is already registered. "
                f"Use update() to modify an existing module."
            )
        self._modules[module.module_id] = module
        self._rebuild_reverse_deps()

    def update(self, module: ModuleMeta) -> None:
        """Update an existing module's metadata, replacing it entirely.

        Args:
            module: The new metadata for the module.

        Raises:
            KeyError: If the module is not registered.
        """
        if module.module_id not in self._modules:
            raise KeyError(f"Module '{module.module_id}' not registered. Use register() first.")
        self._modules[module.module_id] = module
        self._rebuild_reverse_deps()

    def unregister(self, module_id: str) -> ModuleMeta:
        """Remove a module from the registry.

        Args:
            module_id: The module to remove.

        Returns:
            The removed ModuleMeta.

        Raises:
            KeyError: If the module is not registered.
            ValueError: If other modules depend on this module.
        """
        if module_id not in self._modules:
            raise KeyError(f"Module '{module_id}' not registered.")
        dependents = self.dependents_of(module_id)
        if dependents:
            raise ValueError(
                f"Cannot unregister '{module_id}': still depended on by {dependents}"
            )
        removed = self._modules.pop(module_id)
        self._rebuild_reverse_deps()
        return removed

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, module_id: str) -> Optional[ModuleMeta]:
        """Retrieve a module by ID, or None if not found.

        Args:
            module_id: The module identifier.

        Returns:
            ModuleMeta if registered, else None.
        """
        return self._modules.get(module_id)

    def list_all(self) -> List[ModuleMeta]:
        """Return all registered modules as a list."""
        return list(self._modules.values())

    def filter_by_state(self, state: ModuleState) -> List[ModuleMeta]:
        """Return modules matching a given lifecycle state.

        Args:
            state: The state to filter by.

        Returns:
            List of modules in that state.
        """
        return [m for m in self._modules.values() if m.state == state]

    @property
    def module_count(self) -> int:
        """Return the number of registered modules."""
        return len(self._modules)

    # ------------------------------------------------------------------
    # Dependency queries
    # ------------------------------------------------------------------

    def dependencies_of(self, module_id: str) -> FrozenSet[str]:
        """Return the set of modules that *module_id* directly depends on.

        Args:
            module_id: The module to query.

        Returns:
            Frozen set of dependency module IDs.

        Raises:
            KeyError: If *module_id* is not registered.
        """
        self._require_registered(module_id)
        return self._modules[module_id].dependencies

    def dependents_of(self, module_id: str) -> FrozenSet[str]:
        """Return the set of modules that directly depend on *module_id*.

        Args:
            module_id: The module to query.

        Returns:
            Frozen set of dependent module IDs.
        """
        self._require_registered(module_id)
        return frozenset(self._reverse_deps.get(module_id, set()))

    def all_dependencies(self, module_id: str) -> FrozenSet[str]:
        """Return the transitive closure of all dependencies of *module_id*.

        Walks the entire dependency graph (breadth-first) to collect every
        module that *module_id* depends on, directly or indirectly.

        Args:
            module_id: The module to compute the closure for.

        Returns:
            Frozen set of all transitive dependency IDs.
        """
        self._require_registered(module_id)
        visited: Set[str] = set()
        queue: deque[str] = deque([module_id])
        while queue:
            current = queue.popleft()
            for dep in self._modules[current].dependencies:
                if dep not in visited:
                    visited.add(dep)
                    if dep in self._modules:
                        queue.append(dep)
        return frozenset(visited)

    # ------------------------------------------------------------------
    # Topological sort / resolution
    # ------------------------------------------------------------------

    def resolve_activation_order(self, module_ids: Optional[Iterable[str]] = None) -> List[ModuleMeta]:
        """Return modules in topological order (dependencies before dependents).

        Uses Kahn's algorithm for topological sorting. If *module_ids* is provided,
        only those modules (and their transitive dependencies) are included.

        Args:
            module_ids: Optional subset of modules to resolve. If None, resolves
                every registered module.

        Returns:
            List of ModuleMeta in dependency-first order.

        Raises:
            ValueError: If a circular dependency is detected.

        Example::

            # Resolve order for just two modules and their deps
            order = registry.resolve_activation_order(["auth", "db"])
        """
        # Determine the working set of modules
        if module_ids is not None:
            id_set = set(module_ids)
            # Expand with transitive dependencies
            expanded: Set[str] = set()
            for mid in id_set:
                expanded.add(mid)
                expanded.update(self.all_dependencies(mid))
            working_ids: Set[str] = {mid for mid in expanded if mid in self._modules}
        else:
            working_ids = set(self._modules.keys())

        # Build in-degree map and adjacency list for the subgraph
        in_degree: Dict[str, int] = {mid: 0 for mid in working_ids}
        adjacency: Dict[str, Set[str]] = {mid: set() for mid in working_ids}

        for mid in working_ids:
            for dep in self._modules[mid].dependencies:
                if dep in working_ids:
                    adjacency[dep].add(mid)
                    in_degree[mid] += 1

        # Kahn's algorithm
        queue: deque[str] = deque(mid for mid, deg in in_degree.items() if deg == 0)
        result: List[ModuleMeta] = []

        while queue:
            current = queue.popleft()
            result.append(self._modules[current])
            for neighbor in adjacency[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(working_ids):
            remaining = working_ids - {m.module_id for m in result}
            raise ValueError(
                f"Circular dependency detected involving modules: {remaining}"
            )

        return result

    def resolve_load_order(self) -> List[ModuleMeta]:
        """Alias for resolve_activation_order(). Included for semantic clarity."""
        return self.resolve_activation_order()

    # ------------------------------------------------------------------
    # Lifecycle management
    # ------------------------------------------------------------------

    def enable(self, module_id: str) -> None:
        """Enable a module, making it eligible for activation.

        Verifies that all dependencies are themselves enabled (or active) before
        allowing the state transition.

        Args:
            module_id: The module to enable.

        Raises:
            KeyError: If the module is not registered.
            ValueError: If a dependency is not yet enabled.
        """
        self._require_registered(module_id)
        module = self._modules[module_id]
        if module.state in (ModuleState.ENABLED, ModuleState.ACTIVE):
            return  # Already enabled

        # Check dependencies are enabled
        for dep_id in module.dependencies:
            dep = self._modules.get(dep_id)
            if dep is None or dep.state not in (ModuleState.ENABLED, ModuleState.ACTIVE):
                raise ValueError(
                    f"Cannot enable '{module_id}': dependency '{dep_id}' is not enabled "
                    f"(current state: {dep.state if dep else 'not registered'})"
                )

        module.state = ModuleState.ENABLED
        self._modules[module_id] = module

    def disable(self, module_id: str) -> None:
        """Disable a module, preventing its activation.

        Also prevents disabling if any enabled/active modules depend on it.

        Args:
            module_id: The module to disable.

        Raises:
            KeyError: If the module is not registered.
            ValueError: If an enabled/active module depends on this module.
        """
        self._require_registered(module_id)
        if self._modules[module_id].state == ModuleState.DISABLED:
            return

        # Check that no enabled dependents exist
        for dep_id in self.dependents_of(module_id):
            dep = self._modules.get(dep_id)
            if dep and dep.state in (ModuleState.ENABLED, ModuleState.ACTIVE):
                raise ValueError(
                    f"Cannot disable '{module_id}': '{dep_id}' depends on it and is "
                    f"{dep.state.value}"
                )

        self._modules[module_id].state = ModuleState.DISABLED

    def activate(self, module_id: str) -> None:
        """Mark a module as active (post-initialisation).

        The module must be in the ENABLED state. Dependencies must already be
        satisfied (they were checked at enable time).

        Args:
            module_id: The module to activate.

        Raises:
            KeyError: If the module is not registered.
            ValueError: If the module is not enabled or activation conditions are not met.
        """
        self._require_registered(module_id)
        module = self._modules[module_id]

        if module.state == ModuleState.ACTIVE:
            return
        if module.state != ModuleState.ENABLED:
            raise ValueError(
                f"Cannot activate '{module_id}': current state is {module.state.value}, "
                f"expected ENABLED"
            )

        # Evaluate activation condition
        if not self._evaluate_activation_condition(module):
            raise ValueError(
                f"Cannot activate '{module_id}': activation condition "
                f"'{module.activation_condition.value}' not satisfied"
            )

        module.state = ModuleState.ACTIVE
        self._modules[module_id] = module

    def deactivate(self, module_id: str) -> None:
        """Move a module from ACTIVE back to ENABLED.

        Prevents deactivation if active modules depend on this one.

        Args:
            module_id: The module to deactivate.

        Raises:
            KeyError: If the module is not registered.
            ValueError: If the module is not active or active modules depend on it.
        """
        self._require_registered(module_id)
        if self._modules[module_id].state != ModuleState.ACTIVE:
            raise ValueError(
                f"Cannot deactivate '{module_id}': current state is "
                f"{self._modules[module_id].state.value}, expected ACTIVE"
            )

        # Check no active dependents
        for dep_id in self.dependents_of(module_id):
            dep = self._modules.get(dep_id)
            if dep and dep.state == ModuleState.ACTIVE:
                raise ValueError(
                    f"Cannot deactivate '{module_id}': '{dep_id}' is ACTIVE and depends on it"
                )

        self._modules[module_id].state = ModuleState.ENABLED

    def set_error(self, module_id: str, error_info: Optional[str] = None) -> None:
        """Mark a module as being in an error state.

        Args:
            module_id: The module to mark.
            error_info: Optional error description stored in metadata.
        """
        self._require_registered(module_id)
        self._modules[module_id].state = ModuleState.ERROR
        if error_info:
            self._modules[module_id].metadata["error"] = error_info

    # ------------------------------------------------------------------
    # Cycle detection
    # ------------------------------------------------------------------

    def has_cycles(self) -> bool:
        """Check whether the full dependency graph contains any cycles.

        Returns:
            True if at least one cycle exists, False otherwise.
        """
        try:
            self.resolve_activation_order()
            return False
        except ValueError:
            return True

    def find_cycle(self) -> Optional[List[str]]:
        """Return one cycle path if a circular dependency exists, or None.

        Uses depth-first search with three-colour marking (white/gray/black).

        Returns:
            A list of module IDs forming a cycle, or None if the graph is acyclic.
        """
        WHITE, GRAY, BLACK = 0, 1, 2
        colour: Dict[str, int] = {mid: WHITE for mid in self._modules}
        parent: Dict[str, Optional[str]] = {mid: None for mid in self._modules}

        def dfs(node: str) -> Optional[List[str]]:
            colour[node] = GRAY
            for dep in self._modules[node].dependencies:
                if dep not in colour:  # Skip unresolvable deps
                    continue
                if colour[dep] == GRAY:
                    # Found a back-edge; reconstruct the cycle
                    cycle: List[str] = [dep, node]
                    cur = node
                    while parent.get(cur) is not None and parent[cur] != dep:
                        cur = parent[cur]  # type: ignore[assignment]
                        cycle.append(cur)  # type: ignore[arg-type]
                    cycle.append(dep)
                    cycle.reverse()
                    return cycle
                if colour[dep] == WHITE:
                    parent[dep] = node
                    result = dfs(dep)
                    if result is not None:
                        return result
            colour[node] = BLACK
            return None

        for mid in self._modules:
            if colour[mid] == WHITE:
                cycle = dfs(mid)
                if cycle is not None:
                    return cycle
        return None

    # ------------------------------------------------------------------
    # Version management
    # ------------------------------------------------------------------

    def get_version(self, module_id: str) -> str:
        """Return the version string of a registered module.

        Args:
            module_id: The module to query.

        Returns:
            The version string (e.g. '1.2.3').

        Raises:
            KeyError: If the module is not registered.
        """
        self._require_registered(module_id)
        return self._modules[module_id].version

    def check_version_satisfies(self, module_id: str, required: str) -> bool:
        """Check whether a module's version satisfies a minimum requirement.

        Performs simple tuple-based comparison after parsing both versions.

        Args:
            module_id: The module to check.
            required: Minimum required version string (e.g. '1.0.0').

        Returns:
            True if the module version >= required version.
        """
        self._require_registered(module_id)
        actual = self._modules[module_id].version_tuple
        try:
            req_tuple = tuple(int(x) for x in required.split("."))
        except (ValueError, TypeError):
            return False
        # Pad shorter tuple with zeros
        max_len = max(len(actual), len(req_tuple))
        actual_padded = actual + (0,) * (max_len - len(actual))
        req_padded = req_tuple + (0,) * (max_len - len(req_tuple))
        return actual_padded >= req_padded

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_registered(self, module_id: str) -> None:
        """Raise KeyError if *module_id* is not in the registry."""
        if module_id not in self._modules:
            raise KeyError(f"Module '{module_id}' is not registered")

    def _rebuild_reverse_deps(self) -> None:
        """Rebuild the reverse-dependency index from scratch."""
        self._reverse_deps = defaultdict(set)
        for mid, module in self._modules.items():
            for dep in module.dependencies:
                if dep in self._modules:
                    self._reverse_deps[dep].add(mid)

    def _evaluate_activation_condition(self, module: ModuleMeta) -> bool:
        """Evaluate whether a module's activation condition is satisfied.

        Args:
            module: The module whose condition to evaluate.

        Returns:
            True if the module is ready to activate.
        """
        condition = module.activation_condition
        if condition == ActivationCondition.ALWAYS:
            return True
        elif condition == ActivationCondition.NEVER:
            return False
        elif condition == ActivationCondition.DEPENDENCIES_READY:
            return all(
                self._modules.get(d) is not None and self._modules[d].state == ModuleState.ACTIVE
                for d in module.dependencies
            )
        elif condition == ActivationCondition.CONDITIONAL:
            if module.activation_callable is not None:
                try:
                    return module.activation_callable()
                except Exception:
                    return False
            return False
        elif condition == ActivationCondition.ON_DEMAND:
            # ON_DEMAND requires an explicit activate() call, which we are already in
            return True
        return False