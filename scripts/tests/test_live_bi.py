"""Minimal tests for the C2 live BI CLI.

Verifies that live_bi counts sessions/artifacts from real telemetry and that
it does NOT crash on empty/missing data (reporting zeros + a note).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SCRIPTS = REPO / "scripts"

_spec = importlib.util.spec_from_file_location("live_bi", SCRIPTS / "live_bi.py")
assert _spec and _spec.loader
live_bi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(live_bi)


def _make_session(base: Path, name: str, n_artifacts: int) -> None:
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text("{}", encoding="utf-8")
    for i in range(1, n_artifacts + 1):
        (d / f"step{i:02d}_thing.py").write_text("print(1)\n", encoding="utf-8")


def test_counts_sessions_and_artifacts(tmp_path: Path) -> None:
    _make_session(tmp_path, "session_1", 3)
    _make_session(tmp_path, "session_2", 2)
    _make_session(tmp_path, "not_a_session", 99)  # ignored

    builds = live_bi.count_sessions_and_artifacts(tmp_path)
    assert builds["ok"] is True
    assert builds["sessions"] == 2
    assert builds["artifacts"] == 5  # manifests excluded


def test_empty_missing_data_does_not_crash_and_reports_zeros(tmp_path: Path) -> None:
    # directory does not exist at all
    missing = live_bi.count_sessions_and_artifacts(tmp_path / "does_not_exist")
    assert missing["ok"] is False
    assert missing["sessions"] == 0
    assert missing["artifacts"] == 0

    # a truly empty directory (exists but no sessions)
    empty = tmp_path / "empty"
    empty.mkdir()
    builds = live_bi.count_sessions_and_artifacts(empty)
    assert builds["ok"] is True
    assert builds["sessions"] == 0
    assert builds["artifacts"] == 0

    meter = live_bi.load_cost_meter(tmp_path / "cost_meter.json")  # missing
    assert meter["present"] is False and meter["tokens"] is None

    snap = live_bi.render_snapshot(
        builds, meter, live_bi.DEFAULT_RATE, live_bi.DEFAULT_COST_PER_1K
    )
    assert "Build sessions : 0" in snap
    assert "Artifacts      : 0" in snap
    assert "cost_meter.json" in snap  # the note explains the zeros


def test_reads_real_cost_meter_when_present(tmp_path: Path) -> None:
    _make_session(tmp_path, "session_1", 2)
    meter_path = tmp_path / "cost_meter.json"
    meter_path.write_text(json.dumps({"tokens": 50000, "cost": 1.25}), encoding="utf-8")

    builds = live_bi.count_sessions_and_artifacts(tmp_path)
    meter = live_bi.load_cost_meter(meter_path)
    assert meter["present"] is True
    assert meter["tokens"] == 50000 and meter["cost"] == 1.25

    snap = live_bi.render_snapshot(
        builds, meter, live_bi.DEFAULT_RATE, live_bi.DEFAULT_COST_PER_1K
    )
    assert "Est tokens     : 50000" in snap
    assert "Est cost       : $1.2500" in snap
    assert "(estimated)" not in snap
