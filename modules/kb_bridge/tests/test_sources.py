"""
Tests for the pluggable knowledge-source adapters + merge facade added to the
ENI KB bridge (``enterprise.modules.kb_bridge.sources``).

Covers:
  - FileSourceAdapter: query, list_docs, filters, missing-dir error.
  - SqliteSourceAdapter: query, list_docs, metadata round-trip.
  - JsonSourceAdapter: query, list_docs, missing/invalid file errors.
  - SourceRegistry: register / get / list / duplicate & missing errors.
  - KbMerger: cross-source merge, de-duplication by id, re-rank, limit.
  - KbQueryBridge facade: cross-source query, source subset, lifecycle close.

Every adapter is exercised against real temporary files / a real SQLite DB —
no mocks, no stubs.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

# Ensure project root is importable for `enterprise` package.
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pytest  # noqa: E402

from enterprise.modules.kb_bridge.sources import (  # noqa: E402
    FileSourceAdapter,
    JsonSourceAdapter,
    KbDoc,
    KbMerger,
    KbQueryBridge,
    SourceAdapter,
    SourceRegistry,
    SqliteSourceAdapter,
    score_text,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def file_dir(tmp_path: Path) -> Path:
    (tmp_path / "a.md").write_text(
        "Deploy the service with kubernetes and monitor latency.\n"
        "Kubernetes orchestration scales horizontally.",
        encoding="utf-8",
    )
    (tmp_path / "b.txt").write_text(
        "A recipe for homemade pasta sauce with tomatoes and basil.",
        encoding="utf-8",
    )
    (tmp_path / "notes").mkdir(parents=True)
    (tmp_path / "notes" / "c.md").write_text(
        "kubernetes deployment best practices and rollback strategies.",
        encoding="utf-8",
    )
    # Non-doc extension must be ignored.
    (tmp_path / "ignored.py").write_text("kubernetes ignored", encoding="utf-8")
    return tmp_path


@pytest.fixture
def sqlite_db(tmp_path: Path) -> Path:
    db = tmp_path / "kb.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        """CREATE TABLE docs (
            id TEXT PRIMARY KEY, text TEXT, source TEXT,
            metadata TEXT, score REAL
        )"""
    )
    conn.executemany(
        "INSERT INTO docs (id, text, source, metadata, score) VALUES (?,?,?,?,?)",
        [
            ("d1", "kubernetes deployment guide", "ops", json.dumps({"tier": 1}), 9.0),
            ("d2", "baking bread with sourdough starter", "kitchen", "{}", 2.0),
            ("d3", "kubernetes networking and services", "ops", "{}", 6.0),
        ],
    )
    conn.commit()
    conn.close()
    return db


@pytest.fixture
def json_file(tmp_path: Path) -> Path:
    path = tmp_path / "docs.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "j1",
                    "text": "kubernetes scaling tips",
                    "source": "manual",
                    "metadata": {"section": "scaling"},
                },
                {"id": "j2", "text": "fresh pasta recipe", "score": 4.0},
                {"id": "j3", "text": "kubernetes security hardening", "score": 7.0},
            ]
        ),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# FileSourceAdapter
# ---------------------------------------------------------------------------


class TestFileSourceAdapter:
    def test_query_returns_matching_docs(self, file_dir: Path) -> None:
        adapter = FileSourceAdapter(str(file_dir), source_id="files")
        docs = adapter.query("kubernetes")
        assert docs
        assert all(doc.source == "files" for doc in docs)
        assert {d.id for d in docs} == {"a.md", "notes/c.md"}
        adapter.close()

    def test_query_reranked_by_relevance(self, file_dir: Path) -> None:
        adapter = FileSourceAdapter(str(file_dir))
        docs = adapter.query("kubernetes")
        # a.md contains "kubernetes" twice -> higher score than notes/c.md.
        assert docs[0].id == "a.md"
        assert docs[0].score > docs[-1].score
        adapter.close()

    def test_list_docs_returns_all_docs(self, file_dir: Path) -> None:
        adapter = FileSourceAdapter(str(file_dir))
        docs = adapter.list_docs()
        # .md/.txt only; the ignored.py file is excluded.
        assert {d.id for d in docs} == {"a.md", "b.txt", "notes/c.md"}
        assert all("path" in d.metadata for d in docs)
        adapter.close()

    def test_list_docs_honors_limit(self, file_dir: Path) -> None:
        adapter = FileSourceAdapter(str(file_dir))
        docs = adapter.list_docs(limit=2)
        assert len(docs) == 2
        adapter.close()

    def test_query_path_filter(self, file_dir: Path) -> None:
        adapter = FileSourceAdapter(str(file_dir))
        target = str(file_dir / "a.md")
        docs = adapter.query("", filters={"path": target})
        assert [d.id for d in docs] == ["a.md"]
        adapter.close()

    def test_missing_directory_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            FileSourceAdapter(str(tmp_path / "nope"))


# ---------------------------------------------------------------------------
# SqliteSourceAdapter
# ---------------------------------------------------------------------------


class TestSqliteSourceAdapter:
    def test_query_returns_matching_docs(self, sqlite_db: Path) -> None:
        adapter = SqliteSourceAdapter(str(sqlite_db), source_id="db1")
        docs = adapter.query("kubernetes")
        assert {d.id for d in docs} == {"d1", "d3"}
        adapter.close()

    def test_list_docs_returns_all(self, sqlite_db: Path) -> None:
        adapter = SqliteSourceAdapter(str(sqlite_db))
        docs = adapter.list_docs()
        assert {d.id for d in docs} == {"d1", "d2", "d3"}
        assert len(docs) == 3
        adapter.close()

    def test_metadata_round_trip(self, sqlite_db: Path) -> None:
        adapter = SqliteSourceAdapter(str(sqlite_db))
        docs = adapter.list_docs()
        d1 = next(d for d in docs if d.id == "d1")
        assert d1.metadata == {"tier": 1}
        assert d1.score == 9.0
        adapter.close()

    def test_query_source_filter(self, sqlite_db: Path) -> None:
        adapter = SqliteSourceAdapter(str(sqlite_db))
        docs = adapter.query("kubernetes", filters={"source": "ops"})
        assert {d.id for d in docs} == {"d1", "d3"}
        adapter.close()

    def test_query_min_score_filter(self, sqlite_db: Path) -> None:
        adapter = SqliteSourceAdapter(str(sqlite_db))
        docs = adapter.query("kubernetes", filters={"min_score": 7.0})
        # d1 (9.0) and d3 (6.0) match text; d1 survives min_score.
        assert {d.id for d in docs} == {"d1"}
        adapter.close()


# ---------------------------------------------------------------------------
# JsonSourceAdapter
# ---------------------------------------------------------------------------


class TestJsonSourceAdapter:
    def test_query_returns_matching_docs(self, json_file: Path) -> None:
        adapter = JsonSourceAdapter(str(json_file), source_id="json1")
        docs = adapter.query("kubernetes")
        assert {d.id for d in docs} == {"j1", "j3"}
        adapter.close()

    def test_list_docs_returns_all(self, json_file: Path) -> None:
        adapter = JsonSourceAdapter(str(json_file))
        docs = adapter.list_docs()
        assert {d.id for d in docs} == {"j1", "j2", "j3"}
        j1 = next(d for d in docs if d.id == "j1")
        assert j1.metadata == {"section": "scaling", "source": "manual"}
        assert j1.source == adapter.id
        adapter.close()

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            JsonSourceAdapter(str(tmp_path / "missing.json"))

    def test_invalid_structure_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text('{"not": "an array"}', encoding="utf-8")
        adapter = JsonSourceAdapter(str(bad))
        with pytest.raises(ValueError, match="expects a JSON array"):
            adapter.list_docs()
        adapter.close()


# ---------------------------------------------------------------------------
# SourceRegistry
# ---------------------------------------------------------------------------


class TestSourceRegistry:
    def test_register_get_list(self, file_dir: Path, sqlite_db: Path) -> None:
        reg = SourceRegistry()
        fa = reg.register(FileSourceAdapter(str(file_dir), source_id="files"))
        sa = reg.register(SqliteSourceAdapter(str(sqlite_db), source_id="db"))
        assert reg.get("files") is fa
        assert reg.get("db") is sa
        assert reg.list() == ["db", "files"]
        assert len(reg.adapters()) == 2
        reg.close()

    def test_duplicate_register_raises(self, file_dir: Path) -> None:
        reg = SourceRegistry()
        reg.register(FileSourceAdapter(str(file_dir), source_id="dup"))
        with pytest.raises(ValueError, match="already registered"):
            reg.register(FileSourceAdapter(str(file_dir), source_id="dup"))
        reg.close()

    def test_get_missing_raises(self) -> None:
        reg = SourceRegistry()
        with pytest.raises(KeyError):
            reg.get("nope")
        assert reg.get_or_create("nope") is None
        reg.close()


# ---------------------------------------------------------------------------
# KbMerger
# ---------------------------------------------------------------------------


class TestKbMerger:
    def test_merges_and_reranks_across_sources(self, file_dir: Path, json_file: Path) -> None:
        reg = SourceRegistry()
        reg.register(FileSourceAdapter(str(file_dir), source_id="files"))
        reg.register(JsonSourceAdapter(str(json_file), source_id="json"))
        merger = KbMerger(reg)
        docs = merger.query("kubernetes")
        assert {d.id for d in docs} >= {"a.md", "notes/c.md", "j1", "j3"}
        # Re-ranked by score descending.
        scores = [d.score for d in docs]
        assert scores == sorted(scores, reverse=True)
        merger.close()

    def test_dedupes_by_id_keeps_highest_score(self) -> None:
        reg = SourceRegistry()
        merger = KbMerger(reg)

        class Fake(SourceAdapter):
            id = "fake"
            type = "fake"

            def query(
                self,
                query: str,
                filters: dict[str, Any] | None = None,  # noqa: ARG002
            ) -> list[KbDoc]:
                return [
                    KbDoc(id="doc1", text=query, source=self.id, score=3.0),
                    KbDoc(id="doc2", text=query, source=self.id, score=1.0),
                ]

            def list_docs(self, limit: int | None = None) -> list[KbDoc]:  # noqa: ARG002
                return []

            def close(self) -> None:
                pass

        class Fake2(Fake):
            id = "fake2"

            def query(
                self,
                query: str,
                filters: dict[str, Any] | None = None,  # noqa: ARG002
            ) -> list[KbDoc]:
                return [KbDoc(id="doc1", text=query, source=self.id, score=9.0)]

        reg.register(Fake())
        reg.register(Fake2())
        docs = merger.query("x")
        assert len(docs) == 2  # doc1 deduped, doc2 present
        d1 = next(d for d in docs if d.id == "doc1")
        assert d1.score == 9.0  # kept the higher score from fake2
        assert d1.source == "fake2"
        merger.close()

    def test_limit_applied(self, json_file: Path) -> None:
        reg = SourceRegistry()
        reg.register(JsonSourceAdapter(str(json_file), source_id="json"))
        merger = KbMerger(reg)
        docs = merger.query("kubernetes", limit=1)
        assert len(docs) == 1
        assert docs[0].id == "j3"  # highest score for 'kubernetes'
        merger.close()

    def test_source_ids_subset(self, file_dir: Path, json_file: Path) -> None:
        reg = SourceRegistry()
        reg.register(FileSourceAdapter(str(file_dir), source_id="files"))
        reg.register(JsonSourceAdapter(str(json_file), source_id="json"))
        merger = KbMerger(reg)
        docs = merger.query("kubernetes", source_ids=["json"])
        assert all(doc.source == "json" for doc in docs)
        merger.close()

    def test_empty_source_returns_empty(self) -> None:
        reg = SourceRegistry()
        merger = KbMerger(reg)
        assert merger.query("anything") == []
        merger.close()


# ---------------------------------------------------------------------------
# KbQueryBridge facade
# ---------------------------------------------------------------------------


class TestKbQueryBridge:
    def test_cross_source_facade(self, file_dir: Path, json_file: Path) -> None:
        bridge = KbQueryBridge()
        bridge.register(FileSourceAdapter(str(file_dir), source_id="files"))
        bridge.register(JsonSourceAdapter(str(json_file), source_id="json"))
        assert bridge.list_sources() == ["files", "json"]
        docs = bridge.query("kubernetes")
        assert len(docs) >= 4
        assert all(isinstance(d, KbDoc) for d in docs)
        bridge.close()

    def test_facade_limit_and_source_subset(self, file_dir: Path, sqlite_db: Path) -> None:
        bridge = KbQueryBridge()
        bridge.register(FileSourceAdapter(str(file_dir), source_id="files"))
        bridge.register(SqliteSourceAdapter(str(sqlite_db), source_id="db"))
        docs = bridge.query("kubernetes", limit=2, source_ids=["files"])
        assert len(docs) <= 2
        assert all(doc.source == "files" for doc in docs)
        bridge.close()

    def test_lifecycle_close_releases(self, file_dir: Path, sqlite_db: Path) -> None:
        bridge = KbQueryBridge()
        bridge.register(FileSourceAdapter(str(file_dir), source_id="files"))
        bridge.register(SqliteSourceAdapter(str(sqlite_db), source_id="db"))
        bridge.close()
        assert bridge.list_sources() == []  # registry cleared on close


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


class TestScoring:
    def test_score_text_case_insensitive(self) -> None:
        assert score_text("Kubernetes deploy", "kubernetes") > 0
        assert score_text("pasta", "kubernetes") == 0
        assert score_text("", "query") == 0
