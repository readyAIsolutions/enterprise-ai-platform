"""Tests for ICM's integration into the local_controller prompt layer."""
from __future__ import annotations

import os

import pytest

from enterprise.modules.icm import scaffold


def test_enrich_prompt_injects_icm_stage(tmp_path, monkeypatch):
    # scaffold an ICM project, point ICM_PROJECT at it
    root = scaffold(tmp_path / "skill")
    icm_path = str(root)
    monkeypatch.setenv("ICM_PROJECT", icm_path)
    # need the repo on path for enterprise.modules.icm inside enrich_prompt
    import sys
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if repo not in sys.path:
        sys.path.insert(0, repo)

    from local_controller.planner import enrich_prompt
    out = enrich_prompt("verify the citation", goal="verify the citation")
    assert "ICM STAGE" in out
    # progressive disclosure: only the routed stage's markdown is injected
    assert "verification" in out
    # the generic building-guidance is still present (base enrichment retained)
    assert "BUILDING GUIDANCE" in out


def test_enrich_prompt_noop_without_icm(tmp_path, monkeypatch):
    monkeypatch.delenv("ICM_PROJECT", raising=False)
    import sys
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if repo not in sys.path:
        sys.path.insert(0, repo)
    from local_controller.planner import enrich_prompt
    out = enrich_prompt("do a thing")
    assert "ICM STAGE" not in out