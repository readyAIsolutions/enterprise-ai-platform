"""Tests for the video_as_code enterprise module.

Covers: spec parse/validate, tightness scoring monotonicity and edge cases,
hallucination-risk being inverse to tightness, scene breakdown, assembly
manifests, deterministic stub generation, the graceful-degrading real
generator, the module factory, and the initialize/health/shutdown lifecycle.

Network-free: all generation is deterministic/stubbed; no external services.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from enterprise.platform_kernel import EventBus, HealthStatus, ModuleRegistry
from enterprise.modules import video_as_code as mod
from enterprise.modules.video_as_code.video_as_code import (
    AssemblyManifest,
    Generator,
    GenerationError,
    PipelineRunner,
    PipelineResult,
    RealGenerator,
    Scene,
    SceneRender,
    SpecValidationReport,
    StubGenerator,
    VideoSpec,
    hallucination_risk_estimate,
    hallucination_risk_label,
    parse_spec_markdown,
    run_pipeline,
    run_pipeline_from_dict,
    spec_from_dict,
    spec_to_dict,
    tightness_score,
    validate_spec,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def make_tight_spec() -> VideoSpec:
    """A spec fully filled in — the 'directing at every beat' ideal."""
    return VideoSpec(
        title="Tightness Demo",
        thesis="Tight specs reduce hallucination.",
        arc="Introduce -> explain -> example -> conclusion.",
        scenes=[
            Scene(
                scene_id="scene_1",
                description="Open on a spinning hexagon over a dark grid.",
                timing_seconds=12.0,
                visual_elements=["dark grid background", "spinning hexagon"],
                emphasis="The hexagon must spin slowly.",
                background_notes="Keep hexagon muted; no text yet.",
                script_lines=["Hello, and welcome to video as code."],
            ),
            Scene(
                scene_id="scene_2",
                description="Counting numbers flip on the right, text slides in left.",
                timing_seconds=9.0,
                visual_elements=["counting numbers", "sweeping text", "fade transition"],
                emphasis="Numbers count up fast then slow at the end.",
                background_notes="Background stays a low-contrast gradient.",
                script_lines=["The hard work is the spec, not the code."],
            ),
        ],
        style_guide={"palette": "dark + accent cyan", "minimal_text": "true"},
        component_registry=["TextComponent", "SceneContainer", "CountingNumbersEffect"],
    )


def make_loose_spec() -> VideoSpec:
    """A sparse spec missing per-scene detail, timing and emphasis."""
    return VideoSpec(
        title="Loose Demo",
        thesis="",
        arc="",
        scenes=[
            Scene(scene_id="scene_1", description="Some animation."),
            Scene(scene_id="scene_2"),
        ],
    )


# ---------------------------------------------------------------------------
# Spec parsing
# ---------------------------------------------------------------------------


def test_parse_spec_markdown_basic():
    md = """# My Video Brief

Thesis: AI animation is software engineering.
Arc: setup -> build -> payoff.

## Scene 1
Description: An orbit diagram rotates into place.
Emphasis: The orbit must rotate gently.
Background: Keep background flat and dark.
Timing: 12 seconds
Visuals:
- orbiting diagram
- soft glow
Script:
- Let's talk about video as code.

## Scene 2
Description: Counting numbers replace the diagram.
Timing: 0:07
"""
    spec = parse_spec_markdown(md)
    assert spec.title == "My Video Brief"
    assert spec.thesis == "AI animation is software engineering."
    assert spec.arc == "setup -> build -> payoff."
    assert len(spec.scenes) == 2
    s1 = spec.scenes[0]
    assert s1.scene_id == "scene_1"
    assert s1.description.startswith("An orbit diagram")
    assert s1.timing_seconds == 12.0
    assert s1.emphasis != ""
    assert s1.background_notes != ""
    assert "orbiting diagram" in s1.visual_elements
    assert s1.script_lines == ["Let's talk about video as code."]
    assert spec.scenes[1].timing_seconds == 7.0  # "0:07" -> 7s


def test_parse_spec_markdown_timing_variants():
    assert parse_spec_markdown("## S\nTiming: 12s").scenes[0].timing_seconds == 12.0
    assert parse_spec_markdown("## S\nTiming: 12").scenes[0].timing_seconds == 12.0
    assert parse_spec_markdown("## S\nTiming: 1:30").scenes[0].timing_seconds == 90.0
    assert parse_spec_markdown("## S\nTiming: n/a").scenes[0].timing_seconds is None


def test_spec_to_dict_roundtrip():
    spec = make_tight_spec()
    data = spec_to_dict(spec)
    again = spec_from_dict(data)
    assert again.title == spec.title
    assert again.thesis == spec.thesis
    assert [s.scene_id for s in again.scenes] == ["scene_1", "scene_2"]
    assert again.scenes[0].timing_seconds == 12.0
    assert again.component_registry == spec.component_registry


def test_spec_from_dict_invalid_raises():
    with pytest.raises(ValueError):
        spec_from_dict("not-a-dict")
    with pytest.raises(ValueError):
        spec_from_dict({"scenes": [42]})


def test_spec_to_dict_json_serializable():
    data = spec_to_dict(make_tight_spec())
    json.dumps(data)  # must not raise


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_validate_tight_spec_has_no_errors():
    report = validate_spec(make_tight_spec())
    assert isinstance(report, SpecValidationReport)
    assert report.valid is True
    assert report.errors == []


def test_validate_loose_spec_warns_on_missing_and_loose_fields():
    report = validate_spec(make_loose_spec())
    assert report.valid is False
    assert any("thesis" in e for e in report.errors)
    assert any("arc" in e for e in report.errors)
    assert "scene_2.emphasis" in report.missing_fields
    assert "scene_2.timing_seconds" in report.missing_fields
    assert "scene_2.visual_elements" in report.loose_fields


def test_validate_empty_spec_reports_no_scenes():
    report = validate_spec(VideoSpec(title="x", thesis="y", arc="z"))
    assert report.valid is False
    assert any("no scenes" in e for e in report.errors)


# ---------------------------------------------------------------------------
# Tightness scoring
# ---------------------------------------------------------------------------


def test_tightness_monotonic_tight_beats_loose():
    tight = tightness_score(make_tight_spec())
    loose = tightness_score(make_loose_spec())
    assert tight > loose


def test_tightness_tight_spec_scores_high():
    assert tightness_score(make_tight_spec()) >= 0.95


def test_tightness_empty_spec_scores_low():
    assert tightness_score(VideoSpec()) < 0.3


def test_tightness_requires_videospec():
    with pytest.raises(TypeError):
        tightness_score({"not": "a spec"})  # type: ignore[arg-type]


def test_tightness_bounds():
    for spec in (make_tight_spec(), make_loose_spec(), VideoSpec()):
        assert 0.0 <= tightness_score(spec) <= 1.0


def test_tightness_improves_with_timing_emphasis_script():
    base = VideoSpec(title="t", thesis="th", arc="a", scenes=[Scene(scene_id="s1")])
    partial = tightness_score(base)
    base.scenes[0].timing_seconds = 5.0
    base.scenes[0].emphasis = "land the beat"
    base.scenes[0].visual_elements = ["a dot"]
    improved = tightness_score(base)
    assert improved > partial


# ---------------------------------------------------------------------------
# Hallucination risk
# ---------------------------------------------------------------------------


def test_risk_inverse_to_tightness():
    # Implements the transcript claim: tighter spec -> less hallucination.
    for tight in (0.0, 0.25, 0.5, 0.75, 1.0):
        risk = hallucination_risk_estimate(tight)
        assert risk == pytest.approx(1.0 - tight)


def test_risk_labels():
    assert hallucination_risk_label(0.0) == "LOW"
    assert hallucination_risk_label(0.25) == "LOW"
    assert hallucination_risk_label(0.5) == "MEDIUM"
    assert hallucination_risk_label(0.75) == "HIGH"
    assert hallucination_risk_label(1.0) == "HIGH"


def test_risk_clamped_to_unit_interval():
    # Negative/oversized tightness is clamped to [0, 1] first; risk is inverse.
    assert hallucination_risk_estimate(-0.5) == 1.0  # clamp(-0.5)=0 -> risk 1.0
    assert hallucination_risk_estimate(1.5) == 0.0  # clamp(1.5)=1 -> risk 0.0
    for tight in (-1.0, 0.33, 2.5):
        assert 0.0 <= hallucination_risk_estimate(tight) <= 1.0


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def test_stub_generator_deterministic():
    spec = make_tight_spec()
    g = StubGenerator()
    first = g.generate(spec)
    second = g.generate(spec)
    assert first == second  # byte-for-byte deterministic
    assert all(r.ok for r in first)


def test_stub_generator_component_names():
    g = StubGenerator()
    render = g.generate_scene(Scene(scene_id="scene_1"))
    assert render.component_name == "Scene1Component"


def test_real_generator_degrades_gracefully_when_no_tooling():
    g = RealGenerator()  # network-free: no tooling attached
    renders = g.generate(make_tight_spec())
    assert len(renders) == 2
    assert all(r.ok is False for r in renders)
    assert "no generation tooling" in renders[0].note


def test_real_generator_delegates_to_injected_tooling():
    g = RealGenerator(tooling=lambda scene: SceneRender(scene_id=scene.scene_id, component_name="X"))
    render = g.generate_scene(Scene(scene_id="scene_1"))
    assert render.ok is True
    assert render.component_name == "X"


def test_real_generator_tooling_exception_degrades(caplog):
    def boom(_scene):
        raise RuntimeError("downstream outage")

    g = RealGenerator(tooling=boom)
    render = g.generate_scene(Scene(scene_id="scene_1"))
    assert render.ok is False
    assert "downstream outage" in render.note


def test_stub_and_real_are_generators():
    assert isinstance(StubGenerator(), Generator)
    assert isinstance(RealGenerator(), Generator)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def test_pipeline_assembles_manifest():
    spec = make_tight_spec()
    runner = PipelineRunner()
    result = runner.run(spec, source="brief.md")
    assert isinstance(result, PipelineResult)
    assert result.ok is True
    m = result.manifest
    assert isinstance(m, AssemblyManifest)
    assert m.spec_title == "Tightness Demo"
    assert m.total_scenes == 2
    assert m.total_duration_seconds == 21.0  # 12 + 9
    assert m.risk_label == hallucination_risk_label(m.hallucination_risk)
    assert m.hallucination_risk == pytest.approx(1.0 - m.tightness)
    assert len(m.renders) == 2
    assert any("tightness scored" in s for s in m.stages)


def test_pipeline_writes_manifest_file(tmp_path):
    result = run_pipeline(make_tight_spec(), output_dir=tmp_path)
    manifest_file = tmp_path / "manifest.json"
    assert manifest_file.exists()
    assert result.artifact_path == str(manifest_file)
    data = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert data["spec_title"] == "Tightness Demo"
    assert data["total_scenes"] == 2
    assert data["tightness"] == result.manifest.tightness


def test_pipeline_validate_failure_raises_generation_error():
    with pytest.raises(GenerationError):
        PipelineRunner().run(make_loose_spec())
    # Disabling validation lets a loose spec run through.
    result = PipelineRunner().run(make_loose_spec(), validate=False)
    assert result.manifest.tightness < 0.5


def test_pipeline_from_dict():
    data = spec_to_dict(make_tight_spec())
    result = run_pipeline_from_dict(data)
    assert result.manifest.total_scenes == 2
    assert result.manifest.tightness >= 0.95


def test_assembly_manifest_to_dict_serializable():
    m = PipelineRunner().run(make_tight_spec()).manifest
    json.dumps(m.to_dict())


def test_total_duration_and_scene_count():
    assert total_duration_spec(make_tight_spec()) == 21.0
    assert scene_count_spec(make_tight_spec()) == 2


# ---------------------------------------------------------------------------
# Module lifecycle / factory / registration (network-free)
# ---------------------------------------------------------------------------

MODULE_NAME = "video_as_code"


def test_module_registers_with_kernel():
    assert hasattr(mod, "VideoAsCodeModule")
    cls = mod.VideoAsCodeModule
    assert cls._meta_name == MODULE_NAME
    assert cls._meta_version == "1.0.0"


def test_discovery_binds_module_class():
    reg = ModuleRegistry()
    reg.discover()
    record = reg.get_record(MODULE_NAME)
    assert record is not None
    assert record.module_class is not None


def test_factory_returns_module():
    inst = mod.create_video_as_code_module({})
    assert isinstance(inst, mod.VideoAsCodeModule)
    assert inst.name == MODULE_NAME
    assert inst.module_id


def test_factory_applies_config_defaults():
    inst = mod.create_video_as_code_module({})
    assert inst.config.get("generator") == "stub"
    assert inst.config.get("publish_events") is True


def test_factory_wires_real_generator():
    inst = mod.create_video_as_code_module({"generator": "real"})
    assert inst.config.get("generator") == "real"


async def test_initialize_sets_healthy():
    inst = mod.create_video_as_code_module({})
    await inst.initialize()
    assert inst.status == HealthStatus.HEALTHY
    assert inst.runner is not None
    await inst.shutdown()


async def test_health_check_returns_status():
    inst = mod.create_video_as_code_module({})
    await inst.initialize()
    status = await inst.health_check()
    assert status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)
    await inst.shutdown()


async def test_shutdown_clears_runner():
    inst = mod.create_video_as_code_module({})
    await inst.initialize()
    assert inst.runner is not None
    await inst.shutdown()
    assert inst.runner is None


async def test_health_before_initialize_is_unknown():
    inst = mod.create_video_as_code_module({})
    await inst.initialize()
    await inst.shutdown()
    with pytest.MonkeyPatch.context() as mp:
        inst2 = mod.create_video_as_code_module({})
        # Simulate uninitialized module by clearing runner.
        inst2._runner = None  # type: ignore[attr-defined]
        assert await inst2.health_check() == HealthStatus.UNKNOWN


async def test_no_event_bus_does_not_crash_publish():
    inst = mod.create_video_as_code_module({})
    assert inst.event_bus is None
    await inst.initialize()
    result = await inst.run_pipeline(make_tight_spec())
    assert result.ok is True
    await inst.shutdown()


async def test_set_event_bus_and_publish_emits_event():
    inst = mod.create_video_as_code_module({"publish_events": True})
    # Synchronous dispatch so the published event is delivered synchronously.
    bus = EventBus({"async_dispatch": False})
    received = []
    bus.subscribe("video_as_code.pipeline.ran")(received.append)
    inst.set_event_bus(bus)
    await inst.initialize()
    await inst.run_pipeline(make_tight_spec())
    assert len(received) == 1
    event = received[0]
    assert event.topic == "video_as_code.pipeline.ran"
    assert event.payload["spec_title"] == "Tightness Demo"
    await inst.shutdown()


# ---------------------------------------------------------------------------
# Transcript-grounded constants
# ---------------------------------------------------------------------------


def test_transcript_constants_present():
    assert mod.TIGHT_BRIEF_QUOTE == "Give me the freedom of a tight brief."
    assert len(mod.VIDEO_AS_CODE_STACK) == 4
    assert mod.VIDEO_AS_CODE_STACK[0] == "spec (markdown brief)"
    assert "coding agent" in mod.VIDEO_AS_CODE_STACK[1]
    assert "Claude Code" in mod.VIDEO_AS_CODE_STACK[1]
    assert "Remotion" in mod.VIDEO_AS_CODE_STACK[2]
    assert "Cap Cut" in mod.VIDEO_AS_CODE_STACK[3]
    assert mod.LOOSE_SPEC_CLAIM


# small local helpers re-exported names (kept explicit for clarity)
def total_duration_spec(spec):
    from enterprise.modules.video_as_code import total_duration

    return total_duration(spec)


def scene_count_spec(spec):
    from enterprise.modules.video_as_code import scene_count

    return scene_count(spec)