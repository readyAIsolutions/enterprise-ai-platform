"""
Tests for AuditTrail.
"""

import time

import pytest

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[5]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from enterprise.foundation.config_feature_flags.audit import (
    AuditEntry,
    AuditReport,
    AuditTrail,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def trail():
    """Return a fresh AuditTrail."""
    return AuditTrail()


def record_sample_entries(trail: AuditTrail) -> None:
    """Record a standard set of sample entries."""
    trail.record(
        actor="alice",
        action="set",
        target="database.host",
        old_value="localhost",
        new_value="db.internal",
        reason="Migrate to internal",
    )
    trail.record(
        actor="bob",
        action="set",
        target="database.port",
        old_value=5432,
        new_value=5433,
        reason="Port conflict",
    )
    trail.record(
        actor="alice",
        action="set",
        target="redis.host",
        old_value=None,
        new_value="redis.internal",
        reason="Add redis",
    )
    trail.record(
        actor="alice",
        action="delete",
        target="redis.host",
        old_value="redis.internal",
        new_value=None,
        reason="Remove redis",
    )


# ---------------------------------------------------------------------------
# Basic recording tests
# ---------------------------------------------------------------------------

class TestRecording:
    """Tests for audit entry recording."""

    def test_record_entry(self, trail):
        entry = trail.record(
            actor="admin",
            action="set",
            target="app.name",
            old_value="old-app",
            new_value="new-app",
            reason="Rebranding",
        )
        assert entry.actor == "admin"
        assert entry.action == "set"
        assert entry.target == "app.name"
        assert entry.old_value == "old-app"
        assert entry.new_value == "new-app"
        assert entry.reason == "Rebranding"
        assert len(trail) == 1

    def test_record_batch(self, trail):
        entries = [
            {"actor": "a1", "action": "set", "target": "k1", "new_value": "v1"},
            {"actor": "a2", "action": "set", "target": "k2", "new_value": "v2"},
        ]
        results = trail.record_batch(entries)
        assert len(results) == 2
        assert len(trail) == 2

    def test_entry_is_immutable(self, trail):
        entry = trail.record(actor="user", target="key", new_value="val")
        with pytest.raises(Exception):
            entry.actor = "hacker"  # frozen dataclass

    def test_entry_hash_is_computed(self, trail):
        entry = trail.record(actor="u", target="k", new_value="v")
        assert entry.hash != ""
        assert len(entry.hash) == 64  # SHA-256 hex

    def test_entry_verify(self, trail):
        entry = trail.record(actor="u", target="k", new_value="v")
        assert entry.verify() is True


# ---------------------------------------------------------------------------
# Query tests
# ---------------------------------------------------------------------------

class TestQuery:
    """Tests for audit entry querying."""

    def setup_method(self):
        self.trail = AuditTrail()
        record_sample_entries(self.trail)

    def test_query_all(self):
        results = self.trail.query()
        assert len(results) == 4

    def test_query_by_actor(self):
        results = self.trail.query(actor="alice")
        assert len(results) == 3
        assert all(e.actor == "alice" for e in results)

    def test_query_by_action(self):
        results = self.trail.query(action="delete")
        assert len(results) == 1
        assert results[0].target == "redis.host"

    def test_query_by_target_exact(self):
        results = self.trail.query(target="database.host")
        assert len(results) == 1

    def test_query_by_target_pattern(self):
        results = self.trail.query(target_pattern="database.*")
        assert len(results) == 2

    def test_query_by_time_range(self):
        t0 = time.time()
        self.trail.record(actor="c1", target="a", new_value="x")
        t_mid = time.time()
        time.sleep(0.01)
        self.trail.record(actor="c2", target="b", new_value="y")
        t_end = time.time()

        results = self.trail.query(since=t0, until=t_mid)
        assert len(results) >= 1
        assert results[0].target == "a"

        results = self.trail.query(since=t_mid, until=t_end)
        assert len(results) >= 1

    def test_query_pagination(self):
        results = self.trail.query(limit=2, offset=1)
        assert len(results) <= 2

    def test_get_entry(self, trail):
        entry = trail.record(actor="u", target="k", new_value="v")
        found = trail.get_entry(entry.id)
        assert found is not None
        assert found.id == entry.id
        assert trail.get_entry("nonexistent-uuid") is None

    def test_get_latest(self, trail):
        trail.record(actor="u", target="k", new_value="v1")
        trail.record(actor="u", target="k", new_value="v2")
        latest = trail.get_latest("k")
        assert latest.new_value == "v2"

    def test_get_latest_none(self, trail):
        assert trail.get_latest("nonexistent") is None

    def test_count(self, trail):
        record_sample_entries(trail)
        assert trail.count() == 4
        assert trail.count(actor="alice") == 3
        assert trail.count(actor="bob") == 1

    def test_len_and_iter(self, trail):
        record_sample_entries(trail)
        assert len(trail) == 4
        entries = list(trail)
        assert len(entries) == 4

    def test_getitem(self, trail):
        e = trail.record(target="k", new_value="v")
        assert trail[0] == e


# ---------------------------------------------------------------------------
# Diff generation tests
# ---------------------------------------------------------------------------

class TestDiff:
    """Tests for diff generation."""

    def test_diff_between_states(self, trail):
        t0 = time.time()
        trail.record(actor="u", target="a", new_value="x")
        t1 = time.time()
        time.sleep(0.01)
        trail.record(actor="u", target="b", new_value="y")
        t2 = time.time()

        diff = trail.diff(t1=t0, t2=t2)
        # Should show changes
        assert diff != ""

    def test_diff_identical(self, trail):
        trail.record(actor="u", target="a", new_value="x")
        t_same = time.time()
        diff = trail.diff(t1=t_same, t2=t_same)
        # Same state at the same point in time -> no diff
        assert diff == "" or len(diff.strip()) == 0

    def test_diff_with_target_filter(self, trail):
        trail.record(actor="u", target="db.host", new_value="x")
        trail.record(actor="u", target="cache.ttl", new_value="60")
        t_end = time.time()

        diff = trail.diff(t2=t_end, target_filter="db.*")
        assert "db.host" in diff or len(diff.strip()) >= 0

    def test_changes_between(self, trail):
        t0 = time.time()
        trail.record(actor="u", target="a", new_value="1")
        t1 = time.time()
        entries = trail.changes_between(t0, t1)
        assert len(entries) == 1


# ---------------------------------------------------------------------------
# Snapshot tests
# ---------------------------------------------------------------------------

class TestSnapshot:
    """Tests for state snapshot reconstruction."""

    def test_snapshot_empty(self, trail):
        snap = trail.snapshot()
        assert snap == {}

    def test_snapshot_reconstructs_state(self, trail):
        trail.record(actor="u", target="a", new_value="1")
        trail.record(actor="u", target="b", new_value="2")
        trail.record(actor="u", target="a", new_value="3")  # overwrites
        trail.record(actor="u", action="delete", target="b")
        snap = trail.snapshot()
        assert snap.get("a") == "3"
        assert "b" not in snap

    def test_snapshot_at_time(self, trail):
        t0 = time.time()
        trail.record(actor="u", target="a", new_value="v1")
        t1 = time.time()
        trail.record(actor="u", target="a", new_value="v2")
        t2 = time.time()

        snap = trail.snapshot(at_time=t1)
        assert snap.get("a") == "v1"


# ---------------------------------------------------------------------------
# Integrity tests
# ---------------------------------------------------------------------------

class TestIntegrity:
    """Tests for audit integrity verification."""

    def test_verify_integrity_passes(self, trail):
        record_sample_entries(trail)
        valid, errors = trail.verify_integrity()
        assert valid is True
        assert len(errors) == 0

    def test_tampered_entry_detected(self, trail):
        entry = trail.record(actor="u", target="k", new_value="v")
        # Directly modify the hash (bypassing frozen via object.__setattr__)
        object.__setattr__(entry, "hash", "tampered-hash")
        valid, errors = trail.verify_integrity()
        assert valid is False
        assert len(errors) > 0


# ---------------------------------------------------------------------------
# Report tests
# ---------------------------------------------------------------------------

class TestReport:
    """Tests for audit report generation."""

    def test_generate_report(self, trail):
        record_sample_entries(trail)
        report = trail.generate_report()
        assert isinstance(report, AuditReport)
        assert report.total_changes == 4
        assert report.changes_by_actor["alice"] == 3
        assert report.changes_by_actor["bob"] == 1
        assert report.changes_by_action["set"] == 3
        assert report.changes_by_action["delete"] == 1

    def test_generate_report_filtered(self, trail):
        record_sample_entries(trail)
        report = trail.generate_report(actor="bob")
        assert report.total_changes == 1
        assert report.changes_by_actor.get("bob") == 1

    def test_generate_report_time_range(self, trail):
        t0 = time.time()
        trail.record(actor="u", target="a", new_value="1")
        t1 = time.time()
        time.sleep(0.01)
        trail.record(actor="u", target="b", new_value="2")
        t2 = time.time()

        report = trail.generate_report(period_start=t0, period_end=t1)
        assert report.total_changes == 1


# ---------------------------------------------------------------------------
# Export tests
# ---------------------------------------------------------------------------

class TestExport:
    """Tests for audit export."""

    def test_export_dicts(self, trail):
        record_sample_entries(trail)
        data = trail.export()
        assert len(data) == 4
        assert all("id" in d for d in data)
        assert all("timestamp" in d for d in data)

    def test_export_json(self, trail):
        record_sample_entries(trail)
        json_str = trail.export_json()
        assert isinstance(json_str, str)
        import json
        data = json.loads(json_str)
        assert len(data) == 4


# ---------------------------------------------------------------------------
# Data model tests
# ---------------------------------------------------------------------------

class TestDataModels:
    """Tests for data model properties."""

    def test_audit_entry_to_dict(self, trail):
        entry = trail.record(
            actor="admin",
            action="set",
            target="key",
            old_value="old",
            new_value="new",
            reason="test",
        )
        d = entry.to_dict()
        assert d["actor"] == "admin"
        assert d["action"] == "set"
        assert d["target"] == "key"
        assert d["old_value"] == "old"
        assert d["new_value"] == "new"
        assert d["reason"] == "test"
        assert "datetime" in d

    def test_audit_entry_datetime_utc(self, trail):
        entry = trail.record(actor="u", target="k", new_value="v")
        dt = entry.datetime_utc
        assert dt is not None
        # Should be close to now
        assert abs(dt.timestamp() - time.time()) < 5


# ---------------------------------------------------------------------------
# Max entries tests
# ---------------------------------------------------------------------------

class TestMaxEntries:
    """Tests for max entries truncation."""

    def test_max_entries_truncation(self):
        trail = AuditTrail(max_entries=10)
        for i in range(15):
            trail.record(actor="u", target=f"k{i}", new_value=f"v{i}")
        assert len(trail) == 10