"""Tests for the ICM (Interpretable Context Methodology) module."""
from __future__ import annotations

import asyncio

import pytest

from enterprise.modules.icm import (
    ICMProject,
    classify,
    create_icm_module,
    scaffold,
    should_use_swarm,
)


@pytest.fixture()
def project(tmp_path):
    """A freshly scaffolded ICM project."""
    root = scaffold(tmp_path / "demo", with_examples=True)
    return ICMProject.open(root)


def test_scaffold_creates_standard_template(tmp_path):
    root = scaffold(tmp_path / "proj")
    assert (root / "00_master.md").exists()
    for slug in ["01_intake", "02_research", "03_drafting",
                 "04_verification", "05_output"]:
        assert (root / slug).is_dir()
        assert (root / slug / "instructions.md").exists()
        assert (root / slug / "scripts").is_dir()


def test_open_requires_master(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        ICMProject.open(empty)


def test_routes_stage_by_keyword(tmp_path):
    proj = ICMProject.open(scaffold(tmp_path / "p2"))
    stage = proj.route("please verify the citation")
    assert stage is not None
    assert "verification" in stage.slug or "4" in stage.slug


def test_progressive_disclosure_only_loads_stage(project):
    # staging context should be the stage's markdown, not the whole system
    ctx = project.stage_context(project.stages[0])
    assert isinstance(ctx, str)
    assert len(ctx) > 0
    # it should reference the stage's role, proving we loaded THAT stage
    assert "Stage" in ctx or "Role" in ctx


def test_master_map_routes_explicit_task(tmp_path):
    root = scaffold(tmp_path / "p3")
    # add an explicit task->stage mapping
    master = root / "00_master.md"
    master.write_text(
        "## task routing\n## 01_intake, ingest order\n## 05_output, emit report\n",
        encoding="utf-8",
    )
    proj = ICMProject.open(root)
    stage = proj.route("ingest order")
    assert stage is not None
    assert "intake" in stage.slug


def test_classifier_sequential_vs_swarm():
    assert classify("run the compliance checklist on this record") == "sequential"
    assert classify("verify the citation") == "sequential"
    # judgment-heavy: legal reasoning, classification of a legal principle, generation
    assert classify("cross-validate the legal reasoning with a second model") == "swarm"
    assert classify("generate a character with consistent motivation") == "swarm"
    assert should_use_swarm("debate the two plot interpretations") is True
    assert should_use_swarm("convert the file to PDF") is False


def test_module_registers_and_initializes(tmp_path):
    mod = create_icm_module({"projects_dir": str(tmp_path / "icm")})
    asyncio.run(mod.initialize())
    assert mod.status.value in ("healthy", "HEALTHY") or "HEALTHY" in str(mod.status)
    assert mod.health_check.__name__ == "health_check"
    root = mod.new_project("skill_x")
    assert (root / "00_master.md").exists()
    route = mod.route(str(root), "verify the output")
    assert route["route"] == "sequential"
    assert route["stage"] is not None