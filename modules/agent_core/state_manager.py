"""
StateManager — Distributed State Management with CRDT
=======================================================

Part of the Claude Code Core enterprise module. Provides distributed
state management using Conflict-free Replicated Data Types (CRDTs),
state versioning, merge strategies, and distributed locking.

Classes:
  StateVersion — semantic versioning for state snapshots
  MergeStrategy — strategies for resolving merge conflicts
  CRDTStore — Conflict-free Replicated Data Type store
  DistributedLock — distributed mutex for state operations
  StateManager — orchestrates state operations
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("enterprise.agent.state_manager")

try:
    from enterprise.platform_kernel import HealthStatus
except ImportError:
    from platform_kernel import HealthStatus


# =============================================================================
# Enums
# =============================================================================


class MergeStrategy(Enum):
    """Strategies for resolving merge conflicts between state versions."""
    LAST_WRITE_WINS = "last_write_wins"      # Timestamp-based resolution
    CRDT_MERGE = "crdt_merge"                 # CRDT-based automatic merge
    THREE_WAY = "three_way"                   # Three-way merge with base
    CUSTOM = "custom"                         # User-provided merge function
    REJECT = "reject"                         # Reject conflicting writes


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class StateVersion:
    """Semantic version for state snapshots.

    Attributes:
        major: Major version (breaking changes).
        minor: Minor version (backward-compatible additions).
        patch: Patch version (backward-compatible fixes).
        timestamp: When this version was created.
        parent_hash: Hash of the parent version.
        node_id: Node that created this version.
    """
    major: int = 1
    minor: int = 0
    patch: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    parent_hash: Optional[str] = None
    node_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __str__(self) -> str:
        return f"v{self.major}.{self.minor}.{self.patch}"

    def __lt__(self, other: StateVersion) -> bool:
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, StateVersion):
            return NotImplemented
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)

    def bump_major(self) -> StateVersion:
        return StateVersion(major=self.major + 1, minor=0, patch=0,
                            parent_hash=self.content_hash, node_id=self.node_id)

    def bump_minor(self) -> StateVersion:
        return StateVersion(major=self.major, minor=self.minor + 1, patch=0,
                            parent_hash=self.content_hash, node_id=self.node_id)

    def bump_patch(self) -> StateVersion:
        return StateVersion(major=self.major, minor=self.minor, patch=self.patch + 1,
                            parent_hash=self.content_hash, node_id=self.node_id)

    @property
    def content_hash(self) -> str:
        raw = f"{self.major}.{self.minor}.{self.patch}:{self.node_id}:{self.timestamp.isoformat()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class StateEntry:
    """A single key-value entry in the state store.

    Attributes:
        key: Unique key.
        value: The stored value.
        version: Current version.
        created_at: When this entry was created.
        updated_at: When this entry was last updated.
        metadata: Arbitrary metadata.
    """
    key: str
    value: Any
    version: StateVersion = field(default_factory=StateVersion)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# CRDTStore
# =============================================================================


class CRDTStore:
    """Conflict-free Replicated Data Type store.

    Implements several CRDT types for automatic conflict resolution:
      - G-Counter (grow-only counter)
      - PN-Counter (positive/negative counter)
      - LWW-Register (last-write-wins register)
      - OR-Set (observed-remove set)

    All operations are automatically mergeable without conflicts.
    """

    def __init__(self) -> None:
        # G-Counters: node_id -> count
        self._g_counters: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        # PN-Counters: node_id -> (positive, negative)
        self._pn_counters: Dict[str, Dict[str, Tuple[int, int]]] = defaultdict(
            lambda: defaultdict(lambda: (0, 0))
        )
        # Registers: key -> (value, timestamp)
        self._registers: Dict[str, Tuple[Any, float]] = {}
        # OR-Sets: key -> (add_set, remove_set)
        self._sets: Dict[str, Tuple[Set[Any], Set[Any]]] = defaultdict(
            lambda: (set(), set())
        )

    # ── G-Counter ──────────────────────────────────────────────────────

    def g_counter_increment(self, counter_id: str, node_id: str, amount: int = 1) -> int:
        """Increment a grow-only counter.

        Returns the new total across all nodes.
        """
        self._g_counters[counter_id][node_id] += amount
        return self.g_counter_value(counter_id)

    def g_counter_value(self, counter_id: str) -> int:
        """Get the total value of a G-Counter."""
        return sum(self._g_counters[counter_id].values())

    # ── PN-Counter ─────────────────────────────────────────────────────

    def pn_counter_increment(self, counter_id: str, node_id: str, amount: int = 1) -> int:
        """Increment a PN-Counter (positive direction)."""
        p, n = self._pn_counters[counter_id][node_id]
        self._pn_counters[counter_id][node_id] = (p + amount, n)
        return self.pn_counter_value(counter_id)

    def pn_counter_decrement(self, counter_id: str, node_id: str, amount: int = 1) -> int:
        """Decrement a PN-Counter (negative direction)."""
        p, n = self._pn_counters[counter_id][node_id]
        self._pn_counters[counter_id][node_id] = (p, n + amount)
        return self.pn_counter_value(counter_id)

    def pn_counter_value(self, counter_id: str) -> int:
        """Get the net value of a PN-Counter."""
        total = 0
        for p, n in self._pn_counters[counter_id].values():
            total += p - n
        return total

    # ── LWW-Register ───────────────────────────────────────────────────

    def register_set(self, key: str, value: Any) -> None:
        """Set a register value with last-write-wins semantics."""
        import time
        self._registers[key] = (value, time.time())

    def register_get(self, key: str) -> Optional[Any]:
        """Get a register value."""
        entry = self._registers.get(key)
        return entry[0] if entry else None

    def register_delete(self, key: str) -> bool:
        """Delete a register entry."""
        if key in self._registers:
            del self._registers[key]
            return True
        return False

    # ── OR-Set ─────────────────────────────────────────────────────────

    def set_add(self, set_id: str, element: Any) -> None:
        """Add an element to an observed-remove set."""
        add_set, remove_set = self._sets[set_id]
        add_set.add(element)

    def set_remove(self, set_id: str, element: Any) -> None:
        """Remove an element from an observed-remove set."""
        add_set, remove_set = self._sets[set_id]
        remove_set.add(element)

    def set_contains(self, set_id: str, element: Any) -> bool:
        """Check if an element is in the set."""
        add_set, remove_set = self._sets[set_id]
        return element in add_set and element not in remove_set

    def set_members(self, set_id: str) -> Set[Any]:
        """Get all members of a set."""
        add_set, remove_set = self._sets[set_id]
        return add_set - remove_set

    # ── Merge ──────────────────────────────────────────────────────────

    def merge(self, other: CRDTStore) -> None:
        """Merge another CRDTStore into this one (commutative, associative)."""
        # Merge G-Counters
        for cid, nodes in other._g_counters.items():
            for nid, val in nodes.items():
                self._g_counters[cid][nid] = max(self._g_counters[cid][nid], val)

        # Merge PN-Counters
        for cid, nodes in other._pn_counters.items():
            for nid, (p, n) in nodes.items():
                cp, cn = self._pn_counters[cid][nid]
                self._pn_counters[cid][nid] = (max(cp, p), max(cn, n))

        # Merge Registers (LWW)
        for key, (val, ts) in other._registers.items():
            if key not in self._registers or ts > self._registers[key][1]:
                self._registers[key] = (val, ts)

        # Merge Sets
        for sid, (add_set, remove_set) in other._sets.items():
            s_add, s_remove = self._sets[sid]
            s_add.update(add_set)
            s_remove.update(remove_set)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the CRDT store to a dictionary."""
        return {
            "g_counters": {k: dict(v) for k, v in self._g_counters.items()},
            "pn_counters": {
                k: {n: list(pn) for n, pn in v.items()}
                for k, v in self._pn_counters.items()
            },
            "registers": dict(self._registers),
            "sets": {
                k: (list(add_set), list(remove_set))
                for k, (add_set, remove_set) in self._sets.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CRDTStore:
        """Deserialize a CRDT store from a dictionary."""
        store = cls()
        for cid, nodes in data.get("g_counters", {}).items():
            for nid, val in nodes.items():
                store._g_counters[cid][nid] = val
        for cid, nodes in data.get("pn_counters", {}).items():
            for nid, (p, n) in nodes.items():
                store._pn_counters[cid][nid] = (p, n)
        for key, (val, ts) in data.get("registers", {}).items():
            store._registers[key] = (val, ts)
        for sid, (add_list, rem_list) in data.get("sets", {}).items():
            store._sets[sid] = (set(add_list), set(rem_list))
        return store

    def clear(self) -> None:
        """Clear all data from the store."""
        self._g_counters.clear()
        self._pn_counters.clear()
        self._registers.clear()
        self._sets.clear()


# =============================================================================
# DistributedLock
# =============================================================================


class DistributedLock:
    """Distributed mutex for coordinating state operations.

    In a real system this would use Redis/etcd. Here we use an
    in-process asyncio.Lock with a TTL for simulation.

    Usage::

        lock = DistributedLock("my_resource")
        async with lock.acquire(timeout=5.0):
            # Critical section
            ...
    """

    def __init__(self, resource_id: str, ttl_seconds: float = 30.0) -> None:
        self.resource_id = resource_id
        self.ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()
        self._owner: Optional[str] = None
        self._acquired_at: Optional[float] = None

    async def acquire(self, timeout: float = 10.0) -> bool:
        """Acquire the lock.

        Args:
            timeout: Maximum seconds to wait.

        Returns:
            True if the lock was acquired.
        """
        try:
            acquired = await asyncio.wait_for(self._lock.acquire(), timeout=timeout)
            if acquired:
                import time
                self._owner = str(uuid.uuid4())
                self._acquired_at = time.time()
            return acquired
        except asyncio.TimeoutError:
            return False

    def release(self) -> None:
        """Release the lock."""
        try:
            self._lock.release()
        except RuntimeError:
            pass  # Already released
        self._owner = None
        self._acquired_at = None

    async def __aenter__(self) -> DistributedLock:
        await self.acquire()
        return self

    async def __aexit__(self, *args: Any) -> None:
        self.release()

    @property
    def is_locked(self) -> bool:
        return self._lock.locked()


# =============================================================================
# StateManager
# =============================================================================


class StateManager:
    """Orchestrates distributed state operations.

    Provides a unified interface for state management:
      - Key-value state storage with versioning
      - CRDT-based counters, registers, and sets
      - Distributed locking for critical sections
      - Snapshot/restore for persistence and migration
      - Merge strategies for conflict resolution

    Usage::

        sm = StateManager()
        await sm.initialize()
        sm.set("key", "value")
        sm.g_counter_inc("visits")
        snapshot = sm.snapshot()
        await sm.shutdown()
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._config = config or {}
        self._entries: Dict[str, StateEntry] = {}
        self._crdt = CRDTStore()
        self._locks: Dict[str, DistributedLock] = {}
        self._merge_strategy: MergeStrategy = MergeStrategy(
            self._config.get("merge_strategy", "last_write_wins")
        )
        self._node_id: str = str(uuid.uuid4())
        self._status = HealthStatus.UNKNOWN

    async def initialize(self) -> None:
        self._status = HealthStatus.HEALTHY
        logger.info("StateManager initialized (node_id=%s)", self._node_id)

    async def health_check(self) -> bool:
        return self._status == HealthStatus.HEALTHY

    async def shutdown(self) -> None:
        self._entries.clear()
        self._crdt.clear()
        self._locks.clear()
        self._status = HealthStatus.UNKNOWN
        logger.info("StateManager shut down")

    # ── Key-Value State ────────────────────────────────────────────────

    def set(self, key: str, value: Any, metadata: Optional[Dict[str, Any]] = None) -> StateEntry:
        """Set a key-value entry.

        Creates a new entry or updates an existing one. Version is
        automatically bumped.

        Args:
            key: Unique key.
            value: Value to store.
            metadata: Optional metadata.

        Returns:
            The created or updated StateEntry.
        """
        import time
        now = datetime.now(timezone.utc)
        if key in self._entries:
            entry = self._entries[key]
            entry.value = value
            entry.version = entry.version.bump_patch()
            entry.updated_at = now
            entry.metadata.update(metadata or {})
        else:
            entry = StateEntry(
                key=key,
                value=value,
                version=StateVersion(node_id=self._node_id),
                created_at=now,
                updated_at=now,
                metadata=metadata or {},
            )
            self._entries[key] = entry
        return entry

    def get(self, key: str) -> Optional[Any]:
        """Get a value by key.

        Returns:
            The stored value, or None if not found.
        """
        entry = self._entries.get(key)
        return entry.value if entry else None

    def get_entry(self, key: str) -> Optional[StateEntry]:
        """Get the full StateEntry for a key."""
        return self._entries.get(key)

    def delete(self, key: str) -> bool:
        """Delete a key-value entry.

        Returns:
            True if the entry was found and deleted.
        """
        if key in self._entries:
            del self._entries[key]
            return True
        return False

    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        return key in self._entries

    def list_keys(self, prefix: str = "") -> List[str]:
        """List all keys, optionally filtered by prefix."""
        if prefix:
            return [k for k in self._entries if k.startswith(prefix)]
        return list(self._entries.keys())

    # ── CRDT Operations ────────────────────────────────────────────────

    def g_counter_inc(self, counter_id: str, amount: int = 1) -> int:
        """Increment a grow-only counter."""
        return self._crdt.g_counter_increment(counter_id, self._node_id, amount)

    def g_counter_get(self, counter_id: str) -> int:
        """Get a G-Counter value."""
        return self._crdt.g_counter_value(counter_id)

    def pn_counter_inc(self, counter_id: str, amount: int = 1) -> int:
        """Increment a PN-Counter."""
        return self._crdt.pn_counter_increment(counter_id, self._node_id, amount)

    def pn_counter_dec(self, counter_id: str, amount: int = 1) -> int:
        """Decrement a PN-Counter."""
        return self._crdt.pn_counter_decrement(counter_id, self._node_id, amount)

    def pn_counter_get(self, counter_id: str) -> int:
        """Get a PN-Counter value."""
        return self._crdt.pn_counter_value(counter_id)

    def register_set(self, key: str, value: Any) -> None:
        """Set a CRDT register value."""
        self._crdt.register_set(key, value)

    def register_get(self, key: str) -> Optional[Any]:
        """Get a CRDT register value."""
        return self._crdt.register_get(key)

    def set_add(self, set_id: str, element: Any) -> None:
        """Add to a CRDT set."""
        self._crdt.set_add(set_id, element)

    def set_remove(self, set_id: str, element: Any) -> None:
        """Remove from a CRDT set."""
        self._crdt.set_remove(set_id, element)

    def set_members(self, set_id: str) -> Set[Any]:
        """Get CRDT set members."""
        return self._crdt.set_members(set_id)

    # ── Distributed Locking ────────────────────────────────────────────

    def get_lock(self, resource_id: str, ttl_seconds: float = 30.0) -> DistributedLock:
        """Get or create a distributed lock for a resource.

        Args:
            resource_id: Resource identifier.
            ttl_seconds: Lock time-to-live.

        Returns:
            A DistributedLock instance.
        """
        if resource_id not in self._locks:
            self._locks[resource_id] = DistributedLock(resource_id, ttl_seconds)
        return self._locks[resource_id]

    async def with_lock(self, resource_id: str, ttl: float = 30.0):
        """Async context manager for distributed locking.

        Usage::

            async with sm.with_lock("my_resource"):
                sm.set("shared_key", new_value)
        """
        lock = self.get_lock(resource_id, ttl)
        return lock

    # ── Snapshot / Restore ─────────────────────────────────────────────

    def snapshot(self) -> Dict[str, Any]:
        """Create a snapshot of all state.

        Returns:
            A serializable dictionary representation.
        """
        entries = {}
        for key, entry in self._entries.items():
            entries[key] = {
                "value": entry.value,
                "version": str(entry.version),
                "version_major": entry.version.major,
                "version_minor": entry.version.minor,
                "version_patch": entry.version.patch,
                "created_at": entry.created_at.isoformat(),
                "updated_at": entry.updated_at.isoformat(),
                "metadata": entry.metadata,
            }
        return {
            "node_id": self._node_id,
            "entries": entries,
            "crdt": self._crdt.to_dict(),
            "snapshot_at": datetime.now(timezone.utc).isoformat(),
        }

    def restore(self, snapshot: Dict[str, Any]) -> int:
        """Restore state from a snapshot.

        Args:
            snapshot: A dictionary from snapshot().

        Returns:
            Number of entries restored.
        """
        count = 0
        for key, data in snapshot.get("entries", {}).items():
            entry = StateEntry(
                key=key,
                value=data.get("value"),
                version=StateVersion(
                    major=data.get("version_major", 1),
                    minor=data.get("version_minor", 0),
                    patch=data.get("version_patch", 0),
                    node_id=self._node_id,
                ),
                metadata=data.get("metadata", {}),
            )
            self._entries[key] = entry
            count += 1

        crdt_data = snapshot.get("crdt", {})
        remote_crdt = CRDTStore.from_dict(crdt_data)
        self._crdt.merge(remote_crdt)

        logger.info("Restored %d entries from snapshot", count)
        return count

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def merge_strategy(self) -> MergeStrategy:
        return self._merge_strategy

    @merge_strategy.setter
    def merge_strategy(self, value: MergeStrategy) -> None:
        self._merge_strategy = value

    @property
    def status(self) -> HealthStatus:
        return self._status

    @property
    def crdt(self) -> CRDTStore:
        return self._crdt