"""Tests for the context_workflow_framework module (network-free, stdlib)."""
from __future__ import annotations

import asyncio

import pytest

from enterprise.modules.context_workflow_framework import (
    ContextAssembler,
    ContextWorkflowFrameworkModule,
    WorkflowError,
    WorkflowFramework,
    WorkflowPhase,
    create_context_workflow_framework_module,
)
from enterprise.platform_kernel import HealthStatus


def test_default_framework_has_expected_ordered_phases() -> None:
    fw = WorkflowFramework()
    assert fw.phase_names() == [
        "scope",
        "gather_context",
        "plan",
        "implement",
        "validate",
    ]


def test_add_remove_reorder_phases() -> None:
    fw = WorkflowFramework()
    fw.add_phase(WorkflowPhase(name="review", purpose="human code review"))
    assert fw.phase_names()[-1] == "review"

    fw.remove_phase("review")
    assert "review" not in fw.phase_names()

    new_order = ["validate", "implement", "plan", "gather_context", "scope"]
    fw.reorder(new_order)
    assert fw.phase_names() == new_order

    with pytest.raises(WorkflowError):
        fw.add_phase(WorkflowPhase(name="scope", purpose="dup"))
    with pytest.raises(WorkflowError):
        fw.remove_phase("nope")
    with pytest.raises(WorkflowError):
        fw.reorder(["scope"])


def test_render_contains_phase_names() -> None:
    fw = WorkflowFramework()
    text = fw.render()
    for name in fw.phase_names():
        assert name in text
    assert text.startswith("# Workflow:")


def test_validate_context_flags_missing_keys() -> None:
    fw = WorkflowFramework()
    missing = fw.validate_context({"requirements": "build X"})
    # gather_context needs docs/examples/rules, implement/validate need plan
    assert "gather_context" in missing
    assert set(missing["gather_context"]) == {"docs", "examples", "rules"}
    assert "implement" in missing
    assert "scope" not in missing  # requirements provided

    complete = {
        "requirements": "r",
        "docs": "d",
        "examples": "e",
        "rules": "ru",
        "plan": "p",
    }
    assert fw.validate_context(complete) == {}


def test_next_phase() -> None:
    fw = WorkflowFramework()
    assert fw.next_phase("scope").name == "gather_context"
    assert fw.next_phase("validate") is None
    with pytest.raises(WorkflowError):
        fw.next_phase("missing")


def test_load_template_distinct_phase_sets() -> None:
    prp = WorkflowFramework.load_template("prp")
    bmad = WorkflowFramework.load_template("bmad")
    spec = WorkflowFramework.load_template("spec_kit")
    assert prp.phase_names() != bmad.phase_names()
    assert "generate_prp" in prp.phase_names()
    assert "analyst" in bmad.phase_names()
    assert "specify" in spec.phase_names()
    assert set(WorkflowFramework.available_templates()) == {
        "prp",
        "bmad",
        "spec_kit",
    }
    with pytest.raises(WorkflowError):
        WorkflowFramework.load_template("nope")


def test_context_assembler_headered_ordered_output() -> None:
    asm = (
        ContextAssembler()
        .add_docs("DOC-BODY")
        .add_examples("EX-BODY")
        .add_rules("RULE-BODY")
    )
    out = asm.assemble()
    assert asm.sections() == ["docs", "examples", "rules"]
    assert "## docs" in out and "## examples" in out and "## rules" in out
    assert out.index("## docs") < out.index("## examples") < out.index(
        "## rules"
    )
    assert "DOC-BODY" in out and "EX-BODY" in out and "RULE-BODY" in out


def test_module_lifecycle() -> None:
    mod = create_context_workflow_framework_module()
    assert isinstance(mod, ContextWorkflowFrameworkModule)

    async def run() -> HealthStatus:
        await mod.initialize()
        status = await mod.health_check()
        assert mod.phase_names()[0] == "scope"
        await mod.shutdown()
        return status

    status = asyncio.run(run())
    assert status is HealthStatus.HEALTHY
