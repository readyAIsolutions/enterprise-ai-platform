"""Tests for the Artifact Pipeline module (JEVanClief creative-works transcript)."""
from __future__ import annotations

import pytest

from enterprise.modules.artifact_pipeline import (
    ArtifactNotFoundError,
    ArtifactPipeline,
    ArtifactPipelineModule,
    ArtifactType,
    DependencyError,
    DuplicateArtifactError,
    InvalidTransitionError,
    Stage,
    WorkflowGraph,
    create_artifact_pipeline_module,
)
from enterprise.modules.artifact_pipeline.artifact_pipeline import (
    JsonCatalogStore,
    SqliteCatalogStore,
    id_for_path,
    infer_type,
)
from enterprise.platform_kernel import HealthStatus


# ---------------------------------------------------------------------------
# WorkflowGraph: the script -> animation pipeline
# ---------------------------------------------------------------------------

def test_valid_script_to_animation_shortcut():
    g = WorkflowGraph()
    assert g.can_transition(Stage.SCRIPT, Stage.ANIMATION)
    assert g.can_transition(Stage.SCRIPT, Stage.STORYBOARD)
    assert g.can_transition(Stage.STORYBOARD, Stage.ANIMATION)
    assert g.can_transition(Stage.ANIMATION, Stage.RENDER)
    # render is terminal
    assert g.next_stages(Stage.RENDER) == []


def test_invalid_transition_raises():
    g = WorkflowGraph()
    assert not g.can_transition(Stage.RENDER, Stage.ANIMATION)
    with pytest.raises(InvalidTransitionError):
        g.validate_transition(Stage.RENDER, Stage.ANIMATION)
    # you cannot jump storyboard straight to render (must hit animation first)
    assert not g.can_transition(Stage.STORYBOARD, Stage.RENDER)


# ---------------------------------------------------------------------------
# Type inference
# ---------------------------------------------------------------------------

def test_infer_type_by_extension(tmp_path):
    assert infer_type(tmp_path / "script.md", {}) is ArtifactType.SCRIPT
    assert infer_type(tmp_path / "board.json", {}) is ArtifactType.STORYBOARD
    assert infer_type(tmp_path / "clip.anim", {}) is ArtifactType.ANIMATION
    assert infer_type(tmp_path / "film.mp4", {}) is ArtifactType.RENDER
    # unknown extension falls back to script (a written work)
    assert infer_type(tmp_path / "notes.abc", {}) is ArtifactType.SCRIPT


# ---------------------------------------------------------------------------
# ArtifactPipeline: catalog & organize
# ---------------------------------------------------------------------------

def test_register_artifact_auto_detects_type_and_stage(tmp_path):
    p = tmp_path / "my_script.md"
    p.write_text("# Pilot episode\n")
    pipe = ArtifactPipeline()
    art = pipe.add(str(p), project="ai_doc")
    assert pipe.registry.get(art.id).path == str(p)
    assert art.type is ArtifactType.SCRIPT
    assert art.stage is Stage.SCRIPT
    assert art.project == "ai_doc"


def test_duplicate_artifact_raises(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("x")
    pipe = ArtifactPipeline()
    pipe.add(str(p))
    with pytest.raises(DuplicateArtifactError):
        pipe.add(str(p))


def test_unknown_artifact_raises():
    pipe = ArtifactPipeline()
    with pytest.raises(ArtifactNotFoundError):
        pipe.get("nope")


# ---------------------------------------------------------------------------
# derive: turn a script into a full animation/render (the transcript workflow)
# ---------------------------------------------------------------------------

def test_derive_script_to_animation_tracks_dependency(tmp_path):
    script = tmp_path / "episode.md"
    script.write_text("# Episode\n")
    anim = tmp_path / "episode.anim"
    render = tmp_path / "episode.mp4"

    pipe = ArtifactPipeline()
    s = pipe.add(str(script), project="series")
    a = pipe.derive(s.id, str(anim))          # script -> animation
    assert a.stage is Stage.ANIMATION
    assert s.id in a.dependencies
    r = pipe.derive(a.id, str(render))        # animation -> render
    assert r.stage is Stage.RENDER
    assert a.id in r.dependencies

    # dependency chain: render depends on animation depends on script
    chain = {x.name for x in pipe.dependencies_of(r.id)}
    assert "episode" in chain
    assert s.id in {x.id for x in pipe.dependencies_of(a.id)}


def test_derive_invalid_when_source_is_downstream(tmp_path):
    script = tmp_path / "s.md"
    script.write_text("x")
    pipe = ArtifactPipeline()
    s = pipe.add(str(script))
    # a render cannot be derived directly from a fresh script via this edge set
    with pytest.raises(InvalidTransitionError):
        pipe.derive(s.id, str(tmp_path / "o.mp4"))


# ---------------------------------------------------------------------------
# dependency validation
# ---------------------------------------------------------------------------

def test_dependency_must_be_strictly_earlier(tmp_path):
    script = tmp_path / "s.md"
    script.write_text("x")
    render = tmp_path / "r.mp4"
    pipe = ArtifactPipeline()
    s = pipe.add(str(script))
    r = pipe.add(str(render))
    # script -> render is a valid dependency direction
    pipe.add_dependency(r.id, [s.id])
    assert s.id in pipe.registry.get(r.id).dependencies
    # but a script cannot depend on a render (render is downstream)
    with pytest.raises(DependencyError):
        pipe.add_dependency(s.id, [r.id])


def test_self_dependency_rejected(tmp_path):
    p = tmp_path / "s.md"
    p.write_text("x")
    pipe = ArtifactPipeline()
    art = pipe.add(str(p))
    with pytest.raises(DependencyError):
        pipe.add_dependency(art.id, [art.id])


# ---------------------------------------------------------------------------
# advance + readiness
# ---------------------------------------------------------------------------

def test_advance_valid_and_invalid(tmp_path):
    p = tmp_path / "s.md"
    p.write_text("x")
    pipe = ArtifactPipeline()
    art = pipe.add(str(p))
    assert pipe.can_advance(art.id) == [Stage.STORYBOARD, Stage.ANIMATION]
    pipe.advance(art.id, Stage.ANIMATION)
    assert pipe.registry.get(art.id).stage is Stage.ANIMATION
    with pytest.raises(InvalidTransitionError):
        pipe.advance(art.id, Stage.SCRIPT)  # cannot go backwards
    assert pipe.readiness(art.id)["next"] == ["render"]


# ---------------------------------------------------------------------------
# navigation & grouping
# ---------------------------------------------------------------------------

def test_scan_and_group_by_project(tmp_path):
    proj = tmp_path / "series_one"
    (proj / "shots").mkdir(parents=True)
    (proj / "episode.md").write_text("ep")
    (proj / "episode.anim").write_text("anim")
    (proj / "episode.mp4").write_text("video")
    pipe = ArtifactPipeline()
    added = pipe.scan(str(proj))
    assert len(added) == 3

    groups = pipe.group_by("project")
    assert "series_one" in groups
    # all_renders shows finished outputs "in one place"
    assert {a.name for a in pipe.all_renders()} == {"episode"}


def test_browse_by_type(tmp_path):
    (tmp_path / "a.md").write_text("x")
    (tmp_path / "b.mp4").write_text("v")
    pipe = ArtifactPipeline()
    pipe.scan(str(tmp_path))
    scripts = pipe.browse(type_="script")
    renders = pipe.browse(type_="render")
    assert len(scripts) == 1
    assert len(renders) == 1
    assert scripts[0].name == "a"
    assert renders[0].name == "b"


# ---------------------------------------------------------------------------
# persistence (no network)
# ---------------------------------------------------------------------------

def test_json_store_roundtrip(tmp_path):
    store = JsonCatalogStore(str(tmp_path / "cat.json"))
    pipe = ArtifactPipeline(store=store)
    (tmp_path / "s.md").write_text("x")
    (tmp_path / "r.mp4").write_text("v")
    pipe.add(str(tmp_path / "s.md"), project="p1")
    pipe.add(str(tmp_path / "r.mp4"), project="p2")
    pipe.persist()

    loaded = ArtifactPipeline(store=JsonCatalogStore(str(tmp_path / "cat.json")))
    n = loaded.load_from_store()
    assert n == 2
    assert {a.name for a in loaded.all()} == {"s", "r"}


def test_sqlite_store_roundtrip(tmp_path):
    store = SqliteCatalogStore(str(tmp_path / "cat.db"))
    pipe = ArtifactPipeline(store=store)
    (tmp_path / "s.md").write_text("x")
    pipe.add(str(tmp_path / "s.md"), project="p")
    pipe.persist()

    loaded = ArtifactPipeline(store=SqliteCatalogStore(str(tmp_path / "cat.db")))
    n = loaded.load_from_store()
    assert n == 1
    assert loaded.all()[0].name == "s"
    store.close()


# ---------------------------------------------------------------------------
# Kernel module lifecycle
# ---------------------------------------------------------------------------

async def test_module_lifecycle():
    mod = create_artifact_pipeline_module()
    assert mod.name == "artifact_pipeline"
    await mod.initialize()
    assert await mod.health_check() is HealthStatus.HEALTHY
    assert mod.pipeline is not None
    await mod.shutdown()


async def test_module_set_event_bus_publishes(tmp_path):
    from enterprise.platform_kernel import EventBus

    # sync dispatch so the handler runs before we assert on it
    bus = EventBus(config={"async_dispatch": False})
    received = []

    @bus.subscribe("artifact_pipeline.added")
    def _on_added(event):
        received.append(event)

    mod = create_artifact_pipeline_module()
    mod.set_event_bus(bus)
    await mod.initialize()
    (tmp_path / "x.md").write_text("x")
    mod.add(str(tmp_path / "x.md"), project="p")
    assert any(e.topic == "artifact_pipeline.added" for e in received)
    await mod.shutdown()


async def test_module_health_without_init_is_unhealthy():
    mod = create_artifact_pipeline_module()
    assert await mod.health_check() is HealthStatus.UNHEALTHY
