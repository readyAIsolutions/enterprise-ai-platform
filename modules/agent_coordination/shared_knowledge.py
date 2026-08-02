"""
ENI Enterprise Shared Knowledge Base — Thread-safe, versioned knowledge store
with conflict detection, snapshot/restore, and role-based access control.

Coordinates shared understanding across all agents in the ENI OS.
"""

import json
import time
import uuid
import hashlib
import logging
import threading
from typing import Dict, Any, List, Optional, Callable, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger("enterprise.shared_knowledge")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class KnowledgeDomain(Enum):
    """All recognized knowledge domains in the ENI OS."""
    PROJECT_REQUIREMENTS = "project_requirements"
    ARCHITECTURE = "architecture"
    APIS = "apis"
    DATABASE_SCHEMA = "database_schema"
    UI_COMPONENTS = "ui_components"
    DESIGN_SYSTEM = "design_system"
    SECURITY_POLICIES = "security_policies"
    CODING_STANDARDS = "coding_standards"
    DOCUMENTATION = "documentation"
    BUSINESS_GOALS = "business_goals"
    PREVIOUS_DECISIONS = "previous_decisions"
    SECURITY = "security"
    DATA = "data"
    BUSINESS = "business"
    TECHNICAL = "technical"
    PROCESS = "process"
    COMPLIANCE = "compliance"
    GENERAL = "general"

    @classmethod
    def from_string(cls, value: str) -> "KnowledgeDomain":
        """Case-insensitive lookup."""
        for member in cls:
            if member.value == value.lower():
                return member
        raise ValueError(f"Unknown knowledge domain: {value}")


class AccessLevel(Enum):
    """Access control levels for knowledge domains."""
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    NONE = "none"


class AgentRole(Enum):
    """Agent roles for role-based access control."""
    EXECUTIVE = "executive"
    ARCHITECT = "architect"
    BACKEND = "backend"
    FRONTEND = "frontend"
    SECURITY = "security"
    AI_ENGINEER = "ai_engineer"
    DATA_ENGINEER = "data_engineer"
    QA = "qa"
    DEVOPS = "devops"
    COMPLIANCE = "compliance"
    DOCS = "docs"
    PRODUCT_MANAGER = "product_manager"

    def can_read(self, domain: KnowledgeDomain) -> bool:
        return True  # All agents can read all domains by default

    def can_write(self, domain: KnowledgeDomain) -> bool:
        allowed = _WRITE_PERMISSIONS.get(self, set())
        return domain in allowed or self == AgentRole.EXECUTIVE


# Role-based write permissions
_WRITE_PERMISSIONS: Dict[AgentRole, Set[KnowledgeDomain]] = {
    AgentRole.EXECUTIVE: set(KnowledgeDomain),
    AgentRole.ARCHITECT: {
        KnowledgeDomain.ARCHITECTURE,
        KnowledgeDomain.APIS,
        KnowledgeDomain.DATABASE_SCHEMA,
        KnowledgeDomain.CODING_STANDARDS,
        KnowledgeDomain.TECHNICAL,
    },
    AgentRole.BACKEND: {
        KnowledgeDomain.APIS,
        KnowledgeDomain.DATABASE_SCHEMA,
        KnowledgeDomain.CODING_STANDARDS,
        KnowledgeDomain.TECHNICAL,
    },
    AgentRole.FRONTEND: {
        KnowledgeDomain.UI_COMPONENTS,
        KnowledgeDomain.DESIGN_SYSTEM,
    },
    AgentRole.SECURITY: {
        KnowledgeDomain.SECURITY_POLICIES,
        KnowledgeDomain.SECURITY,
        KnowledgeDomain.COMPLIANCE,
    },
    AgentRole.AI_ENGINEER: {
        KnowledgeDomain.ARCHITECTURE,
        KnowledgeDomain.DOCUMENTATION,
        KnowledgeDomain.TECHNICAL,
    },
    AgentRole.DATA_ENGINEER: {
        KnowledgeDomain.DATABASE_SCHEMA,
        KnowledgeDomain.DATA,
        KnowledgeDomain.CODING_STANDARDS,
    },
    AgentRole.QA: {
        KnowledgeDomain.PROJECT_REQUIREMENTS,
    },
    AgentRole.DEVOPS: {
        KnowledgeDomain.ARCHITECTURE,
        KnowledgeDomain.APIS,
    },
    AgentRole.COMPLIANCE: {
        KnowledgeDomain.SECURITY_POLICIES,
        KnowledgeDomain.COMPLIANCE,
        KnowledgeDomain.CODING_STANDARDS,
    },
    AgentRole.DOCS: {
        KnowledgeDomain.DOCUMENTATION,
    },
    AgentRole.PRODUCT_MANAGER: {
        KnowledgeDomain.PROJECT_REQUIREMENTS,
        KnowledgeDomain.BUSINESS_GOALS,
        KnowledgeDomain.BUSINESS,
        KnowledgeDomain.PREVIOUS_DECISIONS,
    },
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeEntry:
    """A single versioned entry in the shared knowledge base.

    Each entry is identified uniquely by (domain, key).  The version field
    provides optimistic locking: concurrent writers must present the version
    they read — if it has changed underneath them the write is rejected.
    """

    entry_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    domain: str = ""
    key: str = ""
    value: Any = None  # Must be JSON-serializable
    version: int = 1
    created_by: str = ""
    created_at: str = field(
        default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    )
    updated_at: str = field(
        default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    )
    tags: List[str] = field(default_factory=list)
    confidence: float = 0.0  # 0.0 - 1.0

    # Backward-compat aliases
    @property
    def author_id(self) -> str:
        return self.created_by

    @author_id.setter
    def author_id(self, v: str) -> None:
        self.created_by = v

    @property
    def metadata(self) -> Dict[str, Any]:
        return {
            "confidence": self.confidence,
            "tags": self.tags,
        }

    @metadata.setter
    def metadata(self, d: Dict[str, Any]) -> None:
        self.confidence = d.get("confidence", self.confidence)
        self.tags = d.get("tags", self.tags)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for snapshot / JSON export."""
        return {
            "entry_id": self.entry_id,
            "domain": self.domain,
            "key": self.key,
            "value": self.value,
            "version": self.version,
            "created_by": self.created_by,
            "author_id": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tags": self.tags,
            "confidence": self.confidence,
            "metadata": {
                "confidence": self.confidence,
                "tags": self.tags,
            },
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeEntry":
        """Deserialize from dictionary."""
        return cls(
            entry_id=data.get("entry_id", str(uuid.uuid4())[:12]),
            domain=data.get("domain", ""),
            key=data.get("key", ""),
            value=data.get("value"),
            version=data.get("version", 1),
            created_by=data.get("created_by") or data.get("author_id", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            tags=data.get("tags", []),
            confidence=data.get("confidence", 0.0),
        )


# ---------------------------------------------------------------------------
# Readers-writer lock
# ---------------------------------------------------------------------------

class ReadWriteLock:
    """A simple readers-writer lock with writer priority.

    Multiple readers can hold the lock simultaneously, but writers get
    exclusive access.  Writers are given priority over new readers to
    prevent writer starvation.
    """

    def __init__(self) -> None:
        self._readers: int = 0
        self._writers_waiting: int = 0
        self._writing: bool = False
        self._cond = threading.Condition(threading.Lock())

    def acquire_read(self) -> None:
        with self._cond:
            while self._writing or self._writers_waiting > 0:
                self._cond.wait()
            self._readers += 1

    def release_read(self) -> None:
        with self._cond:
            self._readers -= 1
            if self._readers == 0:
                self._cond.notify_all()

    def acquire_write(self) -> None:
        with self._cond:
            self._writers_waiting += 1
            try:
                while self._readers > 0 or self._writing:
                    self._cond.wait()
                self._writing = True
            finally:
                self._writers_waiting -= 1

    def release_write(self) -> None:
        with self._cond:
            self._writing = False
            self._cond.notify_all()

    def read_lock(self):
        class _ReadCtx:
            def __init__(self, rwl: "ReadWriteLock") -> None:
                self._rwl = rwl

            def __enter__(self) -> None:
                self._rwl.acquire_read()

            def __exit__(self, *a: Any) -> None:
                self._rwl.release_read()

        return _ReadCtx(self)

    def write_lock(self):
        class _WriteCtx:
            def __init__(self, rwl: "ReadWriteLock") -> None:
                self._rwl = rwl

            def __enter__(self) -> None:
                self._rwl.acquire_write()

            def __exit__(self, *a: Any) -> None:
                self._rwl.release_write()

        return _WriteCtx(self)


# ---------------------------------------------------------------------------
# Shared Knowledge Base
# ---------------------------------------------------------------------------

class SharedKnowledgeBase:
    """Enterprise-grade shared knowledge store with thread-safe, versioned access.

    All agents in the ENI OS consult this base for shared facts, requirements,
    architectural decisions, and domain-specific knowledge.

    Features:
        - Thread-safe reads/writes with readers-writer lock
        - Optimistic concurrency control via version field
        - Full version history per entry
        - Domain-scoped queries with filtering
        - Change subscription notifications
        - Full snapshot export/import with checksums
        - Role-based access control per agent role
    """

    def __init__(self, snapshot_path: Optional[str] = None) -> None:
        # Primary store: domain -> key -> KnowledgeEntry
        self._store: Dict[str, Dict[str, KnowledgeEntry]] = defaultdict(dict)
        # Version history: (domain, key) -> list of past KnowledgeEntry states
        self._history: Dict[Tuple[str, str], List[KnowledgeEntry]] = defaultdict(list)
        # Subscribers: domain -> set of callback functions
        self._subscribers: Dict[str, Set[Callable[[str, KnowledgeEntry], None]]] = (
            defaultdict(set)
        )
        self._rwlock = ReadWriteLock()
        self._subscriber_lock = threading.Lock()
        self._snapshot_path = snapshot_path
        # Access control: agent_id -> {domain -> AccessLevel}
        self._access_control: Dict[str, Dict[str, AccessLevel]] = {}
        logger.info("SharedKnowledgeBase initialized")

    # ------------------------------------------------------------------
    # Core access methods
    # ------------------------------------------------------------------

    def get(self, domain_or_key: str, key: Optional[str] = None) -> Optional[KnowledgeEntry]:
        """Retrieve the current version of an entry.

        Supports both ``get(domain, key)`` and ``get(key)`` signatures for
        backward compatibility.

        Args:
            domain_or_key: Domain name or, in single-arg form, entry key.
            key: Entry key (when called in two-arg form).

        Returns:
            KnowledgeEntry if found, None otherwise.
        """
        if key is not None:
            domain = domain_or_key.lower()
            with self._rwlock.read_lock():
                return self._store.get(domain, {}).get(key)
        else:
            # Single-arg mode: search all domains by key
            with self._rwlock.read_lock():
                for dom_entries in self._store.values():
                    if domain_or_key in dom_entries:
                        return dom_entries[domain_or_key]
            return None

    def get_with_version(
        self, domain: str, key: str, version: int
    ) -> Optional[KnowledgeEntry]:
        """Retrieve a specific historical version of an entry."""
        domain = domain.lower()
        with self._rwlock.read_lock():
            history = self._history.get((domain, key), [])
            for entry in history:
                if entry.version == version:
                    return entry
            current = self._store.get(domain, {}).get(key)
            if current and current.version == version:
                return current
        return None

    def set(
        self,
        domain: str,
        key: str,
        value: Any,
        created_by: str = "",
        role: Optional[AgentRole] = None,
        tags: Optional[List[str]] = None,
        confidence: float = 0.0,
        expected_version: Optional[int] = None,
    ) -> Tuple[KnowledgeEntry, Optional[str]]:
        """Write (or update) a knowledge entry with optimistic locking.

        Returns (entry, conflict_message).  conflict_message is None on
        success, or a string describing the conflict when rejected.

        Raises PermissionError if the role lacks write access.
        """
        domain = domain.lower()

        # Access control
        if role is not None and not role.can_write(KnowledgeDomain.from_string(domain)):
            raise PermissionError(
                f"Agent role '{role.value}' lacks write access to domain '{domain}'"
            )

        # Validate JSON-serializable
        try:
            json.dumps(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Value must be JSON-serializable: {exc}")

        now = time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        with self._rwlock.write_lock():
            existing = self._store.get(domain, {}).get(key)

            # Conflict detection via optimistic locking
            if expected_version is not None and existing is not None:
                if existing.version != expected_version:
                    conflict_msg = (
                        f"Version conflict on '{domain}/{key}': "
                        f"expected v{expected_version}, current v{existing.version}. "
                        f"Last modified by '{existing.created_by}' at "
                        f"{existing.updated_at}."
                    )
                    logger.warning(f"CONFLICT: {conflict_msg}")
                    return existing, conflict_msg

            # Create or update
            if existing is not None:
                # Save current to history
                self._history[(domain, key)].append(
                    KnowledgeEntry(
                        entry_id=existing.entry_id,
                        domain=existing.domain,
                        key=existing.key,
                        value=existing.value,
                        version=existing.version,
                        created_by=existing.created_by,
                        created_at=existing.created_at,
                        updated_at=existing.updated_at,
                        tags=list(existing.tags),
                        confidence=existing.confidence,
                    )
                )
                new_version = existing.version + 1
                entry = KnowledgeEntry(
                    entry_id=existing.entry_id,
                    domain=domain,
                    key=key,
                    value=value,
                    version=new_version,
                    created_by=created_by or existing.created_by,
                    created_at=existing.created_at,
                    updated_at=now,
                    tags=tags or existing.tags,
                    confidence=confidence,
                )
            else:
                entry = KnowledgeEntry(
                    domain=domain,
                    key=key,
                    value=value,
                    version=1,
                    created_by=created_by,
                    created_at=now,
                    updated_at=now,
                    tags=tags or [],
                    confidence=confidence,
                )

            self._store[domain][key] = entry

        self._notify_subscribers(domain, entry)
        return entry, None

    # Backward-compat: put(entry)
    def put(self, entry: KnowledgeEntry) -> KnowledgeEntry:
        """Write or update using a KnowledgeEntry object (backward compat)."""
        result, _ = self.set(
            domain=getattr(entry.domain, "value", str(entry.domain)).lower()
            if isinstance(getattr(entry, "domain", ""), Enum)
            else str(entry.domain).lower(),
            key=entry.key,
            value=entry.value,
            created_by=entry.created_by,
            tags=entry.tags,
            confidence=entry.confidence,
        )
        return result

    def delete(self, domain: str, key: str = None, role: Optional[AgentRole] = None) -> bool:
        """Delete an entry. Supports both ``delete(domain, key)`` and
        ``delete(key)`` signatures."""
        if key is None:
            # Delete by key across all domains
            with self._rwlock.write_lock():
                for dom, dom_entries in list(self._store.items()):
                    if domain in dom_entries:
                        existing = dom_entries.pop(domain, None)
                        if existing:
                            self._history[(dom, domain)].append(existing)
                            return True
            return False

        domain = domain.lower()
        if role is not None and not role.can_write(KnowledgeDomain.from_string(domain)):
            raise PermissionError(
                f"Agent role '{role.value}' lacks write access to domain '{domain}'"
            )
        with self._rwlock.write_lock():
            existing = self._store.get(domain, {}).pop(key, None)
            if existing:
                self._history[(domain, key)].append(existing)
                return True
        return False

    # ------------------------------------------------------------------
    # Access control (backward compat)
    # ------------------------------------------------------------------

    def set_access(self, agent_id: str, domain: KnowledgeDomain, level: AccessLevel) -> None:
        with self._rwlock.write_lock():
            self._access_control.setdefault(agent_id, {})[domain.value] = level

    def get_access(self, agent_id: str, domain: KnowledgeDomain) -> AccessLevel:
        with self._rwlock.read_lock():
            return self._access_control.get(agent_id, {}).get(
                domain.value, AccessLevel.NONE
            )

    def check_access(
        self, agent_id: str, domain: KnowledgeDomain, required: AccessLevel
    ) -> bool:
        actual = self.get_access(agent_id, domain)
        if required == AccessLevel.READ:
            return actual in (AccessLevel.READ, AccessLevel.WRITE, AccessLevel.ADMIN)
        elif required == AccessLevel.WRITE:
            return actual in (AccessLevel.WRITE, AccessLevel.ADMIN)
        elif required == AccessLevel.ADMIN:
            return actual == AccessLevel.ADMIN
        return False

    # ------------------------------------------------------------------
    # Query / search
    # ------------------------------------------------------------------

    def query(
        self,
        domain: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[KnowledgeEntry]:
        """Search/filter entries across one or all domains.

        Supported filters: key, tags, created_by, confidence_min,
        confidence_max, version_min, value_contains, author_id.
        """
        filters = filters or {}
        results: List[KnowledgeEntry] = []

        domains_to_search: List[str]
        if domain is not None:
            domains_to_search = [domain.lower()]
        else:
            domains_to_search = list(self._store.keys())

        with self._rwlock.read_lock():
            for dom in domains_to_search:
                for entry in self._store.get(dom, {}).values():
                    if self._matches_filters(entry, filters):
                        results.append(entry)
        return results

    def _matches_filters(self, entry: KnowledgeEntry, filters: Dict[str, Any]) -> bool:
        for field, value in filters.items():
            if field == "key" and value not in entry.key:
                return False
            elif field == "tags":
                required = set(value)
                if not required.issubset(set(entry.tags)):
                    return False
            elif field in ("created_by", "author_id") and entry.created_by != value:
                return False
            elif field == "confidence_min" and entry.confidence < value:
                return False
            elif field == "confidence_max" and entry.confidence > value:
                return False
            elif field == "version_min" and entry.version < value:
                return False
            elif field == "value_contains":
                if isinstance(entry.value, (dict, list)):
                    if value not in json.dumps(entry.value, default=str):
                        return False
                elif value not in str(entry.value):
                    return False
        return True

    def list_domain(self, domain: str) -> List[KnowledgeEntry]:
        """Return all entries in a domain."""
        domain = domain.lower()
        with self._rwlock.read_lock():
            return list(self._store.get(domain, {}).values())

    def list_all_domains(self) -> List[str]:
        """Return names of all domains with entries."""
        with self._rwlock.read_lock():
            return sorted(self._store.keys())

    # Backward compat query methods
    def query_by_domain(self, domain: KnowledgeDomain) -> List[KnowledgeEntry]:
        return self.list_domain(domain.value)

    def query_by_tag(self, tag: str) -> List[KnowledgeEntry]:
        return self.query(filters={"tags": [tag]})

    def query_by_author(self, author_id: str) -> List[KnowledgeEntry]:
        return self.query(filters={"created_by": author_id})

    # ------------------------------------------------------------------
    # Version history
    # ------------------------------------------------------------------

    def get_version_history(self, domain: str, key: str) -> List[KnowledgeEntry]:
        """Full version history including current (oldest to newest)."""
        domain = domain.lower()
        with self._rwlock.read_lock():
            history = list(self._history.get((domain, key), []))
            current = self._store.get(domain, {}).get(key)
            if current is not None:
                history.append(current)
            return history

    def get_history(self, key: str) -> List[KnowledgeEntry]:
        """Backward compat: get history by key alone."""
        with self._rwlock.read_lock():
            for dom in self._store:
                hist = self.get_version_history(dom, key)
                if hist:
                    return hist
        return []

    def get_version(self, key: str, version: int) -> Optional[KnowledgeEntry]:
        """Backward compat: get a specific version by key."""
        with self._rwlock.read_lock():
            for dom in self._store:
                entry = self.get_with_version(dom, key, version)
                if entry:
                    return entry
        return None

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    def subscribe(
        self,
        domain: str,
        callback: Callable[[str, KnowledgeEntry], None],
    ) -> Callable[[], None]:
        """Subscribe to changes in a knowledge domain.

        Returns an unsubscribe function.
        """
        domain = domain.lower()
        with self._subscriber_lock:
            self._subscribers[domain].add(callback)

        def unsubscribe() -> None:
            with self._subscriber_lock:
                self._subscribers[domain].discard(callback)

        return unsubscribe

    def _notify_subscribers(self, domain: str, entry: KnowledgeEntry) -> None:
        with self._subscriber_lock:
            callbacks = list(self._subscribers.get(domain, set()))
        for cb in callbacks:
            try:
                cb(domain, entry)
            except Exception:
                logger.exception(f"Subscriber callback failed for domain '{domain}'")

    # ------------------------------------------------------------------
    # Snapshot / restore
    # ------------------------------------------------------------------

    def export_snapshot(self) -> Dict[str, Any]:
        """Export the entire knowledge base as a serializable dict."""
        with self._rwlock.read_lock():
            entries_data = []
            for dom_entries in self._store.values():
                for entry in dom_entries.values():
                    entries_data.append(entry.to_dict())

            history_data: Dict[str, List[Dict[str, Any]]] = {}
            for (d, k), hist_entries in self._history.items():
                history_data[f"{d}/{k}"] = [e.to_dict() for e in hist_entries]

        entries_json = json.dumps(entries_data, sort_keys=True, default=str)
        checksum = hashlib.sha256(entries_json.encode()).hexdigest()

        return {
            "snapshot_version": 1,
            "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "entries": entries_data,
            "history": history_data,
            "checksum": checksum,
            "entry_count": len(entries_data),
            "timestamp": time.time(),
        }

    def snapshot(self) -> Dict[str, Any]:
        """Backward compat alias for export_snapshot."""
        return self.export_snapshot()

    def import_snapshot(
        self, data: Dict[str, Any], merge: bool = False
    ) -> Tuple[int, Optional[str]]:
        """Restore (or merge) the knowledge base from a snapshot.

        Returns (entries_imported, error_message).
        """
        if "entries" not in data:
            raise ValueError("Invalid snapshot: missing 'entries'")

        if "checksum" in data:
            entries_json = json.dumps(data["entries"], sort_keys=True, default=str)
            computed = hashlib.sha256(entries_json.encode()).hexdigest()
            if computed != data["checksum"]:
                return 0, f"Checksum mismatch"

        imported = 0

        with self._rwlock.write_lock():
            if not merge:
                self._store.clear()
                self._history.clear()

            for entry_dict in data["entries"]:
                entry = KnowledgeEntry.from_dict(entry_dict)
                dom = entry.domain
                k = entry.key

                if merge:
                    existing = self._store.get(dom, {}).get(k)
                    if existing and existing.version >= entry.version:
                        continue

                self._store.setdefault(dom, {})[k] = entry
                imported += 1

            if "history" in data:
                if not merge:
                    self._history.clear()
                for ck, hist_entries in data["history"].items():
                    parts = ck.split("/", 1)
                    if len(parts) == 2:
                        self._history[(parts[0].lower(), parts[1])] = [
                            KnowledgeEntry.from_dict(e) for e in hist_entries
                        ]

        return imported, None

    def restore(self, snapshot_data: Dict[str, Any]) -> int:
        """Backward compat: restore from snapshot dict. Returns count."""
        n, _ = self.import_snapshot(snapshot_data)
        return n

    def save_snapshot_to_disk(self, path: Optional[str] = None) -> str:
        target = path or self._snapshot_path or str(
            Path.home() / ".eni" / "shared_knowledge" / "snapshot.json"
        )
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        snapshot = self.export_snapshot()
        with open(target, "w") as f:
            json.dump(snapshot, f, indent=2, default=str)
        return target

    def load_snapshot_from_disk(
        self, path: Optional[str] = None, merge: bool = False
    ) -> Tuple[int, Optional[str]]:
        target = path or self._snapshot_path or str(
            Path.home() / ".eni" / "shared_knowledge" / "snapshot.json"
        )
        if not Path(target).exists():
            return 0, f"Snapshot file not found: {target}"
        with open(target, "r") as f:
            data = json.load(f)
        return self.import_snapshot(data, merge=merge)

    # ------------------------------------------------------------------
    # Conflict detection
    # ------------------------------------------------------------------

    def detect_conflict(
        self, key: str, new_value: Any, author_id: str
    ) -> Tuple[bool, Optional[str]]:
        """Detect if a concurrent write would cause a conflict.

        Returns (has_conflict, conflict_details).
        """
        with self._rwlock.read_lock():
            for dom, dom_entries in self._store.items():
                existing = dom_entries.get(key)
                if existing:
                    if existing.created_by != author_id and existing.value != new_value:
                        return True, (
                            f"Conflict: {key} was modified by {existing.created_by}"
                        )
                    return False, None
        return False, None

    # ------------------------------------------------------------------
    # Statistics / diagnostics
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        with self._rwlock.read_lock():
            total = sum(len(d) for d in self._store.values())
            domains = {d: len(e) for d, e in self._store.items()}
            total_hist = sum(len(h) for h in self._history.values())
        return {
            "total_entries": total,
            "domain_counts": domains,
            "total_history_entries": total_hist,
            "total_subscribers": sum(len(s) for s in self._subscribers.values()),
        }

    def list_keys(self) -> List[str]:
        with self._rwlock.read_lock():
            keys = set()
            for dom_entries in self._store.values():
                keys.update(dom_entries.keys())
            return sorted(keys)

    def count(self) -> int:
        return len(self)

    def clear(self) -> None:
        with self._rwlock.write_lock():
            self._store.clear()
            self._history.clear()

    def __len__(self) -> int:
        with self._rwlock.read_lock():
            return sum(len(d) for d in self._store.values())


# ---------------------------------------------------------------------------
# Convenience singleton
# ---------------------------------------------------------------------------

_kb_instance: Optional[SharedKnowledgeBase] = None


def get_shared_knowledge(snapshot_path: Optional[str] = None) -> SharedKnowledgeBase:
    """Get or create the global SharedKnowledgeBase singleton."""
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = SharedKnowledgeBase(snapshot_path=snapshot_path)
    return _kb_instance