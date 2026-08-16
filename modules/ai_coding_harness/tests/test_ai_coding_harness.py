"""Unit tests for the ai_coding_harness module (no network, no mocks of state)."""
from __future__ import annotations

from pathlib import Path

from enterprise.modules.ai_coding_harness import (
    AiCodingHarness,
    Artifact,
    ArtifactKind,
    ContextSpec,
    GenerationPlan,
    PipelineStage,
    ScaffoldSpec,
    create_ai_coding_harness,
    create_ai_coding_harness_module,
    default_context,
)


# --- context ---------------------------------------------------------------
def test_build_context_renders_read_paths_and_skills():
    ctx = ContextSpec(
        role="anim studio",
        read_paths=["src/svg/", "CLAUDE.md"],
        skills=["remotion"],
        notes="read first, then scaffold",
    )
    text = ctx.build()
    assert "anim studio" in text
    assert "src/svg/" in text
    assert "remotion" in text
    assert "read first, then scaffold" in text


def test_default_context_covers_workflows():
    ctx = default_context()
    assert "remotion" in ctx.skills
    assert "CLAUDE.md" in ctx.read_paths


# --- scaffolding ------------------------------------------------------------
def test_scaffold_creates_folders_and_claude_md(tmp_path: Path):
    harness = AiCodingHarness()
    spec = ScaffoldSpec(
        name="project",
        kind=ArtifactKind.ANIMATION,
        context=ContextSpec(role="render lab", read_paths=["scripts"]),
    )
    paths = harness.scaffold(spec, tmp_path)
    root = tmp_path / "project"
    assert (root / "scripts").is_dir()
    assert (root / "specs").is_dir()
    assert (root / "scenes").is_dir()
    claude = root / "CLAUDE.md"
    assert claude.is_file()
    assert "render lab" in claude.read_text(encoding="utf-8")
    assert root / "scripts" in paths


def test_scaffold_site_layout(tmp_path: Path):
    harness = AiCodingHarness()
    spec = ScaffoldSpec(name="mysite", kind=ArtifactKind.SITE)
    harness.scaffold(spec, tmp_path)
    assert (tmp_path / "mysite" / "pages").is_dir()
    assert (tmp_path / "mysite" / "public").is_dir()


# --- prompt -> artifact ------------------------------------------------------
def test_plan_builds_prompt_with_context():
    harness = AiCodingHarness()
    plan = harness.plan("make an SVG hero", ArtifactKind.SVG)
    assert isinstance(plan, GenerationPlan)
    assert "make an SVG hero" in plan.prompt_with_context()
    assert "CLAUDE.md" in plan.prompt_with_context()


def test_generate_svg_is_labeled_and_rooted():
    harness = AiCodingHarness()
    art = harness.generate(harness.plan("make a character", ArtifactKind.SVG))
    assert art.kind == ArtifactKind.SVG
    assert "<svg" in art.body and "</svg>" in art.body
    assert "aria-label" in art.body  # the labeling trick from izMBiWG3L24


def test_generate_site_is_html():
    harness = AiCodingHarness()
    art = harness.generate(harness.plan("client landing page", ArtifactKind.SITE))
    assert "<html" in art.body
    assert "<body" in art.body
    assert "client landing page" in art.body


# --- verification -------------------------------------------------------------
def test_verify_passed_artifact():
    harness = AiCodingHarness()
    art = harness.iterate(harness.generate(harness.plan("x", ArtifactKind.SVG)))
    res = harness.verify(art)
    assert res.passed is True
    assert res.checks["has_svg_root"] is True


def test_verify_rejects_empty():
    harness = AiCodingHarness()
    res = harness.verify(Artifact(kind=ArtifactKind.HTML, name="e", body=""))
    assert res.passed is False
    assert res.checks["nonempty"] is False


# --- iteration loop ------------------------------------------------------------
def test_iterate_bumps_revision_until_verified():
    harness = AiCodingHarness()
    plan = harness.plan("hero", ArtifactKind.SITE)
    first = harness.generate(plan)
    final = harness.iterate(first)
    assert final.revision >= first.revision
    assert harness.verify(final).passed is True


# --- pipeline ------------------------------------------------------------------
def test_run_stages_covers_all_stages_and_verifies():
    harness = AiCodingHarness()
    stages = harness.run_stages("a 30 minute script about the ocean")
    for stage in (
        PipelineStage.SCRIPT,
        PipelineStage.SPECIFICATION,
        PipelineStage.SCENES,
        PipelineStage.RENDER,
        PipelineStage.VERIFY,
    ):
        assert stage in stages
    assert all(s.kind == ArtifactKind.ANIMATION for s in stages.values())
    assert harness.verify(stages[PipelineStage.VERIFY]).passed is True


# --- facade ---------------------------------------------------------------------
def test_create_ai_coding_harness_builds_engine():
    h = create_ai_coding_harness({"max_iterations": 3})
    assert isinstance(h, AiCodingHarness)
    assert h.max_iterations == 3


# --- kernel module ---------------------------------------------------------------
async def test_module_initializes_healthy():
    m = create_ai_coding_harness_module({})
    assert m.name == "ai_coding_harness"
    assert m.version == "1.0.0"
    await m.initialize()
    assert m.engine is not None
    from enterprise.platform_kernel import HealthStatus
    assert await m.health_check() == HealthStatus.HEALTHY
    await m.shutdown()


async def test_module_health_unhealthy_before_init():
    from enterprise.platform_kernel import HealthStatus
    m = create_ai_coding_harness_module({})
    assert await m.health_check() == HealthStatus.UNHEALTHY
    await m.initialize()
    assert await m.health_check() == HealthStatus.HEALTHY


def test_module_registered_in_kernel():
    import enterprise.modules.ai_coding_harness  # noqa: F401  (triggers registration)
    from enterprise.platform_kernel import _MODULE_REGISTRY
    assert "ai_coding_harness" in _MODULE_REGISTRY
    assert _MODULE_REGISTRY["ai_coding_harness"] is not None