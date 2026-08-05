"""Tests for the master-class rate-limiting / persistent-attacker layer of ai_defense.

Covers:
* SlidingWindowRateLimiter --- under-limit allow, over-limit block, window slide.
* AttackerStore --- persistent records, survives reopen, block lifecycle.
* ThrottleGate --- combines limiter + store, threshold auto-block, expiry.
* Clock injection, lifecycle, and the (OFF-by-default) facade wiring.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest

from enterprise.modules.ai_defense.rate_limit import (
    Allowance,
    AttackerStore,
    SlidingWindowRateLimiter,
    ThrottleGate,
)
from enterprise.modules.ai_defense.ai_defense import AIDefenseFacade, AIDefenseModule


class Clock:
    """Injectable clock for deterministic time travel."""

    def __init__(self, start: float = 1000.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


# ---------------------------------------------------------------------------
# SlidingWindowRateLimiter
# ---------------------------------------------------------------------------
def test_limiter_allows_under_limit():
    c = Clock()
    r = SlidingWindowRateLimiter(limit=5, window=60.0, clock=c)
    for i in range(5):
        allowed, remaining, reset_in = r.allow("ip:1")
        assert allowed is True
        assert remaining == 4 - i  # 5,4,3,2,1 capacity left
    # 6th request over the limit
    allowed, remaining, reset_in = r.allow("ip:1")
    assert allowed is False
    assert remaining == 0
    assert reset_in > 0


def test_limiter_blocks_over_limit():
    c = Clock()
    r = SlidingWindowRateLimiter(limit=3, window=60.0, clock=c)
    for _ in range(3):
        assert r.allow("k")[0] is True
    assert r.allow("k")[0] is False
    assert r.allow("k")[0] is False


def test_limiter_window_slides_old_calls_expire():
    c = Clock()
    r = SlidingWindowRateLimiter(limit=3, window=10.0, clock=c)
    for _ in range(3):
        r.allow("k")
    assert r.allow("k")[0] is False  # blocked at t=1000
    c.advance(11.0)  # window fully slides; oldest hits now expired
    assert r.allow("k")[0] is True  # a slot freed
    # exactly one slot freed -> two more then blocked again
    assert r.allow("k")[0] is True
    assert r.allow("k")[0] is True
    assert r.allow("k")[0] is False


def test_limiter_reset_clears_key():
    c = Clock()
    r = SlidingWindowRateLimiter(limit=2, window=60.0, clock=c)
    r.allow("a")
    r.allow("a")
    assert r.allow("a")[0] is False
    r.reset("a")
    assert r.allow("a")[0] is True


def test_limiter_is_per_key_independent():
    c = Clock()
    r = SlidingWindowRateLimiter(limit=1, window=60.0, clock=c)
    assert r.allow("ip:1")[0] is True
    assert r.allow("ip:1")[0] is False
    # a different key is unaffected
    assert r.allow("ip:2")[0] is True


def test_limiter_snapshot_counts_live_hits():
    c = Clock()
    r = SlidingWindowRateLimiter(limit=5, window=10.0, clock=c)
    r.allow("a")
    r.allow("a")
    r.allow("b")
    snap = r.snapshot()
    assert snap["a"] == 2
    assert snap["b"] == 1
    c.advance(11.0)
    assert r.snapshot() == {}


# ---------------------------------------------------------------------------
# AttackerStore persistence
# ---------------------------------------------------------------------------
def test_store_records_attempts_and_survives_reopen(tmp_path):
    db = str(tmp_path / "attackers.db")
    c = Clock()
    s1 = AttackerStore(db)
    s1.add_attempt("ip:9", now=c())
    s1.add_attempt("ip:9", now=c())
    s1.add_attempt("ip:9", now=c(), flag="rate_limited")
    rec = s1.get("ip:9")
    assert rec is not None
    assert rec["attempt_count"] == 3
    assert rec["flags"] == ["rate_limited"]
    s1.close()

    # Reopen a fresh store against the SAME file -> state persisted.
    s2 = AttackerStore(db)
    rec2 = s2.get("ip:9")
    assert rec2 is not None
    assert rec2["attempt_count"] == 3
    assert rec2["flags"] == ["rate_limited"]
    s2.close()


def test_store_bump_updates_last_seen_and_count():
    c = Clock()
    s = AttackerStore()
    s.add_attempt("k", now=c())  # first_seen == last_seen == 1000
    c.advance(5.0)
    s.bump("k", now=c())
    rec = s.get("k")
    assert rec["attempt_count"] == 2
    assert rec["last_seen"] == 1005.0
    assert rec["first_seen"] == 1000.0


def test_store_block_lifecycle():
    c = Clock()
    s = AttackerStore()
    s.block("ip:1", until=c() + 100.0, flag="auto_block")
    assert s.blocked("ip:1", now=c()) is True
    assert s.is_blocked("ip:1", now=c()) is True
    assert s.block_remaining("ip:1", now=c()) > 0
    c.advance(200.0)
    assert s.blocked("ip:1", now=c()) is False
    s.unblock("ip:2")  # no-op safe on missing key


def test_store_list_ordering_and_flags(tmp_path):
    db = str(tmp_path / "a.db")
    c = Clock()
    s = AttackerStore(db)
    s.add_attempt("ip:1", now=1000.0, flag="probe")
    c.advance(2.0)
    s.add_attempt("ip:2", now=c())
    c.advance(2.0)
    s.add_attempt("ip:3", now=c())
    s.block("ip:3", until=c() + 50.0)
    rows = s.list(now=c())
    assert [r["key"] for r in rows] == ["ip:3", "ip:2", "ip:1"]
    assert rows[0]["currently_blocked"] is True
    assert rows[2]["flags"] == ["probe"]
    s.close()


def test_store_in_memory_is_isolated():
    s1 = AttackerStore()
    s1.add_attempt("ip:1")
    s2 = AttackerStore()
    assert s2.get("ip:1") is None  # separate in-memory DBs are isolated


# ---------------------------------------------------------------------------
# ThrottleGate (limiter + store combined)
# ---------------------------------------------------------------------------
def test_gate_cooperates_under_limit():
    c = Clock()
    g = ThrottleGate(limit=5, window=60.0, threshold=100, clock=c)
    for _ in range(5):
        a = g.allow("ip:1", now=c())
        assert a.allowed is True
        assert a.reason == "allowed"


def test_gate_denies_over_limit_and_records_attempt():
    c = Clock()
    g = ThrottleGate(limit=2, window=60.0, threshold=100, clock=c)
    g.allow("ip:1", now=c())
    g.allow("ip:1", now=c())
    a = g.allow("ip:1", now=c())
    assert a.allowed is False
    assert a.reason == "rate_limited"
    rec = g.store.get("ip:1")
    assert rec["attempt_count"] == 3
    assert "rate_limited" in rec["flags"]


def test_gate_auto_blocks_after_threshold_then_expires():
    c = Clock()
    g = ThrottleGate(limit=100, window=60.0, threshold=3, block_seconds=50.0, clock=c)
    for _ in range(3):
        a = g.allow("ip:x", now=c())
        assert a.allowed is True  # still allowed up to the threshold
    assert g.blocked("ip:x", now=c()) is True  # but now auto-blocked
    # blocked -> all subsequent attempts denied with reason "blocked"
    a = g.allow("ip:x", now=c())
    assert a.allowed is False
    assert a.blocked is True
    assert a.reason == "blocked"
    assert a.reset_in > 0
    # block expires
    c.advance(100.0)
    a = g.allow("ip:x", now=c())
    assert a.allowed is True
    assert a.blocked is False


def test_gate_blocked_state_takes_priority_over_limiter():
    c = Clock()
    g = ThrottleGate(limit=100, window=60.0, threshold=1, block_seconds=30.0, clock=c)
    g.allow("ip:y", now=c())  # hits threshold=1, auto-blocks
    assert g.blocked("ip:y", now=c()) is True
    # limiter would normally allow (under limit) but the block wins
    a = g.allow("ip:y", now=c())
    assert a.allowed is False
    assert a.reason == "blocked"


def test_gate_clock_injection_is_deterministic():
    c = Clock(start=42.0)
    g = ThrottleGate(limit=1, window=5.0, threshold=100, clock=c)
    a1 = g.allow("k", now=c())
    a2 = g.allow("k", now=c())
    assert a1.allowed is True
    assert a2.allowed is False
    assert a2.reset_in <= 5.0
    c.advance(6.0)
    assert g.allow("k", now=c()).allowed is True


def test_gate_manual_record_marks_attempt():
    c = Clock()
    g = ThrottleGate(threshold=2, clock=c)
    g.record("ip:z", flag="auth_failure", now=c())
    g.record("ip:z", flag="auth_failure", now=c())
    g.allow("ip:z", now=c())
    assert g.blocked("ip:z", now=c()) is True


# ---------------------------------------------------------------------------
# Facade wiring (OFF by default; opt-in via with_throttle)
# ---------------------------------------------------------------------------
def test_facade_default_is_offline_noop_allow():
    f = AIDefenseFacade()
    assert f.throttle is None
    a = f.throttle_request("ip:1")
    assert a.allowed is True
    assert a.reason == "offline"
    assert f.attacker_state("ip:1") is None
    # classic detectors unaffected
    assert f.scan_content("normal text").malicious is False


def test_facade_with_throttle_enforces_and_wires():
    c = Clock()
    f = AIDefenseFacade.with_throttle(clock=c, limit=2, window=60.0, threshold=100)
    assert f.throttle is not None
    f.throttle_request("ip:1", now=c())
    f.throttle_request("ip:1", now=c())
    a = f.throttle_request("ip:1", now=c())
    assert a.allowed is False
    assert a.reason == "rate_limited"
    assert f.attacker_state("ip:1")["attempt_count"] == 3
    # posture exposes the throttle block when active
    assert "throttle" in f.posture()


def test_module_offline_by_default_and_opt_in_via_config():
    m = AIDefenseModule()
    assert m.facade.throttle is None
    assert m.throttle_request("ip:1").allowed is True

    m2 = AIDefenseModule(config={"throttle": {"enabled": True, "limit": 3, "threshold": 100}})
    assert m2.facade.throttle is not None
    for _ in range(3):
        assert m2.throttle_request("ip:1").allowed is True
    assert m2.throttle_request("ip:1").allowed is False


def test_gate_lifecycle_close_is_idempotent():
    s = AttackerStore()
    g = ThrottleGate(store=s)
    g.allow("k")
    g.close()
    s.close()  # closing twice safe (idempotent)
