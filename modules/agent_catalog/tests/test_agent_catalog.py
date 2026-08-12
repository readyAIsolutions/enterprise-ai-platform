"""Tests for the ENI Agent Catalog module."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from enterprise.modules.agent_catalog import (
    AgentCatalogFacade,
    AgentCatalogModule,
    AgentCatalogStore,
    create_agent_catalog_module,
)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(HERE), "data")
CANONICAL = os.path.join(DATA_DIR, "agent_catalog.json")


@pytest.fixture(scope="module")
def canonical() -> dict[str, Any]:
    with open(CANONICAL, "r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture()
def agents(canonical: dict[str, Any]) -> list[dict[str, Any]]:
    return list(canonical["agents"])


def _make_store(
    tmp_path: Path, agents: list[dict[str, Any]]
) -> tuple[AgentCatalogStore, Path]:
    db = tmp_path / "catalog.db"
    store = AgentCatalogStore(db_path=str(db))
    store.load_canonical(agents)
    return store, db


# --------------------------------------------------------------------------- #
# Canonical data integrity
# --------------------------------------------------------------------------- #
def test_canonical_exists_and_nonempty(canonical: dict[str, Any]) -> None:
    assert canonical["schema_version"]
    assert canonical["stats"]["unique_agents"] >= 400
    assert len(canonical["agents"]) == canonical["stats"]["unique_agents"]


def test_every_agent_has_instructions(agents: list[dict[str, Any]]) -> None:
    missing = [a["slug"] for a in agents if len(a.get("instructions", "")) < 50]
    assert not missing, f"agents missing real instructions: {missing[:10]}"


def test_both_sources_present(agents: list[dict[str, Any]]) -> None:
    sources = {s for a in agents for s in (a.get("sources") or [])}
    assert "codex" in sources
    assert "agency" in sources


def test_no_duplicate_slugs(agents: list[dict[str, Any]]) -> None:
    slugs = [a["slug"] for a in agents]
    assert len(slugs) == len(set(slugs))


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #
def test_store_load_and_count(
    tmp_path: Path, agents: list[dict[str, Any]]
) -> None:
    store, _ = _make_store(tmp_path, agents)
    assert store.count() == len(agents)
    store.close()


def test_store_search_by_query(
    tmp_path: Path, agents: list[dict[str, Any]]
) -> None:
    store, _ = _make_store(tmp_path, agents)
    results = store.search(query="architect", limit=20)
    assert results
    assert len(results) <= 20
    store.close()


def test_store_filter_by_source(
    tmp_path: Path, agents: list[dict[str, Any]]
) -> None:
    store, _ = _make_store(tmp_path, agents)
    codex = store.search(source="codex", limit=1000)
    agency = store.search(source="agency", limit=1000)
    assert all("codex" in a["sources"] for a in codex)
    assert all("agency" in a["sources"] for a in agency)
    assert codex and agency
    store.close()


def test_store_filter_by_category(
    tmp_path: Path, agents: list[dict[str, Any]]
) -> None:
    store, _ = _make_store(tmp_path, agents)
    cats = store.categories()
    assert cats
    target = next(e for e in cats if e.startswith(("0", "1")))
    results = store.search(category=target, limit=1000)
    assert results
    assert all(target in a["categories"] for a in results)
    store.close()


def test_store_get_by_slug(
    tmp_path: Path, agents: list[dict[str, Any]]
) -> None:
    store, _ = _make_store(tmp_path, agents)
    a = store.get(agents[0]["slug"])
    assert a is not None
    assert a["slug"] == agents[0]["slug"]
    assert store.get("definitely-not-a-slug-xyz") is None
    store.close()


def test_store_faceted_overview(
    tmp_path: Path, agents: list[dict[str, Any]]
) -> None:
    store, _ = _make_store(tmp_path, agents)
    ov = store.faceted_overview()
    assert ov["total"] == len(agents)
    assert "codex" in ov["sources"]
    assert "agency" in ov["sources"]
    store.close()


def test_store_json_fallback_without_db(
    tmp_path: Path, agents: list[dict[str, Any]]
) -> None:
    store = AgentCatalogStore(db_path=None)
    store.load_canonical(agents[:50])
    assert store.count() == 50
    assert store.get(agents[0]["slug"]) is not None
    store.close()


# --------------------------------------------------------------------------- #
# Module lifecycle
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_module_boots_healthy_and_serves(tmp_path: Path) -> None:
    mod = create_agent_catalog_module({"db_path": str(tmp_path / "m.db")})
    await mod.initialize()
    assert (await mod.health_check()).value == "healthy"
    f = mod.facade
    assert f is not None
    assert f.overview()["total"] >= 400
    await mod.shutdown()


@pytest.mark.asyncio
async def test_module_a2a_registration(tmp_path: Path) -> None:
    try:
        from enterprise.modules.a2a.a2a import A2AFacade
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"a2a unavailable: {exc}")
    mod = create_agent_catalog_module({"db_path": str(tmp_path / "m2.db")})
    await mod.initialize()
    assert mod.facade is not None
    a2a = A2AFacade()
    n = mod.facade.register_all_in_a2a(a2a)
    assert n >= 400
    assert len(a2a.list_agents()) >= 400
    await mod.shutdown()


@pytest.mark.asyncio
async def test_module_health_when_not_initialized() -> None:
    mod = create_agent_catalog_module()
    assert (await mod.health_check()).value == "starting"
    await mod.shutdown()


# --------------------------------------------------------------------------- #
# Facade
# --------------------------------------------------------------------------- #
def test_facade_search_and_get(
    tmp_path: Path, agents: list[dict[str, Any]]
) -> None:
    store, _ = _make_store(tmp_path, agents)
    facade = AgentCatalogFacade(store)
    res = facade.search(query="security", limit=10)
    assert res
    assert len(res) <= 10
    assert facade.categories()
    assert facade.sources()
    store.close()
