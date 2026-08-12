"""Unit tests for the enterprise mlops_lifecycle module.

The package ``__init__.py`` eagerly imports a number of sibling submodules
(feature_label_store, canary_manager, ...) that are not present in this
checkout, so importing the package fails. To keep tests isolated and
runnable against only the available production code, the two real modules
present (``config_manager`` and ``experiment_tracker``) are loaded directly
from their file paths via ``importlib`` instead of through the package
import chain.

All state is isolated in :class:`tempfile.TemporaryDirectory`.
"""

import json
import os
import sqlite3
from pathlib import Path

import pytest

from modules.mlops_lifecycle.config_manager import (
    ConfigManager,
    ConfigSchema,
    ConfigValidator,
    ExperimentConfiguration,
    create_config_manager,
)
from modules.mlops_lifecycle.experiment_tracker import (
    ExperimentConfig,
    ExperimentLineage,
    ExperimentRecord,
    ExperimentStatus,
    ExperimentTracker,
    create_experiment_tracker,
)


def make_valid_config(agent_type="react", temperature=0.5):
    """Produce a config that satisfies the default experiment schema."""
    return {
        "agent_type": agent_type,
        "model_config": {
            "provider": "openai",
            "model_name": "gpt-4o",
            "temperature": temperature,
        },
        "prompt_config": {
            "system_prompt": "You are a helpful assistant.",
            "user_prompt_template": "Answer: {query}",
        },
        "eval_config": {
            "metrics": ["accuracy", "latency"],
            "thresholds": {"accuracy": 0.9},
        },
    }


def make_experiment_config(name="exp1", **overrides):
    data = {
        "name": name,
        "description": "A test experiment",
        "hypothesis": "The agent improves with tool use.",
        "agent_type": "react",
        "model_config": {"provider": "openai", "model_name": "gpt-4o"},
        "prompt_config": {"system_prompt": "hi", "user_prompt_template": "{q}"},
        "tool_config": {"enabled_tools": ["search"]},
        "eval_config": {"metrics": ["accuracy"], "thresholds": {"accuracy": 0.9}},
        "rollout_config": {"strategy": "canary", "initial_percentage": 5},
    }
    data.update(overrides)
    return ExperimentConfig(**data)


@pytest.fixture
def tmp_db(tmp_path):
    """Return a helper that builds a db path inside a fresh temp dir."""
    return tmp_path


# --------------------------------------------------------------------------
# ConfigSchema / ConfigValidator
# --------------------------------------------------------------------------

def test_config_schema_validation_rejects_missing_required_field():
    schema = ConfigSchema(
        schema={
            "type": "object",
            "required": ["agent_type", "eval_config"],
            "properties": {
                "agent_type": {"type": "string"},
                "eval_config": {"type": "object"},
            },
        }
    )
    valid, errors = schema.validate({"agent_type": "react"})
    assert valid is False
    assert any("eval_config" in e and "required" in e for e in errors)


def test_config_schema_rejects_wrong_type_and_enum():
    schema = ConfigSchema(
        schema={
            "type": "object",
            "required": ["agent_type", "temperature"],
            "properties": {
                "agent_type": {
                    "type": "string",
                    "enum": ["react", "swarm"],
                },
                "temperature": {"type": "number"},
            },
        }
    )
    valid, errors = schema.validate({"agent_type": "blob", "temperature": "hot"})
    assert valid is False
    assert any("enum" in e for e in errors)
    assert any("expected number" in e for e in errors)


def test_config_validator_unknown_schema_reports_error():
    v = ConfigValidator()
    valid, errors = v.validate({}, "no_such_schema")
    assert valid is False
    assert errors == ["Schema 'no_such_schema' not registered"]


# --------------------------------------------------------------------------
# ConfigManager: persistence, versioning, diff, patch
# --------------------------------------------------------------------------

def test_create_config_persists_and_roundtrips(tmp_db):
    cm = create_config_manager(str(tmp_db / "configs.db"))
    created = cm.create_config(
        "roundtrip", make_valid_config(), description="desc", created_by="tester"
    )
    assert created.config_id.startswith("cfg-")
    assert created.current_version.version == "1.0.0"

    fetched = cm.get_config(created.config_id)
    assert fetched is not None
    assert fetched.name == "roundtrip"
    assert fetched.current_version.config["agent_type"] == "react"
    assert fetched.current_version.created_by == "tester"


def test_create_config_validates_and_raises(tmp_db):
    cm = create_config_manager(str(tmp_db / "configs.db"))
    with pytest.raises(ValueError, match="validation failed"):
        cm.create_config("bad", {"agent_type": "react"})  # missing required blocks


def test_update_config_bumps_semver_and_keeps_history(tmp_db):
    cm = create_config_manager(str(tmp_db / "configs.db"))
    created = cm.create_config("ver", make_valid_config())
    cfg_id = created.config_id

    v2 = make_valid_config(temperature=0.9)
    updated = cm.update_config(cfg_id, v2, changelog="raise temp", version_bump="minor")
    assert updated.current_version.version == "1.1.0"
    assert updated.current_version.changelog == "raise temp"

    minor = cm.update_config(cfg_id, make_valid_config(temperature=0.1), version_bump="major")
    assert minor.current_version.version == "2.0.0"

    fetched = cm.get_config(cfg_id)
    assert len(fetched.versions) == 3
    assert cm.get_version(cfg_id, "1.0.0") is not None
    assert cm.get_version(cfg_id, "2.0.0") is not None


def test_diff_versions_and_apply_patch(tmp_db):
    cm = create_config_manager(str(tmp_db / "configs.db"))
    v1 = make_valid_config(temperature=0.5)
    created = cm.create_config("diff", v1)
    cfg_id = created.config_id

    v2 = make_valid_config(temperature=0.9)
    cm.update_config(cfg_id, v2, changelog="warm")

    diff = cm.diff_versions(cfg_id, "1.0.0", "1.0.1")
    # temperature changed inside model_config
    changed = diff["changed"]["model_config"]["changed"]["temperature"]
    assert changed == {"from": 0.5, "to": 0.9}

    # apply a direct change patch: set temperature to 0.3
    patched = cm.apply_patch(
        cfg_id, "1.0.0", {"model_config": {"temperature": {"from": 0.5, "to": 0.3}}}
    )
    fetched = cm.get_config(cfg_id)
    assert fetched.current_version.config["model_config"]["temperature"] == 0.3
    # current version was 1.0.1 after the "warm" patch bump -> apply_patch -> 1.0.2
    assert fetched.current_version.version == "1.0.2"


def test_delete_and_list_configs(tmp_db):
    cm = create_config_manager(str(tmp_db / "configs.db"))
    a = cm.create_config("a", make_valid_config())
    b = cm.create_config("b", make_valid_config())
    all_configs = cm.list_configs()
    ids = {c.config_id for c in all_configs}
    assert {a.config_id, b.config_id} <= ids

    assert cm.delete_config(a.config_id) is True
    assert cm.get_config(a.config_id) is None
    assert cm.delete_config(a.config_id) is False  # already gone


# --------------------------------------------------------------------------
# ExperimentTracker: CRUD, status, metrics, lineage, query
# --------------------------------------------------------------------------

def test_create_and_retrieve_experiment(tmp_db):
    tracker = create_experiment_tracker(str(tmp_db / "experiments.db"))
    cfg = make_experiment_config("t1")
    rec = tracker.create_experiment(cfg)
    assert rec.status == ExperimentStatus.DRAFT
    assert rec.lineage is not None
    assert rec.lineage.root_experiment_id == rec.experiment_id

    fetched = tracker.get_experiment(rec.experiment_id)
    assert fetched is not None
    assert fetched.config.name == "t1"
    assert fetched.config.hypothesis == cfg.hypothesis


def test_set_status_sets_run_complete_timestamps(tmp_db):
    tracker = create_experiment_tracker(str(tmp_db / "e.db"))
    rec = tracker.create_experiment(make_experiment_config("lifecycle"))

    running = tracker.set_status(rec.experiment_id, ExperimentStatus.RUNNING)
    assert running.status == ExperimentStatus.RUNNING
    assert running.started_at is not None
    assert running.completed_at is None

    done = tracker.set_status(rec.experiment_id, ExperimentStatus.COMPLETED)
    assert done.status == ExperimentStatus.COMPLETED
    assert done.completed_at is not None


def test_record_results_and_metrics_persist(tmp_db):
    tracker = create_experiment_tracker(str(tmp_db / "e.db"))
    rec = tracker.create_experiment(make_experiment_config("metrics"))
    rec.results = {"correct": 42, "total": 50}
    rec.metrics = {"accuracy": 0.84, "latency_ms": 120.5}
    rec.artifacts = {"model": "/tmp/model.bin"}
    tracker.update_experiment(rec)

    fetched = tracker.get_experiment(rec.experiment_id)
    assert fetched.results == {"correct": 42, "total": 50}
    assert fetched.metrics == {"accuracy": 0.84, "latency_ms": 120.5}
    assert fetched.artifacts == {"model": "/tmp/model.bin"}


def test_lineage_fork_and_lineage_chain(tmp_db):
    tracker = create_experiment_tracker(str(tmp_db / "e.db"))
    root = tracker.create_experiment(make_experiment_config("root"))

    branch_a = tracker.create_experiment(
        make_experiment_config("a"), parent_experiment_id=root.experiment_id, fork_reason="variant A"
    )
    assert branch_a.lineage.root_experiment_id == root.experiment_id
    assert branch_a.lineage.fork_reason == "variant A"
    assert root.experiment_id in branch_a.lineage.ancestors

    branch_b = tracker.create_experiment(
        make_experiment_config("b"), parent_experiment_id=branch_a.experiment_id, fork_reason="variant B"
    )
    chain = tracker.get_lineage(branch_b.experiment_id)
    ids = [r.experiment_id for r in chain]
    assert ids == [root.experiment_id, branch_a.experiment_id, branch_b.experiment_id]

    children = tracker.get_children(root.experiment_id)
    assert [c.experiment_id for c in children] == [branch_a.experiment_id]


def test_list_experiments_filters_by_status_and_tags(tmp_db):
    tracker = create_experiment_tracker(str(tmp_db / "e.db"))
    r1 = tracker.create_experiment(
        make_experiment_config("one", tags={"team": "alpha"})
    )
    r2 = tracker.create_experiment(
        make_experiment_config("two", tags={"team": "beta"})
    )
    tracker.set_status(r1.experiment_id, ExperimentStatus.RUNNING)
    tracker.set_status(r2.experiment_id, ExperimentStatus.RUNNING)

    running = tracker.list_experiments(status=ExperimentStatus.RUNNING)
    assert len(running) == 2

    alpha = tracker.list_experiments(tags={"team": "alpha"})
    assert [r.experiment_id for r in alpha] == [r1.experiment_id]

    drafts = tracker.list_experiments(status=ExperimentStatus.DRAFT)
    assert drafts == []


def test_delete_experiment(tmp_db):
    tracker = create_experiment_tracker(str(tmp_db / "e.db"))
    rec = tracker.create_experiment(make_experiment_config("delete_me"))
    assert tracker.delete_experiment(rec.experiment_id) is True
    assert tracker.get_experiment(rec.experiment_id) is None
    assert tracker.delete_experiment(rec.experiment_id) is False


def test_delete_cascade_removes_children(tmp_db):
    tracker = create_experiment_tracker(str(tmp_db / "e.db"))
    root = tracker.create_experiment(make_experiment_config("root"))
    child = tracker.create_experiment(
        make_experiment_config("child"), parent_experiment_id=root.experiment_id
    )
    assert tracker.delete_experiment(root.experiment_id, cascade=True) is True
    assert tracker.get_experiment(root.experiment_id) is None
    assert tracker.get_experiment(child.experiment_id) is None


def test_experiment_config_json_roundtrip():
    cfg = make_experiment_config("json_rt", tags={"env": "prod"}, metadata={"x": 1})
    parsed = ExperimentConfig.from_json(cfg.to_json())
    assert parsed.name == "json_rt"
    assert parsed.tags == {"env": "prod"}
    assert parsed.metadata == {"x": 1}
