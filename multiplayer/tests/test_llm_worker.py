"""Tests for the multiplayer LLM worker (real one-prompt->program across fleet)."""
from __future__ import annotations

import os
import tempfile

from enterprise.multiplayer.client.runner import llm_worker, WORKERS


def test_llm_worker_in_registry():
    assert "llm" in WORKERS


def test_llm_worker_falls_back_offline(tmp_path):
    # No MP_LLM_URL set -> deterministic local scaffold path, artifact written.
    for k in ("MP_LLM_URL", "MP_LLM_KEY_ENV", "MP_LLM_MODEL"):
        os.environ.pop(k, None)
    w = llm_worker(cwd=str(tmp_path))
    task = {
        "task_id": "t1",
        "goal": "build a small to-do app",
        "step": 1,
        "feature": "core_logic",
        "prompt": "implement core logic",
        "test_hint": "'def main' in source",
    }
    res = w.run(task)
    assert res["ok"] is True
    assert res["artifacts"], "should return an artifact"
    path = os.path.join(str(tmp_path), res["artifacts"][0]["path"])
    assert os.path.exists(path)
    with open(path) as fh:
        assert fh.read().strip() != ""


def test_llm_worker_redacts_secrets(tmp_path):
    # Even in offline mode the summary/artifacts must not contain a leaked secret.
    for k in ("MP_LLM_URL", "MP_LLM_KEY_ENV", "MP_LLM_MODEL"):
        os.environ.pop(k, None)
    w = llm_worker(cwd=str(tmp_path))
    task = {"task_id": "t2", "goal": "build x", "step": 2,
            "feature": "tests_and_validation",
            "prompt": "table with api_key SUPER_SECRET_123",
            "test_hint": "'Test' in tests"}
    res = w.run(task)
    joined = " ".join(res.get("summary", "")) + \
        " ".join(a.get("content", "") for a in res.get("artifacts", []))
    assert "SUPER_SECRET_123" not in joined


def test_llm_worker_respects_len_limit(tmp_path):
    # prompt >4k still yields a result (no crash).
    for k in ("MP_LLM_URL", "MP_LLM_KEY_ENV", "MP_LLM_MODEL"):
        os.environ.pop(k, None)
    w = llm_worker(cwd=str(tmp_path))
    big = "A" * 6000
    task = {"task_id": "t3", "goal": big, "feature": "requirements_and_spec",
            "prompt": big, "step": 1, "test_hint": "assert 'requirements' in text"}
    res = w.run(task)
    assert res["artifacts"]