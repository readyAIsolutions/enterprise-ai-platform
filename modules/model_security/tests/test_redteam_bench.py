#!/usr/bin/env python3
"""Tests for RedTeamBench (Upgrade Run 3) — adversarial attack stopping power."""

import tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from enterprise.modules.model_security.redteam_bench import RedTeamBench, ATTACKS


def _bench(tmp):
    return RedTeamBench({"audit_path": str(Path(tmp) / "audit.log")})


def test_bench_has_cases():
    assert len(ATTACKS) >= 10
    cats = {a["category"] for a in ATTACKS}
    assert "Prompt Injection" in cats
    assert "Jailbreak" in cats
    assert "Benign" in cats


def test_all_attacks_blocked(tmp_path):
    b = _bench(tmp_path)
    r = b.run()
    # benign "TR20/poem" must pass; all attack rows must be blocked
    assert r["slips"] == [], f"attacks slipped through: {r['slips']}"
    assert r["passed"] is True


def test_stop_rate_is_1(tmp_path):
    b = _bench(tmp_path)
    r = b.run()
    assert r["stop_rate"] == 1.0


def test_benign_not_false_positive(tmp_path):
    b = _bench(tmp_path)
    res = {x["id"]: x for x in b.run()["results"]}
    assert res["BENIGN-1"]["blocked"] is False
    assert res["BENIGN-2"]["blocked"] is False
