"""Tests for composable_workflow_engine — grounded in ColeMedin's transcript."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from enterprise.modules.composable_workflow_engine import (
    ComposableWorkflowEngineModule,
    ValidationResult,
    WorkflowEngine,
    WorkflowError,
    WorkflowPhase,
    WorkflowTemplate,
    create_composable_workflow_engine_module,
)
from enterprise.platform_kernel import HealthStatus


# ── fixtures / helpers ───────────────────────────────────────────────────────
def _phase(name, role="worker", inputs=None, outputs=None):
    return WorkflowPhase(
        name=name,
        role=role,
        instructions=f"do {name}",
        inputs=inputs or [],
        outputs=outputs or [],
    )


def _linear_template(name="lin"):
    return WorkflowTemplate(
        name=name,
        phases=[
            _phase("a", inputs=["idea"], outputs=["x"]),
            _phase("b", inputs=["x"], outputs=["y"]),
            _phase("c", inputs=["y"], outputs=["z"]),
        ],
    )


# ── WorkflowPhase ────────────────────────────────────────────────────────────
def test_phase_requires_name():
    with pytest.raises(WorkflowError):
        WorkflowPhase(name="", role="r", instructions="i")


def test_phase_requires_role():
    with pytest.raises(WorkflowError):
        WorkflowPhase(name="p", role="", instructions="i")


def test_phase_rejects_unknown_context_component():
    with pytest.raises(WorkflowError):
        WorkflowPhase(
            name="p", role="r", instructions="i", context_components=["bogus"]
        )


def test_phase_accepts_known_context_component():
    p = WorkflowPhase(
        name="p", role="r", instructions="i", context_components=["rag"]
    )
    assert p.context_components == ["rag"]


def test_phase_roundtrip():
    p = _phase("a", inputs=["i"], outputs=["o"])
    p2 = WorkflowPhase.from_dict(p.to_dict())
    assert p2 == p


def test_phase_from_dict_missing_key():
    with pytest.raises(WorkflowError):
        WorkflowPhase.from_dict({"role": "r"})


def test_phase_from_dict_not_dict():
    with pytest.raises(WorkflowError):
        WorkflowPhase.from_dict(["nope"])


# ── WorkflowTemplate ─────────────────────────────────────────────────────────
def test_template_requires_name():
    with pytest.raises(WorkflowError):
        WorkflowTemplate(name="")


def test_template_rejects_unknown_framework():
    with pytest.raises(WorkflowError):
        WorkflowTemplate(name="t", framework="nope")


def test_template_phase_names():
    t = _linear_template()
    assert t.phase_names() == ["a", "b", "c"]


def test_template_get_phase():
    t = _linear_template()
    assert t.get_phase("b").name == "b"
    assert t.get_phase("zzz") is None


def test_template_add_phase_fluent():
    t = WorkflowTemplate(name="t")
    t.add_phase(_phase("a")).add_phase(_phase("b"))
    assert t.phase_names() == ["a", "b"]


def test_template_add_phase_type_check():
    t = WorkflowTemplate(name="t")
    with pytest.raises(WorkflowError):
        t.add_phase("not a phase")


def test_template_roundtrip():
    t = _linear_template()
    t2 = WorkflowTemplate.from_dict(t.to_dict())
    assert t2.name == t.name
    assert t2.phase_names() == t.phase_names()
    assert t2.phases == t.phases


def test_template_to_dict_json_safe():
    t = _linear_template()
    s = json.dumps(t.to_dict())
    assert "phases" in json.loads(s)


def test_template_from_dict_missing_key():
    with pytest.raises(WorkflowError):
        WorkflowTemplate.from_dict({"framework": "custom"})


# ── built-in registration ────────────────────────────────────────────────────
def test_engine_registers_builtins():
    eng = WorkflowEngine()
    names = eng.all_templates()
    assert "prp" in names
    assert "spec-kit" in names
    assert "three-step" in names


def test_prp_template_phases():
    eng = WorkflowEngine()
    prp = eng.get_template("prp")
    assert prp.framework == "prp"
    assert "vibe_planning" in prp.phase_names()
    assert "create_plan" in prp.phase_names()
    assert "implementation" in prp.phase_names()
    assert "validation" in prp.phase_names()


def test_prp_implementation_no_subagent():
    # Transcript: implementation purposely does NOT use sub-agents.
    eng = WorkflowEngine()
    prp = eng.get_template("prp")
    assert prp.get_phase("implementation").uses_sub_agent is False
    assert prp.get_phase("create_plan").uses_sub_agent is True
    assert prp.get_phase("validation").uses_sub_agent is True


def test_spec_kit_template():
    eng = WorkflowEngine()
    sk = eng.get_template("spec-kit")
    assert sk.phase_names() == ["specify", "plan", "implement", "validate"]


def test_three_step_template():
    eng = WorkflowEngine()
    ts = eng.get_template("three-step")
    assert ts.phase_names() == ["planning", "implementing", "validating"]


def test_get_unknown_template():
    eng = WorkflowEngine()
    with pytest.raises(WorkflowError):
        eng.get_template("nope")


def test_has_template():
    eng = WorkflowEngine()
    assert eng.has_template("prp")
    assert not eng.has_template("nope")


# ── registration / composition ───────────────────────────────────────────────
def test_register_template():
    eng = WorkflowEngine()
    eng.register_template(_linear_template("mine"))
    assert "mine" in eng.all_templates()


def test_register_duplicate_rejected():
    eng = WorkflowEngine()
    eng.register_template(_linear_template("mine"))
    with pytest.raises(WorkflowError):
        eng.register_template(_linear_template("mine"))


def test_register_overwrite():
    eng = WorkflowEngine()
    eng.register_template(_linear_template("mine"))
    eng.register_template(_linear_template("mine"), overwrite=True)
    assert "mine" in eng.all_templates()


def test_register_type_check():
    eng = WorkflowEngine()
    with pytest.raises(WorkflowError):
        eng.register_template("nope")


def test_compose_custom_template():
    eng = WorkflowEngine()
    t = eng.compose(
        "custom1",
        phases=[
            _phase("research", inputs=["idea"], outputs=["ctx"]),
            _phase("build", inputs=["ctx"], outputs=["code"]),
        ],
        description="my own flow",
    )
    assert t.name == "custom1"
    assert eng.has_template("custom1")
    assert t.phase_names() == ["research", "build"]


def test_compose_no_register():
    eng = WorkflowEngine()
    eng.compose("tmp", phases=[_phase("a")], register=False)
    assert not eng.has_template("tmp")


# ── validation ────────────────────────────────────────────────────────────────
def test_validate_good_template():
    eng = WorkflowEngine()
    res = eng.validate_template(_linear_template())
    assert isinstance(res, ValidationResult)
    assert res.valid
    assert res.errors == []


def test_validate_empty_phases():
    eng = WorkflowEngine()
    res = eng.validate_template(WorkflowTemplate(name="empty"))
    assert not res.valid
    assert any("no phases" in e for e in res.errors)


def test_validate_duplicate_names():
    eng = WorkflowEngine()
    t = WorkflowTemplate(
        name="dup",
        phases=[_phase("a", outputs=["x"]), _phase("a", inputs=["x"])],
    )
    res = eng.validate_template(t)
    assert not res.valid
    assert any("duplicate" in e for e in res.errors)


def test_validate_missing_input():
    eng = WorkflowEngine()
    t = WorkflowTemplate(
        name="miss",
        phases=[
            _phase("a", inputs=["idea"], outputs=["x"]),
            _phase("b", inputs=["nonexistent"], outputs=["y"]),
        ],
    )
    res = eng.validate_template(t)
    assert not res.valid
    assert any("nonexistent" in e for e in res.errors)


def test_validate_warns_no_outputs():
    eng = WorkflowEngine()
    t = WorkflowTemplate(name="w", phases=[_phase("a", inputs=["idea"])])
    res = eng.validate_template(t)
    assert res.valid
    assert any("no outputs" in w for w in res.warnings)


def test_validate_builtin_templates_all_valid():
    eng = WorkflowEngine()
    for name in ["prp", "spec-kit", "three-step"]:
        res = eng.validate_template(eng.get_template(name))
        assert res.valid, f"{name}: {res.errors}"


def test_validation_result_to_dict():
    r = ValidationResult(valid=False, errors=["e"], warnings=["w"])
    assert r.to_dict() == {
        "valid": False,
        "errors": ["e"],
        "warnings": ["w"],
    }


# ── execution ─────────────────────────────────────────────────────────────────
def test_run_produces_per_phase_log():
    eng = WorkflowEngine()
    result = eng.run("three-step", context={"idea": "build an agent"})
    assert result["template"] == "three-step"
    assert result["phase_count"] == 3
    assert len(result["phase_log"]) == 3
    assert [p["phase"] for p in result["phase_log"]] == [
        "planning",
        "implementing",
        "validating",
    ]


def test_run_artifacts_flow_between_phases():
    eng = WorkflowEngine()
    result = eng.run("lin", context={"idea": "x"}) if eng.has_template(
        "lin"
    ) else None
    # register a linear template to test artifact flow
    eng.register_template(_linear_template("flow"))
    result = eng.run("flow", context={"idea": "x"})
    # phase b consumed x produced by a
    log_b = next(p for p in result["phase_log"] if p["phase"] == "b")
    assert "x" in log_b["consumed"]
    assert log_b["status"] == "completed"
    assert "z" in result["artifacts"]


def test_run_records_subagent_and_components():
    eng = WorkflowEngine()
    result = eng.run("prp", context={"idea": "x"})
    create_plan = next(
        p for p in result["phase_log"] if p["phase"] == "create_plan"
    )
    assert create_plan["uses_sub_agent"] is True
    assert "rag" in create_plan["context_components"]


def test_run_is_deterministic():
    eng = WorkflowEngine()
    r1 = eng.run("prp", context={"idea": "x"})
    r2 = eng.run("prp", context={"idea": "x"})
    assert r1["phase_log"] == r2["phase_log"]


def test_run_does_not_mutate_input_context():
    eng = WorkflowEngine()
    ctx = {"idea": "x"}
    eng.run("three-step", context=ctx)
    assert ctx == {"idea": "x"}


def test_run_strict_rejects_invalid():
    eng = WorkflowEngine()
    eng.register_template(
        WorkflowTemplate(
            name="bad",
            phases=[
                _phase("a", inputs=["idea"], outputs=["x"]),
                _phase("b", inputs=["missing"], outputs=["y"]),
            ],
        )
    )
    with pytest.raises(WorkflowError):
        eng.run("bad", context={"idea": "x"})


def test_run_non_strict_allows_degraded():
    eng = WorkflowEngine()
    eng.register_template(
        WorkflowTemplate(
            name="bad2",
            phases=[_phase("a", inputs=["missing"], outputs=["x"])],
        )
    )
    result = eng.run("bad2", context={}, strict=False)
    assert result["phase_log"][0]["status"] == "degraded"
    assert "missing" in result["phase_log"][0]["missing_inputs"]


def test_run_result_json_safe():
    eng = WorkflowEngine()
    result = eng.run("prp", context={"idea": "x"})
    json.dumps(result)  # should not raise


def test_describe_returns_dict():
    eng = WorkflowEngine()
    d = eng.describe("prp")
    assert d["name"] == "prp"
    assert d["framework"] == "prp"


# ── serialize / deserialize to file (tmp_path) ───────────────────────────────
def test_template_file_roundtrip(tmp_path: Path):
    eng = WorkflowEngine()
    t = eng.get_template("prp")
    fp = tmp_path / "prp.json"
    fp.write_text(json.dumps(t.to_dict()))
    loaded = WorkflowTemplate.from_dict(json.loads(fp.read_text()))
    assert loaded.name == t.name
    assert loaded.phase_names() == t.phase_names()
    assert loaded.phases == t.phases


# ── module lifecycle ──────────────────────────────────────────────────────────
async def test_module_initialize_healthy():
    mod = create_composable_workflow_engine_module()
    await mod.initialize()
    assert mod.status == HealthStatus.HEALTHY


async def test_module_health_check():
    mod = create_composable_workflow_engine_module()
    await mod.initialize()
    assert await mod.health_check() == HealthStatus.HEALTHY


async def test_module_bad_default_template_unhealthy():
    mod = create_composable_workflow_engine_module({"default_template": "nope"})
    with pytest.raises(WorkflowError):
        await mod.initialize()
    assert mod.status == HealthStatus.UNHEALTHY


async def test_module_shutdown():
    mod = create_composable_workflow_engine_module()
    await mod.initialize()
    await mod.shutdown()
    assert mod.status == HealthStatus.STOPPING


async def test_module_facade_all_templates():
    mod = create_composable_workflow_engine_module()
    await mod.initialize()
    assert "prp" in mod.all_templates()


async def test_module_facade_run():
    mod = create_composable_workflow_engine_module()
    await mod.initialize()
    result = mod.run("three-step", context={"idea": "x"})
    assert result["phase_count"] == 3


async def test_module_facade_compose_and_run():
    mod = create_composable_workflow_engine_module()
    await mod.initialize()
    mod.compose(
        "mine",
        phases=[
            _phase("r", inputs=["idea"], outputs=["ctx"]),
            _phase("b", inputs=["ctx"], outputs=["code"]),
        ],
    )
    result = mod.run("mine", context={"idea": "x"})
    assert [p["phase"] for p in result["phase_log"]] == ["r", "b"]


async def test_module_facade_validate():
    mod = create_composable_workflow_engine_module()
    await mod.initialize()
    res = mod.validate_template(mod.get_template("prp"))
    assert res.valid


def test_module_event_bus_optional():
    # publishing without a bus must not raise
    mod = ComposableWorkflowEngineModule()
    mod._publish("x.y", {"a": 1})


def test_module_set_event_bus_captures():
    class Bus:
        def __init__(self):
            self.events = []

        def publish(self, event):
            self.events.append(event)

    bus = Bus()
    mod = ComposableWorkflowEngineModule()
    mod.set_event_bus(bus)
    import asyncio

    asyncio.run(mod.initialize())
    mod.run("prp", context={"idea": "x"})
    assert len(bus.events) >= 1
