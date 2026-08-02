"""
Tests for the ENI Knowledge Base enterprise module.

Covers:
  - Module registration via @module decorator
  - KnowledgeBaseBridge: CRUD patterns, search, skills, operations
  - Vector search (mock / graceful degradation)
  - Metrics collection
  - Health checks
  - Event publishing
  - Thread safety (concurrent access)
  - Error handling / edge cases

All tests use the real hermes_kb_universal library against temporary
SQLite databases to avoid side effects.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path for enterprise imports.
# ---------------------------------------------------------------------------
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_temp_kb_dir() -> Path:
    """Create a temporary ~/.eni/kb-style directory for test isolation."""
    base = Path(tempfile.mkdtemp(prefix="kb_bridge_test_"))
    kb_dir = base / ".eni" / "kb"
    kb_dir.mkdir(parents=True, exist_ok=True)
    return base


# ======================================================================
# Tests
# ======================================================================


class TestModuleRegistration:
    """Verify the ENIKBModule is properly decorated and discoverable."""

    def test_module_decorator_registers(self):
        """The @module decorator should register the class in _MODULE_REGISTRY."""
        from enterprise.platform_kernel import _MODULE_REGISTRY
        from enterprise.modules.kb_bridge import ENIKBModule

        # Importing the module triggers decorator registration
        assert "kb_bridge" in _MODULE_REGISTRY
        assert _MODULE_REGISTRY["kb_bridge"] is ENIKBModule

    def test_module_instance_has_correct_metadata(self):
        """An ENIKBModule instance should reflect the decorator metadata."""
        from enterprise.modules.kb_bridge import ENIKBModule

        mod = ENIKBModule()
        assert mod.name == "kb_bridge"
        assert mod.version == "1.0.0"

    def test_module_exports_as_documented(self):
        """__all__ contains the expected public API surface."""
        import enterprise.modules.kb_bridge as kb_bridge

        expected = {"ENIKBModule", "KnowledgeBaseBridge", "KBHealthCheck"}
        exported = set(kb_bridge.__all__)
        assert exported >= expected

    def test_module_has_version(self):
        """__version__ is a valid semver string."""
        import enterprise.modules.kb_bridge as kb_bridge

        v = kb_bridge.__version__
        parts = v.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)


class TestKnowledgeBaseBridgeCore:
    """Integration tests against the real hermes_kb_universal library."""

    @classmethod
    def setup_class(cls):
        """Point hermes_kb_universal at a temp DB directory."""
        cls._orig_home = os.environ.get("HOME", "")
        cls._temp_base = _make_temp_kb_dir()
        os.environ["HOME"] = str(cls._temp_base)

        from enterprise.modules.kb_bridge.kb_bridge import KnowledgeBaseBridge
        cls.bridge = KnowledgeBaseBridge(profile="test", publish_events=False)

    @classmethod
    def teardown_class(cls):
        cls.bridge.close()
        os.environ["HOME"] = cls._orig_home

    # ── Patterns ────────────────────────────────────────────────────────────

    def test_create_pattern_returns_record(self):
        rec = self.bridge.create_pattern(
            pattern_type="test",
            title="hello world",
            content="some content",
            tags=["test", "hello"],
        )
        assert rec is not None
        assert rec.pattern_type == "test"
        assert rec.title == "hello world"
        assert rec.content == "some content"
        assert rec.tags == ["test", "hello"]
        assert rec.id > 0

    def test_create_pattern_idempotent(self):
        """Creating the same pattern twice returns the existing ID."""
        rec1 = self.bridge.create_pattern(
            pattern_type="memo", title="T", content="C"
        )
        rec2 = self.bridge.create_pattern(
            pattern_type="memo", title="T", content="C"
        )
        assert rec1.id == rec2.id

    def test_read_pattern_found(self):
        rec = self.bridge.create_pattern(
            pattern_type="test", title="readme", content="readme content"
        )
        fetched = self.bridge.read_pattern(rec.id)
        assert fetched is not None
        assert fetched.id == rec.id
        assert fetched.title == "readme"

    def test_read_pattern_not_found(self):
        assert self.bridge.read_pattern(999_999) is None

    def test_update_pattern_title(self):
        rec = self.bridge.create_pattern(
            pattern_type="test", title="orig", content="c"
        )
        updated = self.bridge.update_pattern(rec.id, title="new title")
        assert updated is not None
        assert updated.title == "new title"
        assert updated.content == "c"

    def test_update_pattern_content(self):
        rec = self.bridge.create_pattern(
            pattern_type="test", title="t", content="old"
        )
        updated = self.bridge.update_pattern(rec.id, content="brand new")
        assert updated is not None
        assert updated.content == "brand new"

    def test_update_pattern_tags(self):
        rec = self.bridge.create_pattern(
            pattern_type="t", title="t", content="c", tags=["a"]
        )
        updated = self.bridge.update_pattern(rec.id, tags=["x", "y"])
        assert updated is not None
        assert set(updated.tags) == {"x", "y"}

    def test_update_non_existent_pattern(self):
        assert self.bridge.update_pattern(999_999, title="nope") is None

    def test_delete_pattern_found(self):
        rec = self.bridge.create_pattern(
            pattern_type="test", title="delme", content="bye"
        )
        assert self.bridge.delete_pattern(rec.id) is True
        assert self.bridge.read_pattern(rec.id) is None

    def test_delete_pattern_not_found(self):
        assert self.bridge.delete_pattern(999_999) is False

    # ── Search ──────────────────────────────────────────────────────────────

    def test_search_by_query(self):
        self.bridge.create_pattern(
            pattern_type="test", title="unique_query_test", content="abc"
        )
        results = self.bridge.search_patterns(query="unique_query_test")
        assert results.total_count >= 1
        assert any("unique_query_test" in p.title for p in results.items)

    def test_search_by_type(self):
        self.bridge.create_pattern(pattern_type="search_test", title="T1", content="C1")
        results = self.bridge.search_patterns(pattern_type="search_test")
        assert results.total_count >= 1

    def test_search_by_tags(self):
        self.bridge.create_pattern(
            pattern_type="t", title="tagged", content="x", tags=["special"]
        )
        results = self.bridge.search_patterns(tags=["special"])
        assert results.total_count >= 1

    def test_search_empty(self):
        results = self.bridge.search_patterns(query="zz_no_match_999")
        assert results.total_count == 0
        assert results.items == []

    def test_search_limit_offset(self):
        for i in range(5):
            self.bridge.create_pattern(
                pattern_type="limit_test", title=f"Item {i}", content=str(i)
            )
        results = self.bridge.search_patterns(
            pattern_type="limit_test", limit=2, offset=0
        )
        assert len(results.items) <= 2

    # ── Skills ──────────────────────────────────────────────────────────────

    def test_list_skills_empty(self):
        skills = self.bridge.list_skills()
        # No skills synced yet; may be empty or contain system defaults
        assert isinstance(skills, list)

    def test_get_skill_count(self):
        assert isinstance(self.bridge.get_skill_count(), int)

    def test_get_skill_not_found(self):
        assert self.bridge.get_skill(999_999) is None

    # ── Operations ──────────────────────────────────────────────────────────

    def test_store_operation(self):
        op_id = self.bridge.store_operation(
            op_type="test_op",
            tool_name="bridge_test",
            tags=["unit"],
        )
        assert op_id
        assert isinstance(op_id, str)

    def test_list_operations_filtered(self):
        self.bridge.store_operation(op_type="test_type_A", tool_name="ta")
        ops = self.bridge.list_operations(op_type="test_type_A")
        assert isinstance(ops, list)

    def test_get_operation_count(self):
        assert self.bridge.get_operation_count() >= 0

    # ─ Metrics ──────────────────
    def test_get_metrics(self):
        snap = self.bridge.get_metrics()
        assert snap is not None
        assert isinstance(snap.patterns_total, int)
        assert isinstance(snap.db_sizes_kb, dict)

    def test_get_db_sizes(self):
        sizes = self.bridge.get_db_sizes()
        assert isinstance(sizes, dict)
        for db_name in ("patterns", "skills", "sessions", "operations", "vectors"):
            assert db_name in sizes
            assert isinstance(sizes[db_name], int)

    # ─ Health ──────────────────────────────────
    def test_health_check(self):
        report = self.bridge.health_check()
        from enterprise.platform_kernel import HealthStatus
        assert report.status in (
            HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY
        )
        assert report.databases_total == 5
        assert isinstance(report.message, str)


class TestEventPublishing:
    """Verify events fire correctly when EventBus is wired."""

    def setup_method(self):
        self._orig_home = os.environ.get("HOME", "")
        self._temp_base = _make_temp_kb_dir()
        os.environ["HOME"] = str(self._temp_base)

        from enterprise.modules.kb_bridge.kb_bridge import KnowledgeBaseBridge
        self.mock_bus = MagicMock()
        self.bridge = KnowledgeBaseBridge(
            event_bus=self.mock_bus, profile="test", publish_events=True
        )

    def teardown_method(self):
        self.bridge.close()
        os.environ["HOME"] = self._orig_home

    def test_create_publishes_eventt(self):
        self.bridge.create_pattern(
            pattern_type="event_type", title="Event Title", content="x"
        )
        assert self.mock_bus.publish.called

    def test_update_publishes_event(self):
        rec = self.bridge.create_pattern(
            pattern_type="et", title="T", content="C"
        )
        self.mock_bus.reset_mock()
        self.bridge.update_pattern(rec.id, title="Updated")
        assert self.mock_bus.publish.called

    def test_delete_publishes_event(self):
        rec = self.bridge.create_pattern(
            pattern_type="et", title="T", content="C"
        )
        self.mock_bus.reset_mock()
        self.bridge.delete_pattern(rec.id)
        assert self.mock_bus.publish.called

    def test_search_publishes_event(self):
        self.bridge.search_patterns(query="event_search")
        assert self.mock_bus.publish.called

    def test_events_disabled_when_publish_false(self):
        from enterprise.modules.kb_bridge.kb_bridge import KnowledgeBaseBridge
        b2 = KnowledgeBaseBridge(
            event_bus=self.mock_bus, profile="test", publish_events=False
        )
        try:
            b2.create_pattern(pattern_type="t", title="no_event", content="c")
            assert not self.mock_bus.publish.called
        finally:
            b2.close()


class TestThreadSafety:
    """Verify concurrent access doesn't corrupt state."""

    def setup_method(self):
        self._orig_home = os.environ.get("HOME", "")
        self._temp_base = _make_temp_kb_dir()
        os.environ["HOME"] = str(self._temp_base)

        from enterprise.modules.kb_bridge.kb_bridge import KnowledgeBaseBridge
        self.bridge = KnowledgeBaseBridge(profile="test", publish_events=False)

    def teardown_method(self):
        self.bridge.close()
        os.environ["HOME"] = self._orig_home

    def test_concurrent_pattern_creates(self):
        import threading
        errors: list = []
        results: list = []

        def worker(i: int) -> None:
            try:
                rec = self.bridge.create_pattern(
                    pattern_type=f"concurrent_{i}",
                    title=f"Worker {i}",
                    content=str(i),
                )
                results.append(rec.id)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(32)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 32

    def test_concurrent_search_and_write(self):
        import threading

        def writer(n: int) -> None:
            for _ in range(10):
                self.bridge.create_pattern(
                    pattern_type="rw_test",
                    title=f"Item {n}",
                    content=f"content {n}",
                )

        def reader() -> None:
            for _ in range(10):
                self.bridge.search_patterns(pattern_type="rw_test")

        threads: list = []
        for i in range(4):
            threads.append(threading.Thread(target=writer, args=(i,)))
        for _ in range(2):
            threads.append(threading.Thread(target=reader))

        for t in threads:
            t.start()
        for t in threads:
            t.join()


class TestErrorHandling:
    """Edge cases and error scenarios."""

    def test_bridge_init_no_lib(self):
        """Graceful error when hermes_kb_universal is missing."""
        from enterprise.modules.kb_bridge.kb_bridge import KnowledgeBaseBridge, _FALLBACK

        if not _FALLBACK:
            with patch("enterprise.modules.kb_bridge.kb_bridge._kb", None):
                with patch("enterprise.modules.kb_bridge.kb_bridge._FALLBACK", True):
                    import pytest
                    with pytest.raises(RuntimeError, match="not available"):
                        KnowledgeBaseBridge()

    def test_bridge_close_is_idempotent(self):
        """Closing multiple times should not raise."""
        self._orig_home = os.environ.get("HOME", "")
        self._temp_base = _make_temp_kb_dir()
        os.environ["HOME"] = str(self._temp_base)
        from enterprise.modules.kb_bridge.kb_bridge import KnowledgeBaseBridge

        b = KnowledgeBaseBridge(publish_events=False)
        b.close()
        b.close()  # second close should be safe

    def test_update_nonexistent_safe(self):
        self._orig_home = os.environ.get("HOME", "")
        self._temp_base = _make_temp_kb_dir()
        os.environ["HOME"] = str(self._temp_base)
        from enterprise.modules.kb_bridge.kb_bridge import KnowledgeBaseBridge

        b = KnowledgeBaseBridge(publish_events=False)
        result = b.update_pattern(999_999_999, title="ghost")
        assert result is None
        b.close()


class TestDataclasses:
    """Verify serialization / deserialization helpers."""

    def test_pattern_record_from_row_handles_bad_json(self):
        from enterprise.modules.kb_bridge.kb_bridge import PatternRecord
        class FakeRow(dict):
            def __init__(self):
                super().__init__(
                    id=1,
                    pattern_hash="abc",
                    pattern_type="test",
                    title="T",
                    content="C",
                    metadata="not json",
                    source_profile=None,
                    source_session=None,
                    tags="also not json",
                    created_at=1234567890,
                    updated_at=1234567890,
                    access_count=0,
                    last_accessed=None,
                )
        rec = PatternRecord.from_row(FakeRow())
        assert rec.metadata == "not json" or isinstance(rec.metadata, dict)
        assert rec.tags == "also not json" or isinstance(rec.tags, list)

    def test_pattern_record_to_dict(self):
        from enterprise.modules.kb_bridge.kb_bridge import PatternRecord
        rec = PatternRecord(
            id=1,
            pattern_hash="abc",
            pattern_type="t",
            title="T",
            content="C",
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        d = rec.to_dict()
        assert d["id"] == 1
        assert d["created_at"] == "2025-01-01T00:00:00+00:00"

    def test_metric_snapshot_to_dict(self):
        from enterprise.modules.kb_bridge.kb_bridge import MetricSnapshot
        snap = MetricSnapshot(patterns_total=10)
        d = snap.to_dict()
        assert d["patterns_total"] == 10
        assert "timestamp" in d


class TestModuleLifecycleIntegration:
    """Smoke test for the full module lifecycle."""

    def setup_method(self):
        self._orig_home = os.environ.get("HOME", "")
        self._temp_base = _make_temp_kb_dir()
        os.environ["HOME"] = str(self._temp_base)
        from enterprise.modules.kb_bridge import ENIKBModule
        self.module = ENIKBModule(config={"profile": "test", "publish_events": False})

    def teardown_method(self):
        os.environ["HOME"] = self._orig_home

    def test_initialize_and_shutdown(self):
        import asyncio

        async def run():
            await self.module.initialize()
            assert self.module.status.value == "healthy"
            await self.module.shutdown()

        asyncio.run(run())

    def test_health_check_after_initialize(self):
        import asyncio

        async def run():
            await self.module.initialize()
            status = await self.module.health_check()
            assert status.value == "healthy"

        asyncio.run(run())


class TestSearchResult:
    """Additional search result behaviour."""

    def setup_method(self):
        self._orig_home = os.environ.get("HOME", "")
        self._temp_base = _make_temp_kb_dir()
        os.environ["HOME"] = str(self._temp_base)
        from enterprise.modules.kb_bridge.kb_bridge import KnowledgeBaseBridge
        self.bridge = KnowledgeBaseBridge(profile="test", publish_events=False)

    def teardown_method(self):
        self.bridge.close()
        os.environ["HOME"] = self._orig_home

    def test_search_result_has_timings(self):
        results = self.bridge.search_patterns(query="test")
        assert results.execution_time_ms >= 0

    def test_semantic_search_graceful_degredation(self):
        """semantic_search should not crash when sentence-transformers is absent."""
        results = self.bridge.semantic_search(query="hello")
        # May return empty or real results; should not raise
        assert isinstance(results, list)