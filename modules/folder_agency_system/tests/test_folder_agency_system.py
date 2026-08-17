"""Unit tests for the folder_agency_system module (no network, real assertions)."""
from __future__ import annotations

import asyncio
import json

import pytest

from enterprise.platform_kernel import HealthStatus

from enterprise.modules.folder_agency_system import (
    FolderAgency,
    FolderAgencyError,
    FolderAgencySystemModule,
    FolderKind,
    FolderNode,
    create_folder_agency,
    create_folder_agency_system_module,
)


# --- folder hierarchy structure --------------------------------------------
def test_scaffold_creates_containers(tmp_path):
    agency = FolderAgency(tmp_path)
    tree = agency.scaffold()
    assert tree.kind is FolderKind.ROOT
    for container in ("capabilities", "projects", "agents", "templates", "workbenches", "atlas"):
        assert container in tree.children
        assert tree.children[container].path.is_dir()
        assert (tree.children[container].path / "README.md").is_file()


def test_create_capability_and_project(tmp_path):
    agency = FolderAgency(tmp_path)
    agency.scaffold()
    cap = agency.create_capability("rag-pipeline", "Retrieval augmented generation.")
    proj = agency.create_project("customer-ai", "Build the customer assistant.")
    assert cap.kind is FolderKind.CAPABILITY
    assert proj.kind is FolderKind.PROJECT
    assert cap.path.is_dir() and proj.path.is_dir()
    assert (cap.path / "README.md").read_text(encoding="utf-8") == "Retrieval augmented generation."


def test_create_agent(tmp_path):
    agency = FolderAgency(tmp_path)
    agency.scaffold()
    agent = agency.create_agent("librarian", "Walks the library and fetches what you need.")
    assert agent.kind is FolderKind.AGENT
    assert (agent.path / "README.md").read_text(encoding="utf-8") == (
        "Walks the library and fetches what you need."
    )


def test_duplicate_folder_raises(tmp_path):
    agency = FolderAgency(tmp_path)
    agency.scaffold()
    agency.create_project("alpha")
    with pytest.raises(FolderAgencyError):
        agency.create_project("alpha")


# --- templates & workbenches (deployed software) ---------------------------
def test_import_template_and_deploy_workbench(tmp_path):
    agency = FolderAgency(tmp_path)
    agency.scaffold()
    tpl = agency.import_template("marketing-os", "A marketing operating system.")
    # give the template some content to be copied
    (tpl.path / "strategy.md").write_text("# strategy", encoding="utf-8")

    wb = agency.create_workbench("marketing-os", "acme-marketing")
    assert wb.kind is FolderKind.WORKBENCH
    assert (wb.path / "strategy.md").read_text(encoding="utf-8") == "# strategy"
    # the immutable version-one template is untouched
    assert (tpl.path / "strategy.md").read_text(encoding="utf-8") == "# strategy"
    assert len(agency.list_workbenches()) == 1


def test_workbench_unknown_template_raises(tmp_path):
    agency = FolderAgency(tmp_path)
    agency.scaffold()
    with pytest.raises(FolderAgencyError):
        agency.create_workbench("nope", "w")


# --- atlas (guaranteed facts) ----------------------------------------------
def test_atlas_create_and_read(tmp_path):
    agency = FolderAgency(tmp_path)
    agency.scaffold()
    agency.create_atlas("company-logic", {"mission": "folder-first", "okr": "shipping"})
    facts = agency.read_atlas("company-logic")
    assert facts["mission"] == "folder-first"
    assert facts["okr"] == "shipping"


def test_atlas_missing_raises(tmp_path):
    agency = FolderAgency(tmp_path)
    agency.scaffold()
    with pytest.raises(FolderAgencyError):
        agency.read_atlas("ghost")


# --- librarian query --------------------------------------------------------
def test_librarian_query_walks_whole_library(tmp_path):
    agency = FolderAgency(tmp_path)
    agency.scaffold()
    agency.create_capability("token-reduction", "Cut tokens at scale.")
    agency.create_project("onboarding-agent", "Get new hires up to speed.")
    hits = agency.librarian_query("token")
    assert any(h.kind is FolderKind.CAPABILITY for h in hits)
    assert all("token" in h.name.lower() or "token" in h.description.lower() for h in hits)


def test_render_tree_mentions_nodes(tmp_path):
    agency = FolderAgency(tmp_path)
    agency.scaffold()
    agency.create_project("alpha")
    tree = agency.render_tree()
    assert "projects" in tree
    assert "alpha" in tree
    assert "capabilities" in tree


# --- module lifecycle -------------------------------------------------------
def _run(coro):
    return asyncio.run(coro)


def test_module_initialize_healthy(tmp_path):
    module = create_folder_agency_system_module({"root_dir": str(tmp_path / "mod")})
    _run(module.initialize())
    assert module.status is HealthStatus.HEALTHY
    assert module.agency is not None
    assert (tmp_path / "mod" / "capabilities").is_dir()


def test_module_health_check_and_shutdown(tmp_path):
    module = create_folder_agency_system_module({"root_dir": str(tmp_path / "mod")})
    _run(module.initialize())
    assert _run(module.health_check()) is HealthStatus.HEALTHY
    _run(module.shutdown())
    assert module.status is HealthStatus.STOPPING


def test_module_metadata():
    module = create_folder_agency_system_module()
    assert module.name == "folder_agency_system"
    assert module.version == "1.0.0"
    assert module.config.get("root_dir") is None  # config_defaults merged
    assert module.module_id


def test_module_facade_creates_and_queries(tmp_path):
    module = create_folder_agency_system_module({"root_dir": str(tmp_path / "mod")})
    _run(module.initialize())
    module.create_capability("rag-pipeline", "RAG at scale.")
    module.create_project("customer-ai")
    module.create_agent("librarian")
    module.import_template("marketing-os")
    module.create_workbench("marketing-os", "acme")
    module.create_atlas("facts", {"region": "eu"})
    hits = module.librarian_query("rag")
    assert any(h.kind is FolderKind.CAPABILITY for h in hits)
    manifest = module.manifest()
    assert "projects" in manifest["children"]


def test_event_bus_none_is_safe(tmp_path):
    # Publishing with no event bus attached must be a no-op (not crash).
    module = create_folder_agency_system_module({"root_dir": str(tmp_path / "mod")})
    _run(module.initialize())
    module.create_capability("x")  # internally calls _publish with _event_bus None


class _FakeBus:
    def __init__(self):
        self.published = []

    def publish(self, event):
        self.published.append(event)


def test_event_bus_receives_publish(tmp_path):
    module = create_folder_agency_system_module({"root_dir": str(tmp_path / "mod")})
    _run(module.initialize())
    bus = _FakeBus()
    module.set_event_bus(bus)
    module.create_capability("rag-pipeline")
    assert bus.published
    assert bus.published[0].topic == "folder_agency.capability_created"
    assert bus.published[0].payload["name"] == "rag-pipeline"
