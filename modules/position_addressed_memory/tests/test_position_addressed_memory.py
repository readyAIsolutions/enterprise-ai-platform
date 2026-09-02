"""Tests for the Position-Addressed Memory module (JEVanClief transcript-grounded).

The transcript (hALln9wrrQo, "How I Run Creative, Software, and Business Work
as One System") teaches *folder-as-memory*: a root ``CLAUDE.md`` whose rules
cascade down, per-project ``Context.md`` layered on top, so "by the time Claude
reads the scene, it has already inherited the brand voice, the production
rules, the specific shot list." It contrasts position-, content- and
link-addressed memory. These tests exercise the cascade and all three
addressing modes deterministically.
"""
from __future__ import annotations

import asyncio

import pytest

from enterprise.modules.position_addressed_memory import (
    AddressingMode,
    ContentStore,
    ContextRule,
    ContextStack,
    LinkStore,
    MemoryAddressing,
    PathResolver,
    PositionAddressedMemoryModule,
    Precedence,
    create_position_addressed_memory_module,
    parse_markdown_context,
)
from enterprise.platform_kernel import HealthStatus


# ---------------------------------------------------------------------------
# Fixture: a folder-as-memory tree (transcript-style production project)
# ---------------------------------------------------------------------------

def _build_tree(root) -> dict[str, str]:
    """Create the transcript's production folder: root CLAUDE.md cascades down,
    project Context.md layers on top, and a per-scene convention doc sits next
    to the scene file. Returns {path: content} to write to disk."""
    files = {
        root / "CLAUDE.md": (
            "# Brand Voice\nenergetic, technical, confident\n"
            "# Production Rules\nPattern A pipeline; deliver by Friday\n"
            "# Tone\nconsistent with founder speaking\n"
        ),
        root / "video_projects" / "Context.md": (
            "# Client\nNLP Logics\n"
            "# Pattern A Pipeline\nscene-by-scene animation\n"
            "# Tone\nwarm and precise\n"
        ),
        root / "video_projects" / "nlp_logics" / "Context.md": (
            "# Client\nNLP Logics\n"
            "# Scene Conventions\neach scene 20s max\n"
        ),
        root / "video_projects" / "nlp_logics" / "scene_three.md": (
            "# Shot List\nopen on logo; zoom to founder; punchline cut\n"
            "# Script\nThis is scene three.\n"
        ),
    }
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return {str(p): c for p, c in files.items()}


# ---------------------------------------------------------------------------
# ContextRule + markdown parsing
# ---------------------------------------------------------------------------

def test_parse_markdown_context_headings_and_kv():
    rules = parse_markdown_context(
        "# Brand Voice\nenergetic, technical\n# Production Rules\nA pipeline\n"
        "# Client\nNLP Logics\n",
        path="/r/CLAUDE.md",
        source="CLAUDE.md",
        order=0,
    )
    assert {r.key for r in rules} == {"brand_voice", "production_rules", "client"}
    by_key = {r.key: r for r in rules}
    assert by_key["brand_voice"].value == "energetic, technical"
    assert by_key["client"].value == "NLP Logics"
    assert by_key["client"].source == "CLAUDE.md"
    assert by_key["client"].order == 0


def test_context_rule_serialization_roundtrip():
    rule = ContextRule(
        key="brand_voice",
        value="energetic",
        source="CLAUDE.md",
        path="/r/CLAUDE.md",
        order=0,
    )
    restored = ContextRule.from_dict(rule.to_dict())
    assert restored == rule


# ---------------------------------------------------------------------------
# ContextStack — the root->leaf cascade
# ---------------------------------------------------------------------------

def test_context_stack_inherits_root_claude_cascades_down(tmp_path):
    root = tmp_path / "prod"
    _build_tree(root)
    stack = ContextStack(str(root))
    scene = str(root / "video_projects" / "nlp_logics" / "scene_three.md")
    layers = stack.collect(scene)
    # root CLAUDE.md + two project Context.md layers + scene file, root -> leaf
    assert len(layers) == 4
    assert layers[0].rules[0].source == "CLAUDE.md"
    assert layers[0].rules[0].order == 0
    assert layers[2].rules[0].order == 2
    assert layers[3].rules[0].source == "scene_three.md"


def test_context_stack_cascades_brand_voice_and_production_rules(tmp_path):
    root = tmp_path / "prod"
    _build_tree(root)
    stack = ContextStack(str(root))
    scene = str(root / "video_projects" / "nlp_logics" / "scene_three.md")
    ctx = stack.resolve(scene)
    # root CLAUDE.md rules cascade down to the deep scene file
    assert ctx["production_rules"] == "Pattern A pipeline; deliver by Friday"
    # project Context.md layers on top of the root
    assert ctx["client"] == "NLP Logics"
    # scene's own convention doc is inherited too
    assert "shot_list" in ctx


def test_context_stack_deepest_wins_over_root(tmp_path):
    root = tmp_path / "prod"
    _build_tree(root)
    stack = ContextStack(str(root))
    scene = str(root / "video_projects" / "nlp_logics" / "scene_three.md")
    ctx = stack.resolve(scene)
    # "Tone" exists in both root CLAUDE.md and project Context.md.
    # DEEPEST precedence => the project's value layers on top.
    assert ctx["tone"] == "warm and precise"


def test_context_stack_shallowest_precedence_keeps_root_rule(tmp_path):
    root = tmp_path / "prod"
    _build_tree(root)
    stack = ContextStack(str(root), precedence=Precedence.SHALLOWEST)
    scene = str(root / "video_projects" / "nlp_logics" / "scene_three.md")
    ctx = stack.resolve(scene)
    # SHALLOWEST => the root CLAUDE.md "Tone" wins over the project layer.
    assert ctx["tone"] == "consistent with founder speaking"


def test_context_stack_rejects_path_outside_root(tmp_path):
    root = tmp_path / "prod"
    stack = ContextStack(str(root))
    with pytest.raises(ValueError):
        stack.collect(str(tmp_path / "elsewhere" / "file.md"))


# ---------------------------------------------------------------------------
# PathResolver — the path as a namespace
# ---------------------------------------------------------------------------

def test_path_resolver_namespaces_carry_meaning(tmp_path):
    root = tmp_path / "prod"
    _build_tree(root)
    resolver = PathResolver(str(root))
    scene = str(root / "video_projects" / "nlp_logics" / "scene_three.md")
    res = resolver.resolve(scene)
    # "The folder name is a namespace. The namespace carries meaning."
    assert res.namespaces == ("video_projects", "nlp_logics")
    assert res.filename == "scene_three.md"
    assert res.depth == 2
    assert resolver.namespace_path(scene) == "video_projects/nlp_logics"


def test_path_resolver_relative_and_is_within(tmp_path):
    root = tmp_path / "prod"
    resolver = PathResolver(str(root))
    inside = str(root / "a" / "b.md")
    assert resolver.is_within(inside)
    assert resolver.relative(inside).as_posix() == "a/b.md"


# ---------------------------------------------------------------------------
# Content-addressed store (SHA-256 digest)
# ---------------------------------------------------------------------------

def test_content_store_addresses_by_sha256_and_dedups():
    store = ContentStore()
    d1 = store.address("brand voice script")
    d2 = store.address("brand voice script")
    assert d1 == d2  # dedup
    assert len(store) == 1
    assert d1 == ContentStore.digest("brand voice script")
    hit = store.lookup(d1)
    assert hit.mode is AddressingMode.CONTENT
    assert hit.content == "brand voice script"


# ---------------------------------------------------------------------------
# Link-addressed store (wiki-style entity pages)
# ---------------------------------------------------------------------------

def test_link_store_defines_pages_and_flags_orphans():
    store = LinkStore()
    store.define("NLP Logics", "a machine learning company")
    store.reference("NLP Logics", "Client")
    store.reference("OrphanPage", "never defined anywhere")
    assert store.resolve("NLP Logics") == "a machine learning company"
    assert store.orphans() == ["OrphanPage"]


def test_link_store_flags_contradictions():
    store = LinkStore()
    store.reference("tone", "warm")
    store.reference("tone", "cold")
    contradictions = store.contradictions()
    assert len(contradictions) == 1
    name, targets = contradictions[0]
    assert name == "tone"
    assert targets == {"warm", "cold"}


# ---------------------------------------------------------------------------
# MemoryAddressing — deterministic resolver across all three modes
# ---------------------------------------------------------------------------

def test_deterministic_resolve_by_content_hash(tmp_path):
    root = tmp_path / "prod"
    _build_tree(root)
    mem = MemoryAddressing(str(root))
    digest = mem.store_content("founder voice lines")
    res = mem.resolve(digest)
    assert res.mode is AddressingMode.CONTENT
    assert res.hit.content == "founder voice lines"


def test_deterministic_resolve_by_position_inherits_context(tmp_path):
    root = tmp_path / "prod"
    _build_tree(root)
    mem = MemoryAddressing(str(root))
    scene = str(root / "video_projects" / "nlp_logics" / "scene_three.md")
    res = mem.resolve(scene)
    assert res.mode is AddressingMode.POSITION
    assert res.hit.namespaces == ("video_projects", "nlp_logics")
    # the path did all the routing: brand voice + production rules inherited
    assert res.hit.context["brand_voice"] == "energetic, technical, confident"
    assert res.hit.context["production_rules"] == "Pattern A pipeline; deliver by Friday"


def test_deterministic_resolve_by_link_name(tmp_path):
    root = tmp_path / "prod"
    mem = MemoryAddressing(str(root))
    mem.store_link("NLP Logics", "a machine learning company")
    res = mem.resolve("NLP Logics")
    assert res.mode is AddressingMode.LINK
    assert res.hit.content == "a machine learning company"


def test_inherited_context_exposes_full_cascade(tmp_path):
    root = tmp_path / "prod"
    _build_tree(root)
    mem = MemoryAddressing(str(root))
    scene = str(root / "video_projects" / "nlp_logics" / "scene_three.md")
    ctx = mem.inherited_context(scene)
    assert set(ctx) >= {
        "brand_voice",
        "production_rules",
        "client",
        "tone",
        "scene_conventions",
        "shot_list",
    }


# ---------------------------------------------------------------------------
# Platform module lifecycle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_module_initialize_healthy_and_facade(tmp_path):
    root = tmp_path / "prod"
    _build_tree(root)
    mod = create_position_addressed_memory_module(
        config={"root": str(root)}
    )
    assert mod.status is HealthStatus.UNKNOWN
    await mod.initialize()
    assert mod.status is HealthStatus.HEALTHY
    assert await mod.health_check() is HealthStatus.HEALTHY

    scene = str(root / "video_projects" / "nlp_logics" / "scene_three.md")
    hit = mod.resolve_position(scene)
    assert hit.context["client"] == "NLP Logics"

    stats = mod.stats()
    assert stats["link_pages"] == 0

    await mod.shutdown()
    assert mod.status is HealthStatus.UNKNOWN


@pytest.mark.asyncio
async def test_module_initialize_unhealthy_without_root():
    # No explicit root: the module falls back to a managed default data dir
    # (under the module's own package) so it initializes out-of-the-box, rather
    # than raising. This is the drag-and-drop-friendly behavior.
    mod = create_position_addressed_memory_module(config={})
    await mod.initialize()
    assert mod.status is HealthStatus.HEALTHY
    assert await mod.health_check() is HealthStatus.HEALTHY
    assert mod._addressing is not None  # a default root was materialised


@pytest.mark.asyncio
async def test_module_publishes_events_when_bus_wired(tmp_path):
    root = tmp_path / "prod"
    _build_tree(root)

    published = []

    class _FakeBus:
        def publish(self, event):
            published.append(event.topic)

    mod = create_position_addressed_memory_module(config={"root": str(root)})
    mod.set_event_bus(_FakeBus())
    await mod.initialize()
    scene = str(root / "video_projects" / "nlp_logics" / "scene_three.md")
    mod.resolve_position(scene)
    mod.resolve(scene)
    assert "position_addressed_memory.initialized" in published
    assert "position_addressed_memory.position" in published
    assert "position_addressed_memory.resolved" in published


# ---------------------------------------------------------------------------
# Sanity: core is async-lifecycle independent (pure logic)
# ---------------------------------------------------------------------------

def test_parity_of_manual_run():
    # Guard against regressions where the sync facade diverges from the core.
    mem = MemoryAddressing(root="/tmp/nonexistent-root-pam")
    mem.store_link("Client", "NLP Logics")
    assert mem.resolve("Client").hit.content == "NLP Logics"
    d = mem.store_content("x" * 8)
    assert mem.resolve(d).hit.content == "x" * 8
