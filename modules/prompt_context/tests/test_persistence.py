"""
Persistence + A/B optimizer tests for the prompt_context module.

Covers:
- PromptStore put/get/delete/list/versions round-trip across a reopen
- PromptRegistry SQLite persistence (db_path) without breaking the memory API
- ABOptimizer: exploits the best after enough samples, explores with epsilon,
  throttles low-n variants, tracks stats, persists across reopen
- Lifecycle: open/close/reopen, flush, context-manager cleanup
"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from enterprise.modules.prompt_context import (
    PromptRegistry,
    PromptStore,
    PromptStoreError,
    PromptNotFoundError,
    ABOptimizer,
    VariantStats,
    PromptStatus,
)
from enterprise.modules.prompt_context.persistence import (
    PromptNotFoundError as StoreNotFound,
)


@pytest.fixture
def db_dir(tmp_path):
    return str(tmp_path / "store")


@pytest.fixture
def store(db_dir):
    s = PromptStore(db_dir)
    yield s
    s.close()


# ---------------------------------------------------------------------------
# PromptStore — put / get / list / versions
# ---------------------------------------------------------------------------

def test_store_put_get_roundtrip(store):
    store.put("greet", template="Hello {{name}}", version="0.1.0",
              params={"name": "str"}, status="draft", metadata={"a": 1})
    rec = store.get("greet")
    assert rec["name"] == "greet"
    assert rec["template"] == "Hello {{name}}"
    assert rec["version"] == "0.1.0"
    assert rec["status"] == "draft"
    assert rec["params"] == {"name": "str"}
    assert rec["metadata"] == {"a": 1}


def test_store_put_updates_and_versions_history(store):
    store.put("greet", template="Hello {{name}}", version="0.1.0")
    store.put("greet", template="Hi {{name}}!", version="0.2.0", status="active")
    rec = store.get("greet")
    assert rec["template"] == "Hi {{name}}!"
    assert rec["version"] == "0.2.0"
    assert rec["status"] == "active"
    versions = store.versions("greet")
    assert [v["version"] for v in versions] == ["0.1.0", "0.2.0"]


def test_store_reopen_roundtrip(db_dir, store):
    store.put("a", template="T {{x}}", version="1.0.0", params={"x": "int"}, status="active")
    store.put("a", template="T2 {{x}}", version="1.1.0")
    store.put("b", template="U {{y}}", version="0.5.0")
    store.close()

    reopened = PromptStore(db_dir)
    try:
        assert set(reopened.list()) == {"a", "b"}
        assert reopened.get("a")["template"] == "T2 {{x}}"
        assert reopened.get("a")["version"] == "1.1.0"
        assert [v["version"] for v in reopened.versions("a")] == ["1.0.0", "1.1.0"]
        assert reopened.get("b")["status"] == "draft"
    finally:
        reopened.close()


def test_store_delete_list_count(store):
    store.put("a", template="T", version="1")
    store.put("b", template="U", version="1")
    store.put("c", template="V", version="1")
    assert store.count() == 3
    assert store.delete("b") is True
    assert store.list() == ["a", "c"]
    assert store.count() == 2
    assert store.delete("missing") is False


def test_store_get_missing_raises(store):
    with pytest.raises(StoreNotFound):
        store.get("nope")
    assert store.get_or_none("nope") is None


def test_store_list_records_contains_payload(store):
    store.put("a", template="T {{x}}", version="2", metadata={"k": "v"},
              record_json={"full": "record"})
    recs = store.list_records()
    assert len(recs) == 1
    assert recs[0]["record"] == {"full": "record"}


# ---------------------------------------------------------------------------
# PromptRegistry persistence (db_path) without breaking the memory API
# ---------------------------------------------------------------------------

def test_registry_default_memory_preserves_api():
    reg = PromptRegistry()
    pid = reg.define(name="mem", objective="o", template="T {{x}}")
    assert reg.get_current(pid).template == "T {{x}}"
    # memory default should not write any SQLite file
    assert reg._store is None


def test_registry_persists_across_reopen(db_dir):
    reg = PromptRegistry(db_path=db_dir)
    pid = reg.define(name="persist", objective="o", template="Ver0 {{x}}")
    assert reg.get_current(pid).template == "Ver0 {{x}}"
    reg.update(pid, template="Ver1 {{x}}")
    reg.set_status(pid, PromptStatus.ACTIVE)
    reg.close()

    reopened = PromptRegistry(db_path=db_dir)
    try:
        records = reopened.list_prompts()
        assert len(records) == 1
        ro = records[0]
        assert ro.name == "persist"
        assert reopened.get_current(pid).template == "Ver1 {{x}}"
        assert reopened.get_current(pid).status == PromptStatus.ACTIVE
    finally:
        reopened.close()


def test_registry_versions_and_metrics_persist(db_dir):
    reg = PromptRegistry(db_path=db_dir)
    pid = reg.define(name="vers", objective="o", template="v0 {{x}}")
    reg.update(pid, template="v1 {{x}}")
    from enterprise.modules.prompt_context import MetricName
    reg.record_metric(pid, MetricName.ACCURACY, 0.95)
    reg.close()

    reopened = PromptRegistry(db_path=db_dir)
    try:
        history = reopened.get_history(pid)
        assert len(history) == 2  # created + update
        metrics = reopened.get_metrics(pid)
        assert len(metrics) == 1
        assert metrics[0].value == 0.95
    finally:
        reopened.close()


def test_registry_hard_delete_removes_from_store(db_dir):
    reg = PromptRegistry(db_path=db_dir)
    pid_a = reg.define(name="keep", objective="o", template="K {{x}}")
    pid_b = reg.define(name="drop", objective="o", template="D {{x}}")
    reg.delete(pid_b, hard=True)
    reg.close()

    reopened = PromptRegistry(db_path=db_dir)
    try:
        assert [r.name for r in reopened.list_prompts()] == ["keep"]
    finally:
        reopened.close()


def test_registry_close_flush_and_rollback_persist(db_dir):
    reg = PromptRegistry(db_path=db_dir)
    pid = reg.define(name="rb", objective="o", template="v1 {{x}}")
    reg.update(pid, template="v2 {{x}}")          # now on v2
    reg.rollback(pid, "0.1.0")                     # rollback creates a new version
    reg.close()

    reopened = PromptRegistry(db_path=db_dir)
    try:
        # rollback bumps the version number, so current > 0.2.0
        assert len(reopened.get_history(pid)) == 3
        cur = reopened.get_current(pid)
        assert cur.template == "v1 {{x}}"
    finally:
        reopened.close()


# ---------------------------------------------------------------------------
# ABOptimizer — exploit, explore, throttle, stats
# ---------------------------------------------------------------------------

def test_ab_optimizer_picks_best_after_enough_samples():
    opt = ABOptimizer("qa", variants=["a", "b", "c"], epsilon=0.0,
                      min_samples=5, seed=42)
    for _ in range(10):
        opt.record("a", 0.9)
        opt.record("b", 0.5)
        opt.record("c", 0.4)
    assert opt.best_variant() == "a"
    picks = [opt.select_variant() for _ in range(30)]
    assert all(p == "a" for p in picks)


def test_ab_optimizer_explores_with_epsilon():
    opt = ABOptimizer("qa", variants=["a", "b"], epsilon=1.0, seed=7)
    picks = {opt.select_variant() for _ in range(60)}
    assert picks == {"a", "b"}


def test_ab_optimizer_throttles_low_n_variants():
    opt = ABOptimizer("qa", variants=["a", "b"], epsilon=0.0,
                      min_samples=50, seed=1)
    opt.record("a", 0.9)   # great score but only 1 sample
    opt.record("b", 0.1)
    assert opt.best_variant() is None  # nothing clears the throttle
    # selection still returns a valid variant (bootstrapping exploration)
    assert opt.select_variant() in {"a", "b"}


def test_ab_optimizer_deterministic_with_seed():
    def run(seed):
        opt = ABOptimizer("qa", variants=["x", "y", "z"], epsilon=0.1,
                          seed=seed)
        for i in range(5):
            opt.record(opt.select_variant(), 0.5)
        return [opt.stats(v).n for v in ("x", "y", "z")]
    assert run(123) == run(123)
    assert run(123) == run(123)  # idempotent


def test_ab_optimizer_tracks_stats():
    opt = ABOptimizer("qa", variants=["a", "b"], epsilon=0.0, seed=5)
    opt.record("a", 0.8)
    opt.record("a", 0.9)
    st = opt.stats("a")
    assert st.n == 2
    assert st.mean_score == pytest.approx(0.85)
    assert st.best_score == 0.9
    assert st.last_used is not None
    assert opt.stats("b").n == 0


def test_ab_optimizer_stats_persist_across_reopen(db_dir):
    opt = ABOptimizer("qa", variants=["a", "b"], epsilon=0.0,
                      min_samples=1, seed=9, db_path=db_dir)
    for _ in range(6):
        opt.record("a", 0.85)
        opt.record("b", 0.55)
    opt.close()

    reopened = ABOptimizer("qa", variants=["a", "b"], epsilon=0.0,
                           min_samples=1, seed=9, db_path=db_dir)
    try:
        assert reopened.stats("a").n == 6
        assert reopened.stats("a").mean_score == pytest.approx(0.85)
        assert reopened.stats("b").n == 6
        assert reopened.best_variant() == "a"
    finally:
        reopened.close()


def test_ab_optimizer_add_variant_and_len():
    opt = ABOptimizer("qa", epsilon=0.0, seed=1)
    assert len(opt) == 0
    opt.add_variant("v1")
    opt.add_variant("v1")  # idempotent
    opt.add_variant("v2")
    assert len(opt) == 2
    assert opt.variants == ["v1", "v2"]
    opt.record("v3", 0.7)  # record auto-registers
    assert len(opt) == 3


def test_ab_optimizer_no_variants_raises():
    opt = ABOptimizer("qa", seed=1)
    with pytest.raises(StoreNotFound):
        opt.select_variant()


def test_variant_stats_from_dict():
    st = VariantStats.from_dict({"n": 4, "mean_score": 0.75, "best_score": 0.9})
    assert st.n == 4
    assert st.mean_score == 0.75
    assert st.best_score == 0.9


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def test_store_context_manager_auto_close(tmp_path):
    path = str(tmp_path / "ctx")
    with PromptStore(path) as s:
        s.put("a", template="T", version="1")
        assert s.get("a")["template"] == "T"
    # reopened after with-block
    with PromptStore(path) as s2:
        assert s2.get("a")["template"] == "T"


def test_store_in_memory_db():
    s = PromptStore(None)
    s.put("a", template="T", version="1")
    assert s.get("a")["template"] == "T"
    s.close()
