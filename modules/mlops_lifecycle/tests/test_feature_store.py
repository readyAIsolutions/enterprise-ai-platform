"""Tests for the Feature/Label Store submodule (SQLite-backed, versioned)."""

from modules.mlops_lifecycle.feature_label_store import (
    FeatureLabelStore,
    FeatureSet,
    FeatureVector,
    LabelSet,
    create_feature_label_store,
)


def test_create_feature_label_store_returns_default_instance():
    store = create_feature_label_store()
    assert isinstance(store, FeatureLabelStore)
    assert store.is_open
    store.close()


def test_register_feature_and_label_sets(tmp_path):
    db = tmp_path / "features.db"
    store = FeatureLabelStore(db_path=str(db))
    fs = store.register_feature_set("spam_features", ["length", "urgency", "has_link"])
    ls = store.register_label_set("spam_labels", ["spam", "ham"])
    assert isinstance(fs, FeatureSet)
    assert isinstance(ls, LabelSet)
    assert fs.feature_names == ["length", "urgency", "has_link"]
    assert store.get_feature_set(fs.feature_set_id).name == "spam_features"
    assert store.get_label_set(ls.label_set_id).name == "spam_labels"
    store.close()


def test_register_returns_existing_schema_by_name(tmp_path):
    store = FeatureLabelStore(db_path=str(tmp_path / "f.db"))
    a = store.register_feature_set("x", ["a", "b"])
    b = store.register_feature_set("x", ["a", "b"])
    assert a.feature_set_id == b.feature_set_id
    store.close()


def test_version_store_and_retrieve_roundtrip(tmp_path, monkeypatch):
    store = FeatureLabelStore(db_path=str(tmp_path / "v.db"))
    fs = store.register_feature_set("f", ["a", "b"])
    lb = store.register_label_set("l", ["pos", "neg"])
    vectors = [
        FeatureVector(features={"a": 1.0, "b": 2.0}, label="pos"),
        FeatureVector(features={"a": 2.0, "b": 3.0}, label="neg"),
    ]
    dv = store.create_version(fs, vectors, label_set=lb, description="train split")
    assert dv.row_count == 2
    assert dv.version == "1"

    got = store.get_version(dv.version)
    assert got is not None
    assert got.feature_set_id == fs.feature_set_id

    rows = store.get_vectors(dv.version)
    assert len(rows) == 2
    assert rows[0].features == {"a": 1.0, "b": 2.0}
    assert rows[0].label == "pos"
    assert rows[1].label == "neg"
    store.close()


def test_versions_are_monotonic_and_listed(tmp_path):
    store = FeatureLabelStore(db_path=str(tmp_path / "m.db"))
    fs = store.register_feature_set("f", ["a"])
    v1 = store.create_version(fs, [FeatureVector(features={"a": 1.0})])
    v2 = store.create_version(fs, [FeatureVector(features={"a": 2.0})])
    assert [v.version for v in store.list_versions()] == ["1", "2"]
    assert v1.version != v2.version
    store.close()


def test_duplicate_version_is_rejected(tmp_path):
    import pytest

    store = FeatureLabelStore(db_path=str(tmp_path / "d.db"))
    fs = store.register_feature_set("f", ["a"])
    store.create_version(fs, [FeatureVector(features={"a": 1.0})], version="7")
    with pytest.raises(ValueError):
        store.create_version(fs, [FeatureVector(features={"a": 2.0})], version="7")
    store.close()
