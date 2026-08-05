#!/usr/bin/env python3
"""
ENI Swarm Bridge — Member Heartbeat + Liveness Registry
========================================================
Master-class swarm health layer for the ENI interop bridge.

Provides real, clock-driven liveness tracking (no stubs):

  SwarmMember       — single swarm participant (id, role, addr, capabilities,
                      status: alive/absent/lost, last_heartbeat).
  MemberRegistry    — in-memory registry with OPTIONAL SQLite persistence.
                      register / unregister / list (filter by role+status) / get.
  HeartbeatProtocol — send_heartbeat(member_id) stamps liveness + marks alive;
                      check_liveness(now, timeout) flags members with stale
                      heartbeats as absent/lost and returns the affected set.
  HealthAggregator  — folds live member statuses into a swarm-level health
                      verdict (alive/absent counts, critical-role loss, healthy
                      vs degraded vs down) via health().

The clock is injectable (SwarmClock or any object exposing now()) so tests can
drive time deterministically.  Stdlib only — no third-party dependencies.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set, Union, cast

logger = logging.getLogger("enterprise.swarm.heartbeat")

# Canonical member statuses
STATUS_ALIVE = "alive"
STATUS_ABSENT = "absent"
STATUS_LOST = "lost"

# Default heartbeat staleness threshold (seconds)
DEFAULT_HEARTBEAT_TIMEOUT = 30.0


# =============================================================================
# Clock — injectable time source
# =============================================================================
class SwarmClock:
    """Injectable monotonic clock.

    Exposes ``now()`` returning a float timestamp.  Production uses
    ``time.monotonic()``; tests substitute a fake clock to fast-forward time.
    """

    def now(self) -> float:
        return time.monotonic()


class FixedClock:
    """Test/deterministic clock.

    Starts at a fixed ``start`` offset and only advances when ``advance()``
    is called — lets tests control liveness transitions precisely.
    """

    def __init__(self, start: float = 0.0) -> None:
        self._t = start

    def now(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += seconds

    def set(self, value: float) -> None:
        self._t = value


# =============================================================================
# SwarmMember
# =============================================================================
@dataclass
class SwarmMember:
    """A single participant in the swarm.

    Attributes:
        member_id:       Unique identifier for this member.
        role:            Functional role (e.g. "worker", "builder", "coordinator").
        addr:            Network/transport address of the member.
        capabilities:    Optional list of capability tags.
        status:          alive / absent / lost — authoritative liveness state.
        last_heartbeat:  Monotonic timestamp of the most recent heartbeat, or None.
        registered_at:   Monotonic timestamp when the member was registered.
    """

    member_id: str
    role: str
    addr: str
    capabilities: List[str] = field(default_factory=list)
    status: str = STATUS_ALIVE
    last_heartbeat: Optional[float] = None
    registered_at: Optional[float] = None

    def mark_alive(self, timestamp: Optional[float] = None) -> None:
        """Stamp a fresh heartbeat and flip status to alive."""
        self.last_heartbeat = timestamp
        self.status = STATUS_ALIVE

    def is_alive(self) -> bool:
        return self.status in (STATUS_ALIVE,)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "SwarmMember":
        allowed = {
            "member_id",
            "role",
            "addr",
            "capabilities",
            "status",
            "last_heartbeat",
            "registered_at",
        }
        kwargs = {k: v for k, v in data.items() if k in allowed}
        caps_val = cast(Optional[List[str]], kwargs.get("capabilities"))
        last_hb = kwargs.get("last_heartbeat")
        reg_at = kwargs.get("registered_at")
        return cls(
            member_id=str(kwargs.get("member_id", "")),
            role=str(kwargs.get("role", "")),
            addr=str(kwargs.get("addr", "")),
            capabilities=list(caps_val or []),
            status=str(kwargs.get("status", STATUS_ALIVE)),
            last_heartbeat=float(cast(float, last_hb)) if last_hb is not None else None,
            registered_at=float(cast(float, reg_at)) if reg_at is not None else None,
        )


# =============================================================================
# MemberRegistry
# =============================================================================
class MemberRegistry:
    """Registry of swarm members with OPTIONAL SQLite persistence.

    Stores members in memory keyed by ``member_id``.  If ``db_path`` is given,
    every mutation (register/unregister) is also mirrored to a SQLite table so
    membership survives process restarts.  All methods are per-instance and
    thread-safe.
    """

    def __init__(self, db_path: Optional[str] = None, clock: Optional[SwarmClock] = None) -> None:
        self._members: Dict[str, SwarmMember] = {}
        self._lock = threading.RLock()
        self._db_path: Optional[str] = db_path
        self._clock = clock or SwarmClock()
        if db_path is not None:
            self._init_db(db_path)

    # -- SQLite persistence -------------------------------------------------
    def _init_db(self, db_path: str) -> None:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS swarm_members (
                    member_id       TEXT PRIMARY KEY,
                    role            TEXT,
                    addr            TEXT,
                    capabilities    TEXT,
                    status          TEXT,
                    last_heartbeat  REAL,
                    registered_at   REAL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def _persist(self, member: SwarmMember) -> None:
        if self._db_path is None:
            return
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO swarm_members
                    (member_id, role, addr, capabilities, status,
                     last_heartbeat, registered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    member.member_id,
                    member.role,
                    member.addr,
                    json.dumps(member.capabilities),
                    member.status,
                    member.last_heartbeat,
                    member.registered_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _delete_row(self, member_id: str) -> None:
        if self._db_path is None:
            return
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("DELETE FROM swarm_members WHERE member_id = ?", (member_id,))
            conn.commit()
        finally:
            conn.close()

    def load_persisted(self) -> int:
        """Load members previously persisted to SQLite into memory.  Returns count."""
        if self._db_path is None:
            return 0
        loaded = 0
        conn = sqlite3.connect(self._db_path)
        try:
            rows = conn.execute(
                "SELECT member_id, role, addr, capabilities, status, "
                "last_heartbeat, registered_at FROM swarm_members"
            ).fetchall()
        finally:
            conn.close()
        with self._lock:
            for row in rows:
                member_id, role, addr, cap_json, status, lh, ra = row
                caps: List[str] = []
                if cap_json:
                    try:
                        caps = json.loads(cap_json)
                    except (ValueError, TypeError):
                        caps = []
                self._members[member_id] = SwarmMember(
                    member_id=member_id,
                    role=role,
                    addr=addr,
                    capabilities=caps,
                    status=status or STATUS_ALIVE,
                    last_heartbeat=lh,
                    registered_at=ra,
                )
                loaded += 1
        return loaded

    # -- CRUD ----------------------------------------------------------------
    def register(self, member: SwarmMember) -> SwarmMember:
        """Add a member to the registry.

        If the member resolves relative to the registry clock (no explicit
        registered_at), the registration time and an initial heartbeat are
        stamped so the member starts alive.  Re-registering an existing id
        replaces it (upsert semantics).
        """
        with self._lock:
            now = self._clock.now()
            if member.registered_at is None:
                member.registered_at = now
            if member.last_heartbeat is None:
                member.last_heartbeat = now
            member.status = STATUS_ALIVE
            self._members[member.member_id] = member
            self._persist(member)
            return member

    def unregister(self, member_id: str) -> Optional[SwarmMember]:
        """Remove a member.  Returns the removed member, or None if absent."""
        with self._lock:
            removed = self._members.pop(member_id, None)
            if removed is not None:
                self._delete_row(member_id)
            return removed

    def get(self, member_id: str) -> Optional[SwarmMember]:
        with self._lock:
            return self._members.get(member_id)

    def get_or_raise(self, member_id: str) -> SwarmMember:
        member = self.get(member_id)
        if member is None:
            raise KeyError(f"unknown swarm member: {member_id!r}")
        return member

    def contains(self, member_id: str) -> bool:
        return self.get(member_id) is not None

    def __contains__(self, member_id: object) -> bool:
        if not isinstance(member_id, str):
            return False
        return self.contains(member_id)

    def __len__(self) -> int:
        with self._lock:
            return len(self._members)

    def list(
        self,
        role: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[SwarmMember]:
        """Return members, optionally filtered by role and/or status."""
        with self._lock:
            members = list(self._members.values())
        if role is not None:
            members = [m for m in members if m.role == role]
        if status is not None:
            members = [m for m in members if m.status == status]
        # stable ordering for deterministic tests
        members.sort(key=lambda m: m.member_id)
        return members

    def roles(self) -> Set[str]:
        with self._lock:
            return {m.role for m in self._members.values()}

    def snapshots(self) -> List[Dict[str, object]]:
        with self._lock:
            return [m.to_dict() for m in self._members.values()]

    def clear(self) -> None:
        with self._lock:
            self._members.clear()
        if self._db_path is not None:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute("DELETE FROM swarm_members")
                conn.commit()
            finally:
                conn.close()


# =============================================================================
# HeartbeatProtocol
# =============================================================================
class HeartbeatProtocol:
    """Drives member liveness through heartbeat reception and expiry checking.

    ``send_heartbeat`` records fresh life at the current clock time and marks
    the member alive.  ``check_liveness`` scans every member and flips those
    whose heartbeats have gone stale past ``timeout`` to absent (first miss)
    or lost (consecutive misses), returning the set of members affected by the
    transition in this pass.  Unknown members raise KeyError so callers surface
    misconfiguration instead of silently swallowing it.
    """

    def __init__(
        self,
        registry: MemberRegistry,
        floor_misses: int = 2,
        clock: Optional[SwarmClock] = None,
    ) -> None:
        self._registry = registry
        self._clock = clock or getattr(registry, "_clock", None) or SwarmClock()
        # floor_misses = consecutive missed passes tolerated before "lost".
        # First miss -> absent; once misses >= floor, escalate to lost.
        self._floor_misses = max(1, int(floor_misses))
        self._miss_counts: Dict[str, int] = {}

    def now(self) -> float:
        return self._clock.now()

    # -- heartbeat reception ------------------------------------------------
    def send_heartbeat(
        self,
        member_id: str,
        timestamp: Optional[float] = None,
    ) -> SwarmMember:
        """Record a heartbeat for a registered member and mark it alive."""
        member = self._registry.get(member_id)
        if member is None:
            raise KeyError(f"cannot heartbeat unregistered member: {member_id!r}")
        ts = self._clock.now() if timestamp is None else timestamp
        with getattr(self._registry, "_lock", threading.RLock()):
            member.mark_alive(ts)
            self._registry._persist(member)
        self._miss_counts[member_id] = 0
        return member

    def mark_alive(self, member_id: str) -> SwarmMember:
        """Force a member to the alive state without updating its heartbeat time."""
        member = self._registry.get(member_id)
        if member is None:
            raise KeyError(f"cannot mark unregistered member alive: {member_id!r}")
        with getattr(self._registry, "_lock", threading.RLock()):
            member.status = STATUS_ALIVE
            self._registry._persist(member)
        self._miss_counts[member_id] = 0
        return member

    def register_member(
        self,
        member: SwarmMember,
        heartbeat: bool = False,
    ) -> SwarmMember:
        """Register a member through the protocol.

        With ``heartbeat=True`` an initial heartbeat is stamped so the member
        is immediately alive.  Otherwise the registration timestamp itself is
        treated as the life anchor.
        """
        self._registry.register(member)
        if heartbeat:
            self.send_heartbeat(member.member_id)
        self._miss_counts[member.member_id] = 0
        return member

    # -- liveness checking ---------------------------------------------------
    def check_liveness(
        self,
        now: Optional[float] = None,
        timeout: float = DEFAULT_HEARTBEAT_TIMEOUT,
    ) -> List[SwarmMember]:
        """Flag members with stale heartbeats as absent/lost.

        A member whose ``last_heartbeat`` is more than ``timeout`` seconds in
        the past is marked ``absent`` on the first missed pass and ``lost`` on
        subsequent consecutive misses (when ``floor_misses > 1``).  Returns the
        list of members whose status changed during this pass.
        """
        ts = self._clock.now() if now is None else now
        affected: List[SwarmMember] = []

        members = self._registry.list()
        for member in members:
            age = float("inf") if member.last_heartbeat is None else (ts - member.last_heartbeat)
            if age <= timeout:
                # fresh — reset any pending miss streak
                self._miss_counts[member.member_id] = 0
                continue

            self._miss_counts[member.member_id] = self._miss_counts.get(member.member_id, 0) + 1
            misses = self._miss_counts[member.member_id]

            new_status = STATUS_LOST if misses >= self._floor_misses else STATUS_ABSENT
            if member.status != new_status:
                member.status = new_status
                self._registry._persist(member)
                affected.append(member)

        return affected

    # backwards/alias: idiomatic name
    check_health = check_liveness

    def tick(
        self,
        now: Optional[float] = None,
        timeout: float = DEFAULT_HEARTBEAT_TIMEOUT,
    ) -> List[SwarmMember]:
        return self.check_liveness(now=now, timeout=timeout)


# =============================================================================
# HealthAggregator
# =============================================================================
@dataclass
class HealthReport:
    """Immutable snapshot of swarm health at a point in time."""

    status: str  # healthy | degraded | down
    healthy: bool
    alive_count: int
    absent_count: int
    lost_count: int
    total: int
    required: int
    missing_required: int
    critical_roles_lost: List[str]
    members: List[Dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "status": self.status,
            "healthy": self.healthy,
            "alive_count": self.alive_count,
            "absent_count": self.absent_count,
            "lost_count": self.lost_count,
            "total": self.total,
            "required": self.required,
            "missing_required": self.missing_required,
            "critical_roles_lost": self.critical_roles_lost,
            "members": self.members,
        }


class HealthAggregator:
    """Aggregates per-member liveness into a swarm-level health verdict.

    The swarm is ``healthy`` when the number of alive members meets ``required``
    AND no critical role is fully lost.  It is ``degraded`` when alive count is
    below required (but non-zero) or a critical role lost members.  It is
    ``down`` when no member is alive.
    """

    def __init__(
        self,
        registry: MemberRegistry,
        required: int = 1,
        critical_roles: Optional[Set[str]] = None,
        heartbeat_timeout: float = DEFAULT_HEARTBEAT_TIMEOUT,
        clock: Optional[SwarmClock] = None,
    ) -> None:
        self._registry = registry
        self._required = max(0, int(required))
        self._critical_roles: Set[str] = set(critical_roles or [])
        self._heartbeat_timeout = float(heartbeat_timeout)
        self._clock = clock or getattr(registry, "_clock", None) or SwarmClock()
        self._protocol = HeartbeatProtocol(registry, clock=self._clock)

    def health(
        self,
        now: Optional[float] = None,
        timeout: Optional[float] = None,
        apply_liveness: bool = True,
    ) -> HealthReport:
        """Compute swarm health.

        Unless ``apply_liveness=False``, stale members are first flipped by the
        heartbeat protocol so the verdict reflects current liveness.
        """
        ts = self._clock.now() if now is None else now
        if timeout is None:
            timeout = self._heartbeat_timeout
        if apply_liveness:
            self._protocol.check_liveness(now=ts, timeout=timeout)

        members = self._registry.list()
        alive = [m for m in members if m.is_alive()]
        absent = [m for m in members if m.status == STATUS_ABSENT]
        lost = [m for m in members if m.status == STATUS_LOST]
        alive_count = len(alive)
        absent_count = len(absent)
        lost_count = len(lost)
        total = len(members)

        # critical roles with zero alive members
        critical_lost = sorted(
            r for r in self._critical_roles
            if r in self._registry.roles() and not any(m.role == r and m.is_alive() for m in members)
        )

        healthy = (alive_count >= self._required) and not critical_lost
        missing_required = max(0, self._required - alive_count)

        if alive_count == 0:
            status = "down"
            healthy = False
        elif healthy:
            status = "healthy"
        else:
            status = "degraded"

        report = HealthReport(
            status=status,
            healthy=healthy,
            alive_count=alive_count,
            absent_count=absent_count,
            lost_count=lost_count,
            total=total,
            required=self._required,
            missing_required=missing_required,
            critical_roles_lost=critical_lost,
            members=[m.to_dict() for m in members],
        )
        return report


# Convenience — a single registry+protocol+aggregator bundle
class SwarmHealth:
    """High-level facade bundling registry, protocol, and aggregator."""

    def __init__(
        self,
        required: int = 1,
        critical_roles: Optional[Set[str]] = None,
        db_path: Optional[str] = None,
        clock: Optional[SwarmClock] = None,
    ) -> None:
        self.clock = clock or SwarmClock()
        self.registry = MemberRegistry(db_path=db_path, clock=self.clock)
        self.protocol = HeartbeatProtocol(self.registry, clock=self.clock)
        self.aggregator = HealthAggregator(
            self.registry,
            required=required,
            critical_roles=critical_roles,
            clock=self.clock,
        )

    def health(self, **kwargs: object) -> HealthReport:
        return self.aggregator.health(**kwargs)  # type: ignore[arg-type]


__all__ = [
    "STATUS_ALIVE",
    "STATUS_ABSENT",
    "STATUS_LOST",
    "DEFAULT_HEARTBEAT_TIMEOUT",
    "SwarmClock",
    "FixedClock",
    "SwarmMember",
    "MemberRegistry",
    "HeartbeatProtocol",
    "HealthAggregator",
    "HealthReport",
    "SwarmHealth",
]
