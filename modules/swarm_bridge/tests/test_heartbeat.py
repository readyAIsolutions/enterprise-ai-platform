#!/usr/bin/env python3
"""
Test Suite — ENI Swarm Bridge: Member Heartbeat + Liveness Registry
====================================================================
Master-class coverage for the heartbeat/liveness/health layer.

Covers:
  - register / list / unregister lifecycle
  - role + status filters
  - heartbeat reception updates liveness
  - stale heartbeat -> absent/lost after timeout (real clock transitions)
  - health aggregation: healthy / degraded / down
  - critical-role loss detection
  - OPTIONAL SQLite persistence (round-trip + reload)
  - injectable FixedClock for deterministic time control
  - protocol edge cases (unknown member, floor_misses escalation)
  - facade SwarmHealth bundle
"""
from __future__ import annotations

import os
import sqlite3
import tempfile

import pytest

from modules.swarm_bridge.heartbeat import (
    SwarmMember,
    MemberRegistry,
    HeartbeatProtocol,
    HealthAggregator,
    HealthReport,
    SwarmHealth,
    SwarmClock,
    FixedClock,
    STATUS_ALIVE,
    STATUS_ABSENT,
    STATUS_LOST,
    DEFAULT_HEARTBEAT_TIMEOUT,
)

# Re-exports must also be visible from the package root
from modules.swarm_bridge import (
    SwarmMember as PkgSwarmMember,
    MemberRegistry as PkgMemberRegistry,
    HeartbeatProtocol as PkgHeartbeatProtocol,
    HealthAggregator as PkgHealthAggregator,
    STATUS_ALIVE as PKG_ALIVE,
)


def make_member(member_id: str, role: str = "worker", **kw) -> SwarmMember:
    return SwarmMember(member_id=member_id, role=role, addr=f"tcp://127.0.0.1:{member_id}", **kw)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def clock():
    return FixedClock(start=1000.0)


@pytest.fixture
def registry(clock):
    return MemberRegistry(clock=clock)


@pytest.fixture
def protocol(registry):
    return HeartbeatProtocol(registry)


@pytest.fixture
def populated(registry):
    """registry pre-loaded with 3 workers + 1 coordinator."""
    for i in range(3):
        registry.register(make_member(f"w{i}", role="worker", capabilities=["build", "test"]))
    registry.register(make_member("coord", role="coordinator", capabilities=["coordinate"]))
    return registry


# ---------------------------------------------------------------------------
# Registry: register / list / unregister / get
# ---------------------------------------------------------------------------
def test_register_adds_member_and_stamps_liveness(registry, clock):
    m = registry.register(make_member("w0", role="worker"))
    assert registry.contains("w0")
    assert registry.get("w0") is m
    # register() gives an initial heartbeat + registered_at at clock time
    assert m.last_heartbeat == 1000.0
    assert m.registered_at == 1000.0
    assert m.status == STATUS_ALIVE


def test_register_is_upsert(registry):
    registry.register(make_member("w0"))
    registry.register(make_member("w0", role="builder"))
    m = registry.get("w0")
    assert m.role == "builder"
    assert len(registry) == 1


def test_list_default_all_and_ordered(registry):
    registry.register(make_member("b", role="builder"))
    registry.register(make_member("a", role="worker"))
    ids = [m.member_id for m in registry.list()]
    assert ids == ["a", "b"]


def test_list_filter_by_role(registry, populated):
    workers = registry.list(role="worker")
    assert len(workers) == 3
    assert all(m.role == "worker" for m in workers)


def test_list_filter_by_status_and_role(populated, protocol, clock):
    clock.advance(100)  # everyone stale
    protocol.check_liveness(timeout=DEFAULT_HEARTBEAT_TIMEOUT)
    stagnant = populated.list(status=STATUS_ABSENT)
    assert len(stagnant) == 4
    assert populated.list(role="coordinator")[0].status == STATUS_ABSENT
    assert populated.list(status=STATUS_ALIVE) == []


def test_unregister_removes_member(registry):
    registry.register(make_member("w0"))
    removed = registry.unregister("w0")
    assert removed is not None
    assert not registry.contains("w0")
    assert len(registry) == 0
    assert registry.unregister("w0") is None  # not an error


def test_get_unknown_returns_none(registry):
    assert registry.get("nope") is None


# ---------------------------------------------------------------------------
# Heartbeat reception
# ---------------------------------------------------------------------------
def test_send_heartbeat_updates_liveness(registry, protocol, clock):
    registry.register(make_member("w0"))
    clock.advance(5)
    protocol.send_heartbeat("w0")
    m = registry.get("w0")
    assert m.last_heartbeat == 1005.0
    assert m.status == STATUS_ALIVE


def test_send_heartbeat_revives_absent_member(populated, protocol, clock):
    clock.advance(100)
    protocol.check_liveness(timeout=DEFAULT_HEARTBEAT_TIMEOUT)
    assert populated.get("w0").status == STATUS_ABSENT
    protocol.send_heartbeat("w0")
    assert populated.get("w0").status == STATUS_ALIVE
    assert populated.get("w0").last_heartbeat == 1100.0


def test_send_heartbeat_unknown_raises(registry, protocol):
    with pytest.raises(KeyError):
        protocol.send_heartbeat("ghost")


# ---------------------------------------------------------------------------
# Stale -> absent/lost after timeout
# ---------------------------------------------------------------------------
def test_fresh_member_survives_liveness_check(populated, protocol, clock):
    affected = protocol.check_liveness(timeout=30.0)
    assert affected == []
    assert all(m.status == STATUS_ALIVE for m in populated.list())


def test_stale_member_becomes_absent_after_timeout(populated, protocol, clock):
    clock.advance(31)  # past 30s default timeout
    affected = protocol.check_liveness(timeout=DEFAULT_HEARTBEAT_TIMEOUT)
    assert len(affected) == 4
    assert all(m.status == STATUS_ABSENT for m in affected)
    # a second miss escalates absent -> lost and is reported again
    escalated = protocol.check_liveness(timeout=DEFAULT_HEARTBEAT_TIMEOUT)
    assert len(escalated) == 4
    assert all(m.status == STATUS_LOST for m in escalated)


def test_floor_misses_escalates_absent_to_lost(registry, clock):
    registry.register(make_member("w0"))
    prot = HeartbeatProtocol(registry, floor_misses=2)
    clock.advance(100)
    first = prot.check_liveness(timeout=30.0)
    assert [m.status for m in first] == [STATUS_ABSENT]
    second = prot.check_liveness(timeout=30.0)
    assert [m.status for m in second] == [STATUS_LOST]


def test_heartbeat_resets_miss_streak(registry, protocol, clock):
    registry.register(make_member("w0"))
    clock.advance(100)
    protocol.check_liveness(timeout=30.0)  # -> absent
    protocol.send_heartbeat("w0")          # revives
    clock.advance(100)
    # fresh beat resets streak; it is only absent again, not escalated
    affected = protocol.check_liveness(timeout=30.0)
    assert [m.status for m in affected] == [STATUS_ABSENT]


# ---------------------------------------------------------------------------
# Health aggregation
# ---------------------------------------------------------------------------
def test_health_healthy(registry, protocol, clock):
    aggregator = HealthAggregator(registry, required=3)
    for i in range(3):
        registry.register(make_member(f"w{i}"))
    h = aggregator.health()
    assert isinstance(h, HealthReport)
    assert h.status == "healthy"
    assert h.healthy is True
    assert h.alive_count == 3
    assert h.absent_count == 0


def test_health_degrades_below_required(populated, protocol, clock):
    aggregator = HealthAggregator(populated, required=4)
    clock.advance(100)
    h = aggregator.health()  # 4 members alive but all now stale -> dead
    # after liveness applied, none alive -> down for a 4-required swarm
    assert h.status == "down"
    assert h.healthy is False
    assert h.alive_count == 0
    assert h.absent_count == 4


def test_health_degrades_not_down_with_partial_alive(populated, protocol, clock):
    aggregator = HealthAggregator(populated, required=4)
    clock.advance(100)
    aggregator.health()  # consume first pass -> all absent
    protocol.send_heartbeat("w0")  # only w0 revives
    clock.advance(1)  # keep w0 fresh
    h = aggregator.health()
    # 1 alive < required 4 -> degraded, not down (alive>0)
    assert h.status == "degraded"
    assert h.healthy is False
    assert h.alive_count == 1
    assert h.missing_required == 3


def test_health_never_applies_liveness_when_disabled(populated, protocol, clock):
    aggregator = HealthAggregator(populated, required=3)
    clock.advance(1000)
    h = aggregator.health(apply_liveness=False)
    assert h.status == "healthy"  # raw registered state, liveness not enforced


def test_health_critical_role_loss(populated, protocol, clock):
    aggregator = HealthAggregator(populated, required=1, critical_roles={"coordinator"})
    clock.advance(100)
    h = aggregator.health()
    # coordinator is lost -> critical role lost even though 0 alive & down
    assert "coordinator" in h.critical_roles_lost
    assert h.healthy is False


def test_health_critical_role_present_stays_healthy(populated, protocol, clock):
    aggregator = HealthAggregator(populated, required=1, critical_roles={"coordinator"})
    # all fresh
    h = aggregator.health()
    assert h.critical_roles_lost == []
    assert h.status == "healthy"


def test_health_empty_swarm_down(registry, clock):
    aggregator = HealthAggregator(registry, required=1)
    h = aggregator.health()
    assert h.status == "down"
    assert h.healthy is False
    assert h.total == 0


# ---------------------------------------------------------------------------
# Injectable clock determinism (already exercised throughout; explicit check)
# ---------------------------------------------------------------------------
def test_injectable_clock_fully_deterministic():
    clock = FixedClock(start=50.0)
    reg = MemberRegistry(clock=clock)
    proto = HeartbeatProtocol(reg)
    reg.register(make_member("w0"))
    assert reg.get("w0").last_heartbeat == 50.0
    clock.advance(25)
    proto.send_heartbeat("w0")
    assert reg.get("w0").last_heartbeat == 75.0


# ---------------------------------------------------------------------------
# Optional SQLite persistence
# ---------------------------------------------------------------------------
def test_sqlite_persistence_round_trip():
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "swarm.db")
        reg = MemberRegistry(db_path=db)
        reg.register(make_member("w0", role="builder", capabilities=["x", "y"]))
        reg.register(make_member("w1", role="worker"))
        reg.unregister("w1")
        # reload from same db file
        reg2 = MemberRegistry(db_path=db)
        assert reg2.load_persisted() == 1
        m = reg2.get("w0")
        assert m is not None
        assert m.role == "builder"
        assert m.capabilities == ["x", "y"]


def test_persistence_skipped_when_no_db_path(registry):
    """No db_path -> persistence is a no-op (optional)."""
    registry.register(make_member("w0"))
    registry.unregister("w0")
    assert len(registry) == 0


# ---------------------------------------------------------------------------
# Lifecycle + facade
# ---------------------------------------------------------------------------
def test_full_lifecycle():
    clock = FixedClock(start=0.0)
    sh = SwarmHealth(required=2, critical_roles={"coordinator"}, clock=clock)
    for i in range(2):
        sh.registry.register(make_member(f"w{i}", role="worker"))
    sh.registry.register(make_member("c", role="coordinator"))
    assert sh.health().status == "healthy"

    clock.advance(1000)
    h = sh.health()
    assert h.status == "down"
    assert h.critical_roles_lost == ["coordinator"]

    sh.protocol.send_heartbeat("w0")
    clock.advance(1)  # keep w0 fresh
    h = sh.health()
    assert h.alive_count == 1  # not enough for required=2


def test_package_root_exports():
    assert PkgSwarmMember is SwarmMember
    assert PkgMemberRegistry is MemberRegistry
    assert PkgHeartbeatProtocol is HeartbeatProtocol
    assert PkgHealthAggregator is HealthAggregator
    assert PKG_ALIVE == STATUS_ALIVE
    assert DEFAULT_HEARTBEAT_TIMEOUT == 30.0


def test_swarm_member_serialization_roundtrip():
    m = make_member("w0", role="worker", capabilities=["a", "b"])
    m.mark_alive(42.0)
    d = m.to_dict()
    m2 = SwarmMember.from_dict(d)
    assert m2.member_id == m.member_id
    assert m2.role == m.role
    assert m2.capabilities == ["a", "b"]
    assert m2.last_heartbeat == 42.0
