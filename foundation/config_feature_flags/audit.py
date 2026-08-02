"""
Immutable configuration change auditing.

Provides:
    - Who / When / What / Why recording for every config change
    - Immutable append-only audit log (conceptually; in-memory for this module)
    - Change diff generation between any two points in time
    - Audit report generation with summary statistics
"""

from __future__ import annotations

import copy
import difflib
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AuditEntry:
    """A single immutable audit record.

    Attributes:
        id: Unique entry identifier (UUID).
        timestamp: Unix timestamp when the change occurred.
        actor: Who made the change (username, service account, system).
        action: What was done (e.g., 'set', 'delete', 'rollback').
        target: The config key or object that was changed.
        old_value: Value before the change (None for creations).
        new_value: Value after the change (None for deletions).
        reason: Why the change was made.
        metadata: Arbitrary additional context.
        hash: Content hash of this entry for tamper detection.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    actor: str = "system"
    action: str = "update"
    target: str = ""
    old_value: Any = None
    new_value: Any = None
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    hash: str = ""

    def __post_init__(self) -> None:
        if not self.hash:
            # Compute a content hash; we need to bypass frozen for this
            object.__setattr__(self, "hash", self._compute_hash())

    def _compute_hash(self) -> str:
        """Compute a SHA-256 hash of the entry contents (excluding the hash itself)."""
        import hashlib

        payload = (
            f"{self.id}:{self.timestamp}:{self.actor}:{self.action}:"
            f"{self.target}:{repr(self.old_value)}:{repr(self.new_value)}:"
            f"{self.reason}"
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def verify(self) -> bool:
        """Check that the entry hash matches its content."""
        return self.hash == self._compute_hash()

    @property
    def datetime_utc(self) -> datetime:
        """Return the timestamp as a UTC datetime."""
        return datetime.fromtimestamp(self.timestamp, tz=timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the entry to a plain dict."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "datetime": self.datetime_utc.isoformat(),
            "actor": self.actor,
            "action": self.action,
            "target": self.target,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "reason": self.reason,
            "metadata": self.metadata,
            "hash": self.hash,
        }


@dataclass
class AuditReport:
    """Summary report generated from audit entries.

    Attributes:
        generated_at: When the report was generated.
        period_start: Start of the reporting period.
        period_end: End of the reporting period.
        total_changes: Number of changes in the period.
        changes_by_actor: Count of changes per actor.
        changes_by_action: Count of changes per action type.
        changes_by_target: Count of changes per target key.
        entries: The underlying audit entries.
    """

    generated_at: float = field(default_factory=time.time)
    period_start: Optional[float] = None
    period_end: Optional[float] = None
    total_changes: int = 0
    changes_by_actor: Dict[str, int] = field(default_factory=dict)
    changes_by_action: Dict[str, int] = field(default_factory=dict)
    changes_by_target: Dict[str, int] = field(default_factory=dict)
    entries: List[AuditEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# AuditTrail
# ---------------------------------------------------------------------------


class AuditTrail:
    """Immutable audit trail for configuration changes.

    Entries are append-only. Once written, an entry cannot be modified
    or deleted.  Tampering can be detected via entry hash verification.

    Usage::

        trail = AuditTrail()

        trail.record(
            actor="alice",
            action="set",
            target="database.host",
            old_value="localhost",
            new_value="db.prod.internal",
            reason="Production migration",
        )

        # Query
        entries = trail.query(target="database.*", since=yesterday)

        # Diff two points in time
        diff = trail.diff(t1, t2)

        # Tamper check
        assert trail.verify_integrity()

        # Generate report
        report = trail.generate_report(start, end)
    """

    def __init__(self, max_entries: int = 10000):
        self._entries: List[AuditEntry] = []
        self._max_entries = max_entries

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        actor: str = "system",
        action: str = "update",
        target: str = "",
        old_value: Any = None,
        new_value: Any = None,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        """Create and append a new audit entry.

        Returns the created AuditEntry.
        """
        entry = AuditEntry(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            actor=actor,
            action=action,
            target=target,
            old_value=copy.deepcopy(old_value),
            new_value=copy.deepcopy(new_value),
            reason=reason,
            metadata=metadata or {},
        )
        self._append(entry)
        return entry

    def record_batch(
        self,
        entries: List[Dict[str, Any]],
    ) -> List[AuditEntry]:
        """Record multiple entries at once.

        Each dict in *entries* should have keys matching AuditEntry
        constructor parameters (actor, action, target, etc.).
        """
        results: List[AuditEntry] = []
        for e in entries:
            result = self.record(**e)
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def query(
        self,
        *,
        actor: Optional[str] = None,
        action: Optional[str] = None,
        target: Optional[str] = None,
        target_pattern: Optional[str] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> List[AuditEntry]:
        """Query audit entries with optional filters.

        Args:
            actor: Filter by actor name (exact match).
            action: Filter by action (exact match).
            target: Filter by target (exact match).
            target_pattern: Filter by target using glob-style wildcard
                            (e.g., 'database.*').
            since: Only entries with timestamp >= since.
            until: Only entries with timestamp <= until.
            limit: Maximum entries to return.
            offset: Number of entries to skip.

        Returns:
            List of matching AuditEntry objects.
        """
        import fnmatch

        results: List[AuditEntry] = []

        for entry in self._entries:
            if actor is not None and entry.actor != actor:
                continue
            if action is not None and entry.action != action:
                continue
            if target is not None and entry.target != target:
                continue
            if target_pattern is not None and not fnmatch.fnmatch(
                entry.target, target_pattern
            ):
                continue
            if since is not None and entry.timestamp < since:
                continue
            if until is not None and entry.timestamp > until:
                continue

            results.append(entry)

        return results[offset : offset + limit]

    def get_entry(self, entry_id: str) -> Optional[AuditEntry]:
        """Retrieve a single entry by its UUID."""
        for entry in self._entries:
            if entry.id == entry_id:
                return entry
        return None

    def get_latest(self, target: str) -> Optional[AuditEntry]:
        """Return the most recent entry for *target*."""
        latest: Optional[AuditEntry] = None
        for entry in reversed(self._entries):
            if entry.target == target:
                if latest is None or entry.timestamp > latest.timestamp:
                    latest = entry
        return latest

    def count(self, **filters: Any) -> int:
        """Count entries matching optional filters (same as query)."""
        return len(self.query(**filters))

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self):
        return iter(self._entries)

    def __getitem__(self, idx: int) -> AuditEntry:
        return self._entries[idx]

    # ------------------------------------------------------------------
    # Diff generation
    # ------------------------------------------------------------------

    def diff(
        self,
        t1: Optional[float] = None,
        t2: Optional[float] = None,
        *,
        target_filter: Optional[str] = None,
    ) -> str:
        """Generate a unified diff of config state between two timestamps.

        Args:
            t1: Start timestamp (inclusive). Default: beginning of log.
            t2: End timestamp (inclusive). Default: end of log.
            target_filter: Optional glob pattern to limit to certain targets.

        Returns:
            A unified diff string.
        """
        state_at_t1 = self._reconstruct_state(at_time=t1, target_filter=target_filter)
        state_at_t2 = self._reconstruct_state(at_time=t2, target_filter=target_filter)

        lines_a = self._state_to_lines(state_at_t1)
        lines_b = self._state_to_lines(state_at_t2)

        diff_lines = difflib.unified_diff(
            lines_a,
            lines_b,
            fromfile=f"config@{t1 or 'start'}",
            tofile=f"config@{t2 or 'end'}",
            lineterm="",
        )
        return "\n".join(diff_lines)

    def changes_between(
        self, t1: float, t2: float, **filters: Any
    ) -> List[AuditEntry]:
        """Return all entries with timestamps between *t1* and *t2*."""
        return self.query(since=t1, until=t2, **filters)

    # ------------------------------------------------------------------
    # Integrity
    # ------------------------------------------------------------------

    def verify_integrity(self) -> Tuple[bool, List[str]]:
        """Verify that all entries' hashes match their content.

        Returns (valid: bool, errors: list of error strings).
        """
        errors: List[str] = []
        for entry in self._entries:
            if not entry.verify():
                errors.append(
                    f"Integrity violation: entry {entry.id} "
                    f"(target: {entry.target}, actor: {entry.actor})"
                )
        return len(errors) == 0, errors

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def generate_report(
        self,
        period_start: Optional[float] = None,
        period_end: Optional[float] = None,
        *,
        actor: Optional[str] = None,
    ) -> AuditReport:
        """Generate an audit summary report for a time period.

        Args:
            period_start: Start of reporting period.
            period_end: End of reporting period.
            actor: Optional filter by actor.

        Returns:
            AuditReport with summary statistics.
        """
        entries = self.query(since=period_start, until=period_end, actor=actor)

        report = AuditReport(
            generated_at=time.time(),
            period_start=period_start,
            period_end=period_end,
            total_changes=len(entries),
            entries=list(entries),
        )

        for entry in entries:
            report.changes_by_actor[entry.actor] = (
                report.changes_by_actor.get(entry.actor, 0) + 1
            )
            report.changes_by_action[entry.action] = (
                report.changes_by_action.get(entry.action, 0) + 1
            )
            report.changes_by_target[entry.target] = (
                report.changes_by_target.get(entry.target, 0) + 1
            )

        return report

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    def snapshot(self, at_time: Optional[float] = None) -> Dict[str, Any]:
        """Reconstruct the full config state as of *at_time*.

        Walks all entries up to *at_time* and applies them to produce
        a single state dict.  Returns an empty dict if no entries exist.
        """
        return self._reconstruct_state(at_time=at_time)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export(self) -> List[Dict[str, Any]]:
        """Export all entries as a list of dicts."""
        return [entry.to_dict() for entry in self._entries]

    def export_json(self) -> str:
        """Export all entries as a JSON string."""
        import json
        return json.dumps(self.export(), indent=2, default=str)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _append(self, entry: AuditEntry) -> None:
        """Append an entry, trimming if over max."""
        self._entries.append(entry)
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]

    def _reconstruct_state(
        self,
        at_time: Optional[float] = None,
        target_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Reconstruct config state by replaying entries."""
        import fnmatch

        state: Dict[str, Any] = {}
        for entry in self._entries:
            if at_time is not None and entry.timestamp > at_time:
                break
            if target_filter and not fnmatch.fnmatch(entry.target, target_filter):
                continue
            if entry.action == "delete":
                state.pop(entry.target, None)
            else:
                state[entry.target] = copy.deepcopy(entry.new_value)
        return state

    @staticmethod
    def _state_to_lines(state: Dict[str, Any]) -> List[str]:
        """Convert a state dict to sorted lines for diffing."""
        lines: List[str] = []
        for key in sorted(state):
            lines.append(f"{key} = {repr(state[key])}")
        return lines