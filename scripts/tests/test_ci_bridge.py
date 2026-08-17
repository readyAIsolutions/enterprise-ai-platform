"""Tests for ci_bridge.build_plan (the deterministic goal->step planner).

These verify the real contract without network: the stage order, step count,
dependency chain, determinism, and the CLI shape.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent  # enterprise/
BRIDGE = REPO / "scripts" / "ci_bridge.py"

sys.path.insert(0, str(REPO / "scripts"))
import ci_bridge  # noqa: E402

STAGES = ["intake", "research", "drafting", "verification", "output"]


def test_returns_five_icm_stages_in_order():
    steps = ci_bridge.build_plan("build a budget tracker")
    assert len(steps) == len(STAGES) == 5
    assert [s.stage for s in steps] == STAGES


def test_steps_are_linely_chained():
    steps = ci_bridge.build_plan("x")
    for i, s in enumerate(steps):
        if i == 0:
            assert s.deps == []
        else:
            assert s.deps == [i]  # depends on the step before it


def test_deterministic_same_output():
    a = ci_bridge.build_plan("greet the user at launch")
    b = ci_bridge.build_plan("greet the user at launch")
    assert [s.prompt for s in a] == [s.prompt for s in b]
    assert ci_bridge.build_plan_id("greet the user at launch", a) == \
        ci_bridge.build_plan_id("greet the user at launch", b)


def test_goal_embedded_in_drafting_task():
    steps = ci_bridge.build_plan("build a budget tracker")
    drafting = [s for s in steps if s.stage == "drafting"][0]
    assert "build a budget tracker" in drafting.task
    assert drafting.feature == "implementation"
    assert drafting.test_hint


def test_empty_goal_defaults():
    steps = ci_bridge.build_plan("")
    assert steps[3].stage == "verification"
    assert all(len(s.task) for s in steps)


def test_cli_json_emits_plan():
    r = subprocess.run(
        [sys.executable, str(BRIDGE), "--json", "--goal", "build a to-do app"],
        capture_output=True, text=True, timeout=30, cwd=str(REPO))
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["count"] == 5
    assert data["stages"] == STAGES
    assert "plan_id" in data


def test_cli_human_prints_stages():
    r = subprocess.run(
        [sys.executable, str(BRIDGE), "--goal", "ship a cli tool"],
        capture_output=True, text=True, timeout=30, cwd=str(REPO))
    assert r.returncode == 0
    for stage in STAGES:
        assert stage.upper() in r.stdout
