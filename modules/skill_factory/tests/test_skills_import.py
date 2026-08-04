"""
Unit tests for the standard markdown-skills import capability.

Covers:
  - parse_skill_markdown: frontmatter name/description/body, no-frontmatter
    heading fallback, --TRIGGERS-- block extraction, graceful degradation.
  - import_skill_from_markdown: stores a real, retrievable/listed record via
    the existing SkillRegistry.create.
  - SkillsImportFacade: parse_file, import_dir, list_all.
  - __init__ exports the new symbols without breaking the @module.

All IO-heavy tests use pytest's ``tmp_path`` fixture for isolation.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Mirrors the existing test_skill_factory.py sys.path bootstrap so that the
# repo root (named ``enterprise``) resolves as a package.
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pytest  # noqa: E402

import enterprise.modules.skill_factory as sf_module  # noqa: E402
from enterprise.modules.skill_factory.skill_factory import (  # noqa: E402
    SkillRecord,
    SkillRegistry,
)
from enterprise.modules.skill_factory.skills_import import (  # noqa: E402
    SkillImport,
    SkillsImportFacade,
    import_skill_from_markdown,
    parse_skill_markdown,
)

# ---------------------------------------------------------------------------
# Standard frontmatter fixture
# ---------------------------------------------------------------------------

_STANDARD_FRONTMATTER = """\
---
name: deploy-backup
description: Deploy a database backup to object storage
---

# Deploy Backup

Run these steps to deploy the backup.

--TRIGGERS--
- back up the database
- deploy backup
--END TRIGGERS--
"""

_NO_FRONTMATTER = """\
# Grep Logs

Search the application logs for a pattern.
"""

# ===========================================================================
# parse_skill_markdown
# ===========================================================================


class TestParseSkillMarkdown:
    def test_parses_name_description_and_body(self):
        parsed = parse_skill_markdown(_STANDARD_FRONTMATTER)
        assert isinstance(parsed, SkillImport)
        assert parsed.name == "deploy-backup"
        assert parsed.description == "Deploy a database backup to object storage"
        # Triggers stripped from the body; instructions preserved.
        assert "# Deploy Backup" in parsed.body
        assert "--TRIGGERS--" not in parsed.body
        assert "--END TRIGGERS--" not in parsed.body

    def test_raw_preserved(self):
        parsed = parse_skill_markdown(_STANDARD_FRONTMATTER)
        assert parsed.raw == _STANDARD_FRONTMATTER

    def test_triggers_parsed_into_list(self):
        parsed = parse_skill_markdown(_STANDARD_FRONTMATTER)
        assert parsed.triggers == [
            "back up the database",
            "deploy backup",
        ]

    def test_no_frontmatter_name_from_first_heading(self):
        parsed = parse_skill_markdown(_NO_FRONTMATTER)
        assert parsed.name == "Grep Logs"
        assert parsed.description == ""
        assert parsed.triggers == []
        assert "Search the application logs" in parsed.body

    def test_missing_description_degrades_gracefully(self):
        text = "---\nname: bare-skill\n---\n\nBody here.\n"
        parsed = parse_skill_markdown(text)
        assert parsed.name == "bare-skill"
        assert parsed.description == ""

    def test_missing_required_name_yields_empty(self):
        parsed = parse_skill_markdown("Just some text with no heading.\n")
        assert parsed.name == ""
        assert parsed.body == "Just some text with no heading.\n"

    def test_no_triggers_block_returns_empty_list(self):
        text = "---\nname: quiet\n---\n\nNo triggers here.\n"
        parsed = parse_skill_markdown(text)
        assert parsed.triggers == []

    def test_frontmatter_quoted_description(self):
        text = '---\nname: "quoted-skill"\ndescription: "A: quoted value"\n---\n\nbody\n'
        parsed = parse_skill_markdown(text)
        assert parsed.name == "quoted-skill"
        assert parsed.description == "A: quoted value"

    def test_none_input(self):
        parsed = parse_skill_markdown(None)  # type: ignore[arg-type]
        assert parsed.name == ""
        assert parsed.body == ""

    def test_superpowers_triggers_blank_line_termination(self):
        text = (
            "---\nname: write-tests\n---\n\n# Write Tests\n\n"
            "--TRIGGERS--\n\n- make a test\n- run the suite\n\n"
            "## Usage\n\nDo things.\n"
        )
        parsed = parse_skill_markdown(text)
        assert parsed.triggers == ["make a test", "run the suite"]
        assert "--TRIGGERS--" not in parsed.body
        assert "## Usage" in parsed.body

    def test_to_dict_shape(self):
        parsed = parse_skill_markdown(_STANDARD_FRONTMATTER)
        d = parsed.to_dict()
        assert d["name"] == "deploy-backup"
        assert "body" in d
        assert "triggers" in d
        assert "raw" not in d


# ===========================================================================
# import_skill_from_markdown
# ===========================================================================


class TestImportSkillFromMarkdown:
    def test_import_stores_real_record(self, tmp_path):
        reg = SkillRegistry(tmp_path)
        record = import_skill_from_markdown(_STANDARD_FRONTMATTER, reg)
        assert isinstance(record, SkillRecord)
        assert record.name == "deploy-backup"
        assert record.version == "1.0.0"
        assert record.description == "Deploy a database backup to object storage"
        # Triggers mapped to tags so they survive the registry round-trip.
        assert set(record.tags) == {"back up the database", "deploy backup"}

    def test_import_record_retrievable_via_registry(self, tmp_path):
        reg = SkillRegistry(tmp_path)
        import_skill_from_markdown(_STANDARD_FRONTMATTER, reg)
        loaded = reg.get("deploy-backup")
        assert loaded is not None
        assert loaded.name == "deploy-backup"
        assert "# Deploy Backup" in loaded.body
        assert loaded.description == "Deploy a database backup to object storage"

    def test_import_record_listed_via_registry(self, tmp_path):
        reg = SkillRegistry(tmp_path)
        import_skill_from_markdown(_STANDARD_FRONTMATTER, reg)
        items = reg.list()
        assert len(items) == 1
        assert items[0]["name"] == "deploy-backup"

    def test_import_missing_name_raises(self, tmp_path):
        reg = SkillRegistry(tmp_path)
        with pytest.raises(ValueError):
            import_skill_from_markdown("just some text without heading\n", reg)

    def test_import_without_frontmatter_uses_heading(self, tmp_path):
        reg = SkillRegistry(tmp_path)
        record = import_skill_from_markdown(_NO_FRONTMATTER, reg)
        assert record.name == "Grep Logs"
        assert reg.get("Grep Logs") is not None


# ===========================================================================
# SkillsImportFacade
# ===========================================================================


class TestSkillsImportFacade:
    def test_requires_registry_or_data_dir(self):
        with pytest.raises(ValueError):
            SkillsImportFacade()

    def test_mutually_exclusive_args(self, tmp_path):
        reg = SkillRegistry(tmp_path)
        with pytest.raises(ValueError):
            SkillsImportFacade(registry=reg, data_dir=tmp_path)

    def test_parse_file(self, tmp_path):
        skill_file = tmp_path / "deploy-backup.md"
        skill_file.write_text(_STANDARD_FRONTMATTER, encoding="utf-8")
        facade = SkillsImportFacade(data_dir=tmp_path)
        parsed = facade.parse_file(skill_file)
        assert parsed.name == "deploy-backup"
        assert parsed.triggers == ["back up the database", "deploy backup"]

    def test_import_file(self, tmp_path):
        skill_file = tmp_path / "deploy-backup.md"
        skill_file.write_text(_STANDARD_FRONTMATTER, encoding="utf-8")
        facade = SkillsImportFacade(data_dir=tmp_path / "data")
        record = facade.import_file(skill_file)
        assert record.name == "deploy-backup"
        assert facade.registry.get("deploy-backup") is not None

    def test_import_dir_imports_multiple_files(self, tmp_path):
        src = tmp_path / "skills_src"
        src.mkdir()
        (src / "one.md").write_text(
            "---\nname: skill-one\ndescription: First\n---\n\nBody one.\n",
            encoding="utf-8",
        )
        (src / "two.md").write_text(
            "---\nname: skill-two\ndescription: Second\n---\n\nBody two.\n",
            encoding="utf-8",
        )
        facade = SkillsImportFacade(data_dir=tmp_path / "data")
        records = facade.import_dir(src)
        assert len(records) == 2
        names = {r.name for r in records}
        assert names == {"skill-one", "skill-two"}
        # Both are retrievable from the registry.
        assert facade.registry.get("skill-one") is not None
        assert facade.registry.get("skill-two") is not None

    def test_import_dir_skips_invalid_files_gracefully(self, tmp_path):
        src = tmp_path / "skills_src"
        src.mkdir()
        (src / "good.md").write_text(
            "---\nname: good-skill\n---\n\nGood body.\n", encoding="utf-8"
        )
        (src / "bad.md").write_text("no name, no heading here\n", encoding="utf-8")
        facade = SkillsImportFacade(data_dir=tmp_path / "data")
        records = facade.import_dir(src)
        assert [r.name for r in records] == ["good-skill"]

    def test_list_all(self, tmp_path):
        facade = SkillsImportFacade(data_dir=tmp_path / "data")
        import_skill_from_markdown(_STANDARD_FRONTMATTER, facade.registry)
        items = facade.list_all()
        assert len(items) == 1
        assert items[0]["name"] == "deploy-backup"
        assert "body" not in items[0]

    def test_list_all_empty(self, tmp_path):
        facade = SkillsImportFacade(data_dir=tmp_path / "data")
        assert facade.list_all() == []

    def test_parse_file_utf8_read(self, tmp_path):
        skill_file = tmp_path / "café.md"
        skill_file.write_text(
            "---\nname: café-skill\n---\n\nUnicode body.\n", encoding="utf-8"
        )
        facade = SkillsImportFacade(data_dir=tmp_path)
        assert facade.parse_file(skill_file).name == "café-skill"


# ===========================================================================
# __init__ exports
# ===========================================================================


class TestExports:
    def test_new_symbols_exported(self):
        assert hasattr(sf_module, "SkillImport")
        assert hasattr(sf_module, "SkillsImportFacade")
        assert callable(sf_module.parse_skill_markdown)
        assert callable(sf_module.import_skill_from_markdown)

    def test_existing_exports_still_present(self):
        for name in (
            "SkillFactoryModule",
            "SkillFactory",
            "SkillRegistry",
            "SkillGenerator",
            "SkillEvolutionLoop",
            "SkillRecord",
            "build_frontmatter",
            "parse_frontmatter",
            "extract_steps",
            "bump_version",
        ):
            assert hasattr(sf_module, name), f"missing existing export {name}"

    def test_module_metadata_unchanged(self):
        assert sf_module.SkillFactoryModule().name == "skill_factory"
