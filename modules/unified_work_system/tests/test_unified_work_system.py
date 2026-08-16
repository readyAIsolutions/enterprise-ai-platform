"""Tests for the Unified Work System module.

Covers the artifact-centered WorkSystem, the three lenses, the lens-consistency
check (do the lenses tell the same story?), and the external-vs-human memory
model with position/link/content addressing.

Run: python3 -m pytest modules/unified_work_system/tests -q
"""

from __future__ import annotations

import pytest

from enterprise.platform_kernel import HealthStatus

from enterprise.modules.unified_work_system import (
    Artifact,
    BusinessLens,
    COMMON_STORY_DIMENSIONS,
    ConsistencyReport,
    ContextResolver,
    CreativeLens,
    HumanMemory,
    MemoryItem,
    MemoryStore,
    TechnicalLens,
    WorkSystem,
    UnifiedWorkSystemModule,
    build_artifact,
    create_unified_work_system_module,
)
from enterprise.modules.unified_work_system.unified_work_system import (
    CONTENT_ADDRESSED,
    LINK_ADDRESSED,
    POSITION_ADDRESSED,
)


# ---------------------------------------------------------------------------
# Artifact + lenses
# ---------------------------------------------------------------------------

def test_artifact_holds_shared_facts() -> None:
    artifact = build_artifact(
        "NLP Logics season one",
        client="NLP Logics",
        kind="video_project",
        creative_audience="marketing leads",
        stack=["claude", "ffmpeg"],
    )
    assert artifact.name == "NLP Logics season one"
    assert artifact.client == "NLP Logics"
    assert artifact.facts["creative_audience"] == "marketing leads"
    assert artifact.facts["stack"] == ["claude", "ffmpeg"]


def test_creative_lens_derives_structured_facts() -> None:
    artifact = build_artifact(
        "brand deck",
        creative_audience="marketing leads",
        creative_metric="watch_time",
        impact="build trust",
        mood="calm, confident",
        brand_voice="studio voice",
        taste_guardian="human",
    )
    view = CreativeLens().derive(artifact)
    assert view.lens == "creative"
    assert view.story["audience"] == "marketing leads"
    assert view.story["primary_metric"] == "watch_time"
    assert view.specifics["impact"] == "build trust"
    assert view.specifics["taste_guardian"] == "human"


def test_technical_lens_derives_stack_tasks() -> None:
    artifact = build_artifact(
        "pipeline",
        technical_subject="render pipeline",
        technical_success="export ready",
        stack=["claude", "ffmpeg"],
        tasks=["resize exports", "rename files", "match color"],
        namespace="studio/nlplogics",
    )
    view = TechnicalLens().derive(artifact)
    assert view.lens == "technical"
    assert view.story["subject"] == "render pipeline"
    assert view.story["success_definition"] == "export ready"
    assert view.specifics["stack"] == ["claude", "ffmpeg"]
    assert "rename files" in view.specifics["tasks"]
    assert view.specifics["namespace"] == "studio/nlplogics"


def test_business_lens_derives_value_revenue() -> None:
    artifact = build_artifact(
        "deliverable",
        business_audience="c-suite buyers",
        business_metric="retainer_renewal",
        value="system not videos",
        cost="low",
        market="marketing agencies",
        revenue="retainer fee",
        business_model="advisor",
    )
    view = BusinessLens().derive(artifact)
    assert view.lens == "business"
    assert view.story["audience"] == "c-suite buyers"
    assert view.specifics["value"] == "system not videos"
    assert view.specifics["business_model"] == "advisor"


# ---------------------------------------------------------------------------
# WorkSystem: artifact at the center, rendered through every lens at once
# ---------------------------------------------------------------------------

def test_work_system_renders_artifact_through_three_lenses() -> None:
    ws = WorkSystem(build_artifact("one project", creative_subject="story"))
    views = ws.render()
    assert set(views) == {"creative", "technical", "business"}
    assert all(isinstance(v, type(views["creative"])) for v in views.values())


def test_consistency_same_story_is_consistent() -> None:
    ws = WorkSystem(build_artifact(
        "campaign",
        creative_subject="launch video",
        technical_subject="launch video",
        business_subject="launch video",
        creative_audience="leads",
        technical_audience="leads",
        business_audience="leads",
    ))
    report = ws.check_consistency()
    assert isinstance(report, ConsistencyReport)
    assert report.consistent is True
    assert report.agreements["subject"] == "launch video"
    assert report.agreements["audience"] == "leads"
    assert not report.disagreements


def test_consistency_detects_lens_disagreement() -> None:
    # The creative lens targets marketing leads; the business lens targets
    # C-suite buyers.  The lenses are NOT telling the same story.
    ws = WorkSystem(build_artifact(
        "campaign",
        creative_audience="marketing leads",
        technical_audience="marketing leads",
        business_audience="c-suite buyers",
    ))
    report = ws.check_consistency()
    assert report.consistent is False
    assert "audience" in report.disagreements
    assert report.disagreements["audience"]["creative"] == "marketing leads"
    assert report.disagreements["audience"]["business"] == "c-suite buyers"


def test_consistency_treats_list_values_order_insensitively() -> None:
    ws = WorkSystem(build_artifact(
        "project",
        technical_audience=["leads", "cfo"],
        business_audience=["cfo", "leads"],
    ))
    report = ws.check_consistency()
    # Same two audiences, different order -> still the same story.
    assert report.consistent is True
    assert report.agreements["audience"] == ["leads", "cfo"]


def test_consistency_marks_unstated_dimensions() -> None:
    ws = WorkSystem(build_artifact("project", creative_audience="leads"))
    report = ws.check_consistency()
    assert report.consistent is True  # no disagreements
    assert "audience" in report.unstated  # only one lens spoke


def test_add_custom_lens() -> None:
    class OpsLens(TechnicalLens):
        kind = "operations"

        specific_fields = ("ops_cost",)

    ws = WorkSystem(build_artifact("project", ops_cost="low"))
    ws.add_lens(OpsLens())
    views = ws.render()
    assert "operations" in views
    assert views["operations"].specifics["ops_cost"] == "low"


# ---------------------------------------------------------------------------
# Memory: external AI memory with three addressing modes + human context
# ---------------------------------------------------------------------------

def test_memory_store_position_cascade() -> None:
    store = MemoryStore()
    root = MemoryItem(content="brand voice: calm", namespace="root", priority=5)
    scene = MemoryItem(content="scene three", namespace="studio/nlplogics/scene3", priority=1)
    store.add(root)
    store.add(scene)

    items = store.cascade("studio/nlplogics/scene3")
    ids = [i.id for i in items]
    # Root rule cascades down to the nested scene file.
    assert root.id in ids
    assert scene.id in ids


def test_memory_store_content_addressed_retrieval() -> None:
    store = MemoryStore()
    deck = MemoryItem(content="brand deck type pairing color logic", priority=2)
    pipe = MemoryItem(content="brand deck render pipeline video exports", priority=1)
    store.add(deck)
    store.add(pipe)

    results = store.retrieve("brand deck video", mode=CONTENT_ADDRESSED)
    # Both items share some keywords with the query
    assert results and results[0].id == deck.id  # higher priority first
    assert pipe.id in [r.id for r in results]


def test_memory_store_link_addressed_retrieval() -> None:
    store = MemoryStore()
    a = MemoryItem(content="client", id="client")
    b = MemoryItem(content="project", id="project", links=["client"])
    c = MemoryItem(content="scene", id="scene", links=["project"])
    store.add(a)
    store.add(b)
    store.add(c)

    found = store.retrieve("", mode=LINK_ADDRESSED, seed="scene")
    ids = [i.id for i in found]
    assert "scene" in ids and "project" in ids and "client" in ids


def test_memory_contradiction_flagged() -> None:
    store = MemoryStore()
    store.add(MemoryItem(content="brand is blue", namespace="brand", subject="color"))
    store.add(MemoryItem(content="brand is red", namespace="brand", subject="color"))
    contradictions = store.contradictions()
    assert len(contradictions) == 1
    assert contradictions[0][0].content == "brand is blue"
    assert contradictions[0][1].content == "brand is red"


def test_memory_duplicate_content_not_contradiction() -> None:
    store = MemoryStore()
    store.add(MemoryItem(content="brand is blue", namespace="brand", subject="color"))
    store.add(MemoryItem(content="brand is blue", namespace="brand", subject="color"))
    assert store.contradictions() == []


def test_human_memory_directs_external_retrieval() -> None:
    human = HumanMemory()
    human.remember("goal", "sell the system")
    human.decide("keep taste with the human")
    human.direct("video")

    store = MemoryStore()
    store.add(MemoryItem(content="video export settings", priority=1))
    store.add(MemoryItem(content="unrelated accounting notes", priority=2))

    ranked = ContextResolver.combine(human, store, "video export")
    assert ranked and ranked[0].content == "video export settings"


# ---------------------------------------------------------------------------
# Module lifecycle + factory
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_module_initialize_health_shutdown() -> None:
    module = create_unified_work_system_module(
        {"artifact_name": "campaign", "facts": {"creative_audience": "leads"}}
    )
    assert isinstance(module, UnifiedWorkSystemModule)
    assert module.status in (HealthStatus.UNKNOWN, HealthStatus.STARTING)

    await module.initialize()
    assert module.status == HealthStatus.HEALTHY
    assert module.work_system is not None
    assert await module.health_check() == HealthStatus.HEALTHY

    report = module.check_consistency()
    assert isinstance(report, ConsistencyReport)

    await module.shutdown()
    assert module.work_system is None


@pytest.mark.asyncio
async def test_module_factory_seeds_memory() -> None:
    module = create_unified_work_system_module(
        {
            "artifact_name": "project",
            "seed_memory": [{"content": "brand is blue", "namespace": "brand"}],
        }
    )
    await module.initialize()
    assert len(module.work_system.memory.namespace_items("brand")) == 1


@pytest.mark.asyncio
async def test_module_set_event_bus_accepts_none() -> None:
    module = create_unified_work_system_module({"artifact_name": "x"})
    module.set_event_bus(None)  # must not raise; events skipped
    await module.initialize()
    assert module.work_system is not None
