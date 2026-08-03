"""
Unit tests for the ENI Skill Factory enterprise module.

Covers:
  - SkillRegistry: create/get/list/update/delete, version bumping, history
  - SkillGenerator: build_frontmatter, extract_steps, name_from_prompt,
    generate_skill
  - SkillEvolutionLoop: record_run scoring, evolve + version bump + refinement
  - SkillFactoryModule: @module registration, lifecycle, health check, events

All IO-heavy tests use ``pytest``'s ``tmp_path`` fixture for isolation.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Ensure the parent of the repo root is on sys.path so that the repo root
# (named ``enterprise``) resolves as a package.  Mirrors the kb_bridge tests.
# ---------------------------------------------------------------------------
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pytest  # noqa: E402

import enterprise.modules.skill_factory as sf_module  # noqa: E402
from enterprise.modules.skill_factory.skill_factory import (  # noqa: E402
    MAX_STEPS,
    SkillEvolutionLoop,
    SkillFactory,
    SkillGenerator,
    SkillRecord,
    SkillRegistry,
    build_frontmatter,
    bump_version,
    extract_steps,
    moving_average,
    name_from_prompt,
    parse_frontmatter,
)
from enterprise.platform_kernel import (  # noqa: E402
    EventBus,
    HealthStatus,
)


def _make_registry(tmp_path: Path) -> SkillRegistry:
    return SkillRegistry(tmp_path)


# ===========================================================================
# Pure helpers
# ===========================================================================


class TestBumpVersion:
    def test_patch_bump(self):
        assert bump_version("1.0.0") == "1.0.1"
        assert bump_version("2.3.4") == "2.3.5"

    def test_minor_bump(self):
        assert bump_version("1.0.0", "minor") == "1.1.0"

    def test_major_bump(self):
        assert bump_version("1.2.3", "major") == "2.0.0"

    def test_short_version(self):
        assert bump_version("1.2") == "1.2.1"
        assert bump_version("1") == "1.0.1"

    def test_invalid_version_defaults(self):
        assert bump_version("garbage") == "1.0.1"


class TestFrontmatter:
    def test_build_frontmatter_is_valid(self):
        meta = {
            "name": "deploy-backup",
            "version": "1.0.0",
            "category": "devops",
            "description": "Deploy a database backup",
            "tags": ["backup", "database"],
        }
        fm = build_frontmatter(meta)
        assert fm.startswith("---\n")
        assert fm.endswith("---\n")
        assert "name: deploy-backup" in fm
        assert "version: 1.0.0" in fm
        assert "category: devops" in fm
        assert "backup" in fm
        assert "database" in fm

    def test_build_parse_round_trip(self):
        meta = {
            "name": "parse-backup",
            "version": "1.2.0",
            "category": "dataops",
            "description": "Parse backup logs",
            "tags": ["logs", "analysis"],
        }
        fm = build_frontmatter(meta)
        parsed, body = parse_frontmatter(fm)
        assert body == ""
        assert parsed["name"] == "parse-backup"
        assert parsed["version"] == "1.2.0"
        assert parsed["category"] == "dataops"
        assert parsed["description"] == "Parse backup logs"
        assert sorted(parsed["tags"]) == ["analysis", "logs"]

    def test_parse_frontmatter_no_delimiter(self):
        parsed, body = parse_frontmatter("just body here")
        assert parsed == {}
        assert body == "just body here"


class TestExtractSteps:
    def test_trims_and_drops_empty(self):
        raw = ["  ls -la  ", "", "   ", "cd /tmp", None]
        steps = extract_steps(raw)
        assert steps == ["ls -la", "cd /tmp"]

    def test_respects_cap(self):
        raw = [f"cmd-{i}" for i in range(MAX_STEPS * 2)]
        steps = extract_steps(raw)
        assert len(steps) == MAX_STEPS
        assert steps[0] == "cmd-0"
        assert steps[-1] == f"cmd-{MAX_STEPS - 1}"

    def test_empty_input(self):
        assert extract_steps([]) == []
        assert extract_steps([""]) == []


class TestNameFromPrompt:
    def test_slug(self):
        assert (
            name_from_prompt("Deploy the PostgreSQL backup!")
            == "deploy-the-postgresql-backup"
        )

    def test_empty_prompt_falls_back(self):
        assert name_from_prompt("   ") == "auto-generated-skill"

    def test_special_characters(self):
        assert name_from_prompt("Install && Configure NGINX") == "install-configure-nginx"


class TestMovingAverage:
    def test_first_run_seeds(self):
        assert moving_average([True]) == 1.0
        assert moving_average([False]) == 0.0

    def test_all_success_stays_high(self):
        assert moving_average([True, True, True]) == 1.0

    def test_success_then_failure(self):
        assert moving_average([True, False]) == 0.7

    def test_empty(self):
        assert moving_average([]) == 0.0


# ===========================================================================
# SkillGenerator
# ===========================================================================


class TestSkillGenerator:
    def test_generate_skill_returns_expected_shape(self):
        gen = SkillGenerator()
        result = gen.generate_skill(
            ["  mkdir -p /backup  ", "rsync -av data/ /backup/", ""],
            category="devops",
            description="Backup the data directory",
            prompt="Create a data backup skill",
        )
        assert result["name"] == "create-a-data-backup-skill"
        assert result["version"] == "1.0.0"
        assert result["category"] == "devops"
        assert result["steps"] == ["mkdir -p /backup", "rsync -av data/ /backup/"]
        # Frontmatter present
        assert result["markdown"].startswith("---\n")
        # Numbered steps present
        assert "1. mkdir -p /backup" in result["markdown"]
        assert "2. rsync -av data/ /backup/" in result["markdown"]
        # Description present in frontmatter block
        assert "Backup the data directory" in result["frontmatter"]

    def test_generate_skill_with_empty_commands(self):
        gen = SkillGenerator()
        result = gen.generate_skill([], description="Something")
        assert result["steps"] == []
        assert "No steps extracted" in result["markdown"]


# ===========================================================================
# SkillRegistry
# ===========================================================================


class TestSkillRegistry:
    def test_create_and_get(self, tmp_path):
        reg = _make_registry(tmp_path)
        record = reg.create(
            "deploy-backup",
            "# Deploy Backup\nRun these steps.",
            category="devops",
            description="Deploy a backup",
            tags=["backup", "deploy"],
        )
        assert record.name == "deploy-backup"
        assert record.version == "1.0.0"
        assert record.body == "# Deploy Backup\nRun these steps."

        loaded = reg.get("deploy-backup")
        assert loaded is not None
        assert loaded.name == "deploy-backup"
        assert loaded.version == "1.0.0"
        assert loaded.category == "devops"
        assert loaded.description == "Deploy a backup"
        assert loaded.tags == ["backup", "deploy"]
        assert loaded.body == record.body

        # File on disk with frontmatter
        skill_file = reg.skill_file("deploy-backup")
        assert skill_file.exists()
        text = skill_file.read_text(encoding="utf-8")
        assert text.startswith("---\n")

    def test_get_missing_returns_none(self, tmp_path):
        reg = _make_registry(tmp_path)
        assert reg.get("missing") is None

    def test_list_returns_metadata_only(self, tmp_path):
        reg = _make_registry(tmp_path)
        reg.create("alpha", "body alpha", description="desc alpha", tags=["a"])
        reg.create("beta", "body beta", description="desc beta", tags=["b"])
        items = reg.list()
        assert len(items) == 2
        names = {i["name"] for i in items}
        assert names == {"alpha", "beta"}
        for item in items:
            assert "body" not in item
            assert "description" in item
            assert "tags" in item
            assert "version" in item
            assert "score" in item

    def test_update_bumps_version_keeps_history(self, tmp_path):
        reg = _make_registry(tmp_path)
        reg.create("skill-a", "v1 body", description="d")
        updated = reg.update("skill-a", body="v2 body")
        assert updated is not None
        assert updated.version == "1.0.1"
        assert updated.body == "v2 body"
        assert len(updated.history) == 1
        assert updated.history[0]["version"] == "1.0.0"
        assert updated.history[0]["body"] == "v1 body"

    def test_create_upsert_bumps_version(self, tmp_path):
        reg = _make_registry(tmp_path)
        reg.create("skill-b", "first body", description="first")
        second = reg.create("skill-b", "second body", description="second")
        assert second.version == "1.0.1"
        assert second.description == "second"
        # History preserved across upserts
        third = reg.create("skill-b", "third body", description="third")
        assert third.version == "1.0.2"
        assert len(third.history) == 2

    def test_delete(self, tmp_path):
        reg = _make_registry(tmp_path)
        reg.create("skill-c", "body c")
        assert reg.delete("skill-c") is True
        assert reg.get("skill-c") is None
        assert reg.delete("skill-c") is False

    def test_invalid_name_raises(self, tmp_path):
        reg = _make_registry(tmp_path)
        with pytest.raises(ValueError):
            reg.create("   ", "body")

    def test_update_missing_returns_none(self, tmp_path):
        reg = _make_registry(tmp_path)
        assert reg.update("nope", body="x") is None


# ===========================================================================
# SkillEvolutionLoop
# ===========================================================================


class TestSkillEvolutionLoop:
    def _seed(self, reg: SkillRegistry):
        return reg.create("evo-skill", "body v1", description="Evolution demo")

    def test_record_run_updates_score(self, tmp_path):
        reg = _make_registry(tmp_path)
        evo = SkillEvolutionLoop(reg)
        self._seed(reg)

        r1 = evo.record_run("evo-skill", True)
        assert r1.score == 1.0

        r2 = evo.record_run("evo-skill", False)
        assert r2.score == pytest.approx(0.7)

        # Persisted
        reloaded = reg.get("evo-skill")
        assert reloaded is not None
        assert reloaded.score == pytest.approx(0.7)

    def test_record_run_appends_feedback(self, tmp_path):
        reg = _make_registry(tmp_path)
        evo = SkillEvolutionLoop(reg)
        self._seed(reg)
        r = evo.record_run("evo-skill", True, feedback="Add a dry-run flag")
        assert "Add a dry-run flag" in r.feedback

    def test_record_run_missing_raises(self, tmp_path):
        reg = _make_registry(tmp_path)
        evo = SkillEvolutionLoop(reg)
        with pytest.raises(KeyError):
            evo.record_run("no-such-skill", True)

    def test_evolve_bumps_version_and_refines(self, tmp_path):
        reg = _make_registry(tmp_path)
        evo = SkillEvolutionLoop(reg)
        self._seed(reg)
        evo.record_run("evo-skill", True, feedback="Consider --force")

        evolved = evo.evolve("evo-skill")
        assert evolved.version == "1.0.1"
        assert "## Outcome & refinement" in evolved.body
        assert "Consider --force" in evolved.body
        # History keeps the original body
        assert evolved.history[0]["version"] == "1.0.0"
        assert "body v1" in evolved.history[0]["body"]

        # Persisted on disk
        reloaded = reg.get("evo-skill")
        assert reloaded is not None
        assert reloaded.version == "1.0.1"
        assert "Outcome & refinement" in reloaded.body

    def test_evolve_missing_raises(self, tmp_path):
        reg = _make_registry(tmp_path)
        evo = SkillEvolutionLoop(reg)
        with pytest.raises(KeyError):
            evo.evolve("no-such-skill")


# ===========================================================================
# SkillFactory facade
# ===========================================================================


class TestSkillFactoryFacade:
    def test_factory_bundles_components(self, tmp_path):
        factory = SkillFactory(tmp_path)
        assert isinstance(factory.registry, SkillRegistry)
        assert isinstance(factory.generator, SkillGenerator)
        assert isinstance(factory.evolution, SkillEvolutionLoop)

    def test_factory_create_get_list_generate(self, tmp_path):
        factory = SkillFactory(tmp_path)
        record = factory.create("facade-skill", "body facade", description="F")
        assert factory.get("facade-skill") is not None
        assert factory.list()[0]["name"] == "facade-skill"

        generated = factory.generate(["step one", ""], description="Gen")
        assert "1. step one" in generated["markdown"]


# ===========================================================================
# SkillFactoryModule (Platform Kernel interface)
# ===========================================================================


class TestSkillFactoryModule:
    def test_module_registered_and_meta(self):
        mod = sf_module.SkillFactoryModule()
        assert mod.name == "skill_factory"
        assert mod.version == "1.0.0"
        assert mod.status == HealthStatus.UNKNOWN

    def test_initialize_healthy(self, tmp_path):
        mod = sf_module.SkillFactoryModule({"data_dir": str(tmp_path)})
        import asyncio

        asyncio.run(mod.initialize())
        assert mod.status == HealthStatus.HEALTHY
        assert mod.factory is not None
        assert isinstance(mod.factory.registry, SkillRegistry)

    def test_health_check_healthy(self, tmp_path):
        mod = sf_module.SkillFactoryModule({"data_dir": str(tmp_path)})
        import asyncio

        asyncio.run(mod.initialize())
        status = asyncio.run(mod.health_check())
        assert status == HealthStatus.HEALTHY

    def test_health_check_unhealthy_when_not_initialized(self):
        mod = sf_module.SkillFactoryModule({"data_dir": "/tmp"})
        import asyncio

        status = asyncio.run(mod.health_check())
        assert status == HealthStatus.UNHEALTHY

    def test_shutdown(self, tmp_path):
        mod = sf_module.SkillFactoryModule({"data_dir": str(tmp_path)})
        import asyncio

        asyncio.run(mod.initialize())
        asyncio.run(mod.shutdown())
        assert mod.factory is None

    def test_initialize_keep_idempotent(self, tmp_path):
        """Initializing twice resolves to a healthy state."""
        mod = sf_module.SkillFactoryModule({"data_dir": str(tmp_path)})
        import asyncio

        asyncio.run(mod.initialize())
        asyncio.run(mod.initialize())
        assert mod.status == HealthStatus.HEALTHY

    def test_event_emission_for_create(self, tmp_path):
        import asyncio

        topics: List[str] = []

        bus = EventBus()

        @bus.subscribe("*")
        def capture(event):
            topics.append(event.topic)

        mod = sf_module.SkillFactoryModule({"data_dir": str(tmp_path)})
        asyncio.run(mod.initialize())
        mod.set_event_bus(bus)
        mod.factory.create("event-skill", "body")
        asyncio.run(asyncio.sleep(0.05))
        assert "skill.created" in topics

    def test_event_emission_for_evolve(self, tmp_path):
        import asyncio

        topics: List[str] = []

        bus = EventBus()

        @bus.subscribe("*")
        def capture(event):
            topics.append(event.topic)

        mod = sf_module.SkillFactoryModule({"data_dir": str(tmp_path)})
        asyncio.run(mod.initialize())
        mod.set_event_bus(bus)
        mod.factory.create("ev-skill", "body")
        mod.factory.evolve("ev-skill")
        asyncio.run(asyncio.sleep(0.05))
        assert "skill.evolved" in topics

    def test_no_event_bus_is_safe(self, tmp_path):
        """Emit guard: no bus wired must not crash."""
        import asyncio

        mod = sf_module.SkillFactoryModule({"data_dir": str(tmp_path)})
        asyncio.run(mod.initialize())
        mod.factory.create("safe-skill", "body")
        mod.factory.evolve("safe-skill")
        assert mod.factory.get("safe-skill") is not None
