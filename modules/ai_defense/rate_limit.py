"""Sliding-window rate limiter + persistent attacker state for ENI AI Defense.

Master-class offense-defense layer: real throttling (not stubs) plus durable
per-attacker state that survives process restarts.

Three cooperating components, all stdlib-only:

* :class:`SlidingWindowRateLimiter` --- per-key (ip/account) sliding-window
  request counter. Thread-safe. ``allow()`` returns the standard
  ``(allowed, remaining, reset_in)`` triple used by API gateways.
* :class:`AttackerStore` --- SQLite-backed persistence of per-attacker records
  keyed by ip/account: ``first_seen``, ``last_seen``, ``attempt_count``,
  ``block_until`` and a JSON ``flags`` list. Survives restarts. Use ``db_path``
  = a file path to persist, or ``None`` for an in-memory database.
* :class:`ThrottleGate`` --- composes the two: a request is denied if the key is
  currently blocked (``block_until`` in the future) OR the sliding-window limit
  is exceeded. Every decision is recorded as an attacker attempt and sustained
  volume beyond a threshold auto-blocks the key.

Time is injectable on every component (``clock`` callable returning epoch
seconds) so tests drive bursts, window slides and lockout expiry deterministically.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional, Sequence, Tuple

__all__ = [
    "SlidingWindowRateLimiter",
    "AttackerStore",
    "ThrottleGate",
    "Allowance",
    "DEFAULT_CLOCK",
]

DEFAULT_CLOCK: Callable[[], float] = time.time


# ---------------------------------------------------------------------------
# Allowance result
# ---------------------------------------------------------------------------
@dataclass
class Allowance:
    """Result of a :meth:`ThrottleGate.allow` decision.

    Attributes
    ----------
    allowed:
        True if the request may proceed.
    remaining:
        Number of requests the key may still make inside the current window
        before hitting the limit (``0`` when denied / blocked).
    reset_in:
        Seconds until the window frees a slot (or until the block expires when
        ``blocked`` is True). ``0.0`` when there is no pending constraint.
    blocked:
        True when the denial came from a persistent attacker block (not the
        sliding window). Implies ``allowed is False``.
    reason:
        Machine-readable reason: ``"allowed"``, ``"rate_limited"``,
        ``"blocked"`` or ``"offline"``.
    """

    allowed: bool
    remaining: int = 0
    reset_in: float = 0.0
    blocked: bool = False
    reason: str = ""

    def __bool__(self) -> bool:
        return self.allowed


# ---------------------------------------------------------------------------
# SlidingWindowRateLimiter
# ---------------------------------------------------------------------------
class SlidingWindowRateLimiter:
    """Per-key sliding-window counter.

    Tracks the exact timestamps of recent ``allow()`` calls per key and prunes
    those older than ``window`` seconds on each access, giving a true sliding
    window (older calls expire continuously rather than at bucket boundaries).

    Thread-safe: all mutations happen under an internal lock.
    """

    def __init__(
        self,
        limit: int = 100,
        window: float = 60.0,
        clock: Callable[[], float] = DEFAULT_CLOCK,
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if window <= 0:
            raise ValueError("window must be > 0")
        self.limit = int(limit)
        self.window = float(window)
        self.clock = clock
        self._lock = threading.Lock()
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, key: str, cost: int = 1, now: Optional[float] = None) -> Tuple[bool, int, float]:
        """Attempt to allow ``cost`` requests from ``key`` in the current window.

        Returns ``(allowed, remaining, reset_in)``:
        * ``allowed`` --- True if the request fits under the sliding window.
        * ``remaining`` --- slots left for this key in the window after this call
          (``0`` when denied).
        * ``reset_in`` --- seconds until the oldest recorded hit in the window
          expires (i.e. when the next slot would free).
        """
        if cost < 1:
            cost = 1
        now = self.clock() if now is None else now
        with self._lock:
            dq = self._hits[key]
            cutoff = now - self.window
            while dq and dq[0] <= cutoff:
                dq.popleft()
            if len(dq) >= self.limit:
                reset_in = (self.window - (now - dq[0])) if dq else 0.0
                return (False, 0, max(0.0, reset_in))
            for _ in range(int(cost)):
                dq.append(now)
            remaining = max(0, self.limit - len(dq))
            reset_in = (self.window - (now - dq[0])) if dq else 0.0
            return (True, remaining, max(0.0, reset_in))

    def count(self, key: str, now: Optional[float] = None) -> int:
        """Current number of live (unexpired) hits for ``key``."""
        now = self.clock() if now is None else now
        with self._lock:
            dq = self._hits[key]
            cutoff = now - self.window
            while dq and dq[0] <= cutoff:
                dq.popleft()
            return len(dq)

    def reset(self, key: str) -> None:
        """Forget all recorded history for ``key``."""
        with self._lock:
            self._hits.pop(key, None)

    def reset_all(self) -> None:
        with self._lock:
            self._hits.clear()

    def snapshot(self) -> Dict[str, int]:
        """Map of key -> live hit count (for monitoring / posture)."""
        now = self.clock()
        out: Dict[str, int] = {}
        with self._lock:
            for key, dq in self._hits.items():
                cutoff = now - self.window
                while dq and dq[0] <= cutoff:
                    dq.popleft()
                if dq:
                    out[key] = len(dq)
        return out


# ---------------------------------------------------------------------------
# AttackerStore (SQLite persistence)
# ---------------------------------------------------------------------------
class AttackerStore:
    """Durable per-attacker state keyed by ip/account.

    Persists each attacker's history --- first/last seen, running attempt count,
    pending block time and free-form flags --- in a SQLite database. Records
    survive process restarts when ``db_path`` points at a real file; pass
    ``db_path=None`` for a transient in-memory database.

    Thread-safe: all database access is serialized under an internal lock and
    the connection is created with ``check_same_thread=False``.
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS attackers (
        key          TEXT PRIMARY KEY,
        first_seen   REAL NOT NULL,
        last_seen    REAL NOT NULL,
        attempt_count INTEGER NOT NULL DEFAULT 0,
        block_until  REAL NOT NULL DEFAULT 0,
        flags        TEXT NOT NULL DEFAULT '[]'
    )
    """

    def __init__(self, db_path: Optional[Any] = None) -> None:
        self.db_path = None if db_path is None else str(db_path)
        if self.db_path and self.db_path != ":memory:":
            parent = Path(self.db_path).parent
            if str(parent) not in ("", "."):
                parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            self.db_path if self.db_path else ":memory:",
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(self._SCHEMA)
            self._conn.commit()

    # -- internal helpers ---------------------------------------------------
    def _now(self, now: Optional[float]) -> float:
        return time.time() if now is None else float(now)

    def _read_flags(self, raw: str) -> List[str]:
        try:
            parsed = json.loads(raw or "[]")
            return list(parsed) if isinstance(parsed, list) else []
        except (ValueError, TypeError):
            return []

    # -- record lifecycle ----------------------------------------------------
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Return the stored record for ``key`` as a dict, or ``None``."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM attackers WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        rec = dict(row)
        rec["flags"] = self._read_flags(rec["flags"])
        return rec

    def add_attempt(self, key: str, now: Optional[float] = None, flag: Optional[str] = None) -> Dict[str, Any]:
        """Record one attempt for ``key`` (create the record on first sight).

        On first sight sets ``first_seen``; always bumps ``attempt_count`` and
        ``last_seen``; appends ``flag`` (if given) to the flags list.
        """
        now = self._now(now)
        with self._lock:
            existing = self._conn.execute(
                "SELECT flags FROM attackers WHERE key = ?", (key,)
            ).fetchone()
            if existing is None:
                flags = [flag] if flag else []
                self._conn.execute(
                    "INSERT INTO attackers (key, first_seen, last_seen, attempt_count, flags) "
                    "VALUES (?, ?, ?, 1, ?)",
                    (key, now, now, json.dumps(flags)),
                )
            else:
                flags = self._read_flags(existing["flags"])
                if flag and flag not in flags:
                    flags.append(flag)
                self._conn.execute(
                    "UPDATE attackers SET last_seen = ?, attempt_count = attempt_count + 1, "
                    "flags = ? WHERE key = ?",
                    (now, json.dumps(flags), key),
                )
            self._conn.commit()
        return self.get(key) or {}

    def bump(self, key: str, now: Optional[float] = None, flag: Optional[str] = None) -> Dict[str, Any]:
        """Increment an existing record's attempt count (create at 0 if absent)."""
        now = self._now(now)
        with self._lock:
            existing = self._conn.execute(
                "SELECT flags FROM attackers WHERE key = ?", (key,)
            ).fetchone()
            if existing is None:
                flags = [flag] if flag else []
                self._conn.execute(
                    "INSERT INTO attackers (key, first_seen, last_seen, attempt_count, flags) "
                    "VALUES (?, ?, ?, 1, ?)",
                    (key, now, now, json.dumps(flags)),
                )
            else:
                flags = self._read_flags(existing["flags"])
                if flag and flag not in flags:
                    flags.append(flag)
                self._conn.execute(
                    "UPDATE attackers SET last_seen = ?, attempt_count = attempt_count + 1, "
                    "flags = ? WHERE key = ?",
                    (now, json.dumps(flags), key),
                )
            self._conn.commit()
        return self.get(key) or {}

    # -- blocking ------------------------------------------------------------
    def block(self, key: str, until: float, flag: Optional[str] = None) -> Dict[str, Any]:
        """Set ``block_until`` for ``key`` (seconds epoch). Creates if absent."""
        now = time.time()
        with self._lock:
            existing = self._conn.execute(
                "SELECT flags FROM attackers WHERE key = ?", (key,)
            ).fetchone()
            flags = self._read_flags(existing["flags"]) if existing else []
            if flag and flag not in flags:
                flags.append(flag)
            if existing is None:
                self._conn.execute(
                    "INSERT INTO attackers (key, first_seen, last_seen, attempt_count, block_until, flags) "
                    "VALUES (?, ?, ?, 0, ?, ?)",
                    (key, now, now, float(until), json.dumps(flags)),
                )
            else:
                self._conn.execute(
                    "UPDATE attackers SET block_until = ?, flags = ? WHERE key = ?",
                    (float(until), json.dumps(flags), key),
                )
            self._conn.commit()
        return self.get(key) or {}

    def blocked(self, key: str, now: Optional[float] = None) -> bool:
        """True if ``key`` is currently blocked (``block_until`` strictly in the future)."""
        now = self._now(now)
        with self._lock:
            row = self._conn.execute(
                "SELECT block_until FROM attackers WHERE key = ?", (key,)
            ).fetchone()
        return bool(row and row["block_until"] > now)

    def is_blocked(self, key: str, now: Optional[float] = None) -> bool:
        """Alias of :meth:`blocked`."""
        return self.blocked(key, now)

    def block_remaining(self, key: str, now: Optional[float] = None) -> float:
        """Seconds until an active block expires (``0.0`` if not blocked)."""
        now = self._now(now)
        with self._lock:
            row = self._conn.execute(
                "SELECT block_until FROM attackers WHERE key = ?", (key,)
            ).fetchone()
        if row and row["block_until"] > now:
            return max(0.0, row["block_until"] - now)
        return 0.0

    def unblock(self, key: str) -> None:
        """Clear a key's block (sets ``block_until`` to 0)."""
        with self._lock:
            self._conn.execute(
                "UPDATE attackers SET block_until = 0 WHERE key = ?", (key,)
            )
            self._conn.commit()

    # -- listing / lifecycle -------------------------------------------------
    def list(self, limit: int = 100, now: Optional[float] = None) -> List[Dict[str, Any]]:
        """All attacker records, most recently active first."""
        now = self._now(now)
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM attackers ORDER BY last_seen DESC LIMIT ?", (int(limit),)
            ).fetchall()
        out = []
        for row in rows:
            rec = dict(row)
            rec["flags"] = self._read_flags(rec["flags"])
            rec["currently_blocked"] = rec["block_until"] > now
            out.append(rec)
        return out

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass


# ---------------------------------------------------------------------------
# ThrottleGate
# ---------------------------------------------------------------------------
class ThrottleGate:
    """Combines the sliding-window limiter with persistent attacker state.

    ``allow(key)``:
      1. If the key is currently *blocked* (``block_until`` in the future) ->
         deny with ``blocked=True``.
      2. Else consult the sliding-window limiter. Over the limit -> deny
         (``reason="rate_limited"``) and record the attempt.
      3. Otherwise allow, record the attempt, and if the key's total attempt
         count has reached ``threshold`` auto-block it for ``block_seconds``.

    All state is durable when the store is file-backed; time is injectable via
    ``clock`` for deterministic tests.
    """

    def __init__(
        self,
        limit: int = 100,
        window: float = 60.0,
        threshold: int = 50,
        block_seconds: float = 300.0,
        db_path: Optional[Any] = None,
        clock: Callable[[], float] = DEFAULT_CLOCK,
        limiter: Optional[SlidingWindowRateLimiter] = None,
        store: Optional[AttackerStore] = None,
    ) -> None:
        if threshold < 1:
            raise ValueError("threshold must be >= 1")
        self.threshold = int(threshold)
        self.block_seconds = float(block_seconds)
        self.clock = clock
        self.limiter = limiter or SlidingWindowRateLimiter(limit=limit, window=window, clock=clock)
        self.store = store or AttackerStore(db_path)
        self._lock = threading.Lock()

    def allow(self, key: str, cost: int = 1, now: Optional[float] = None) -> Allowance:
        """Evaluate one request from ``key`` against limit + attacker state."""
        now = self.clock() if now is None else float(now)
        if self.store.blocked(key, now):
            reset_in = self.store.block_remaining(key, now)
            self.store.bump(key, now, flag="blocked")
            return Allowance(False, 0, reset_in, blocked=True, reason="blocked")

        allowed, remaining, reset_in = self.limiter.allow(key, cost, now)
        if not allowed:
            self.store.add_attempt(key, now, flag="rate_limited")
            return Allowance(False, 0, reset_in, blocked=False, reason="rate_limited")

        self.store.add_attempt(key, now, flag="allowed")
        rec = self.store.get(key) or {}
        if rec.get("attempt_count", 0) >= self.threshold:
            until = now + self.block_seconds
            self.store.block(key, until, flag="auto_block")
            self.store.bump(key, now, flag="blocked")
            return Allowance(True, remaining, 0.0, blocked=False, reason="allowed")
        return Allowance(True, remaining, reset_in, blocked=False, reason="allowed")

    def blocked(self, key: str, now: Optional[float] = None) -> bool:
        """True if the key is currently blocked in the attacker store."""
        return self.store.blocked(key, now)

    def attempt_count(self, key: str) -> int:
        rec = self.store.get(key)
        return rec["attempt_count"] if rec else 0

    def record(self, key: str, flag: str = "manual", now: Optional[float] = None) -> None:
        """Manually record an attempt (e.g. an auth failure) into attacker state."""
        self.store.add_attempt(key, now, flag=flag)

    def close(self) -> None:
        self.store.close()
