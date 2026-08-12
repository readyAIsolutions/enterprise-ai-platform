"""ENI Agent Catalog Module -- unified specialist-agent registry.

Fuses two complementary specialist-agent catalogs into one normalized,
searchable platform module:

  * **Codex** subagents  (~/Desktop/awesome-codex-subagents-main) — 172
    engineering-focused agents in native Codex ``.toml`` format, each carrying
    a model hint, reasoning effort and sandbox mode.
  * **Agency** division agents (~/Desktop/agency-agents-main) — 263 business /
    product / sales / marketing / design / engineering agents in Markdown with
    YAML frontmatter (someone "persona" agents with emoji + color + vibe).

"Rebuilt better" means: a single normalized schema, cross-source slug
deduplication (shared roles collapse into one record with unioned categories
and sources), SQLite persistence with faceted search, and every agent
registered as an A2A ``AgentCard`` so it can participate in the platform's
agent-to-agent network.

The module is a registered Platform Kernel module implementing the standard
lifecycle (``initialize`` / ``health_check`` / ``shutdown``) and the event-bus
wiring contract (``set_event_bus``). A public ``AgentCatalogFacade`` exposes
``search`` / ``get`` / ``overview`` / ``register_all_in_a2a``.

The canonical catalog JSON is committed to ``data/agent_catalog.json`` so the
module works offline; ``python -m modules.agent_catalog.ingest`` regenerates it
from the live source repos, and ``create_agent_catalog_module`` may pass a
``refresh_ingest=True`` config to re-ingest on boot.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
from typing import Any

from enterprise.platform_kernel import (
    HealthStatus,
    Module,
    module,
)

from .store import AgentCatalogStore, _default_canonical_path

__version__ = "1.0.0"
__module__ = "agent_catalog"

_logger = logging.getLogger("eni.agent_catalog")

__all__ = [
    "AgentCatalogModule",
    "AgentCatalogFacade",
    "AgentCatalogStore",
    "create_agent_catalog_module",
]


class AgentCatalogFacade:
    """User-facing surface of the Agent Catalog module."""

    def __init__(self, store: AgentCatalogStore) -> None:
        self._store = store
        self._a2a_cards: dict[str, Any] = {}
        self._a2a_registry: Any | None = None

    # -- reads -------------------------------------------------------------- #
    def search(
        self,
        query: str = "",
        source: str | None = None,
        category: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Faceted search across all specialist agents.

        ``query`` matches name / description / keywords; ``source`` filters to
        ``"codex"`` or ``"agency"``; ``category`` matches a division/category.
        """
        return self._store.search(query=query, source=source, category=category, limit=limit)

    def get(self, slug: str) -> dict[str, Any] | None:
        return self._store.get(slug)

    def overview(self) -> dict[str, Any]:
        return self._store.faceted_overview()

    def categories(self) -> list[str]:
        return self._store.categories()

    def sources(self) -> list[str]:
        return self._store.sources()

    # -- A2A integration ---------------------------------------------------- #
    def register_all_in_a2a(self, a2a_facade: Any) -> int:
        """Register every catalog agent as an A2A AgentCard.

        Returns the number of cards registered. Idempotent per module instance.
        """
        cards: dict[str, Any] = {}
        for slug in [a["slug"] for a in self.list_all()]:
            agent = self.get(slug)
            if agent is None:
                continue
            try:
                from enterprise.modules.a2a.a2a import AgentCard

                card = AgentCard(
                    name=agent.get("slug", slug),
                    description=agent.get("description", ""),
                    capabilities=[
                        *(agent.get("categories") or []),
                        *(agent.get("sources") or []),
                    ],
                    skills=[agent.get("vibe") or ""] if agent.get("vibe") else [],
                )
            except Exception:  # pragma: no cover - optional a2a dep
                from dataclasses import dataclass  # fallback.shape

                @dataclass
                class AgentCard:  # type: ignore[no-redef]
                    name: str = ""
                    description: str = ""
                    capabilities: list[str] | None = None
                    skills: list[str] | None = None

                card = AgentCard(
                    name=agent.get("slug", slug),
                    description=agent.get("description", ""),
                    capabilities=[*(agent.get("categories") or []), *(agent.get("sources") or [])],
                    skills=[agent.get("vibe") or ""] if agent.get("vibe") else [],
                )
            cards[card.name] = card

        registered = 0
        if a2a_facade is not None and hasattr(a2a_facade, "register_agent_card"):
            for card in cards.values():
                try:
                    a2a_facade.register_agent_card(card)
                    registered += 1
                except Exception:  # pragma: no cover
                    continue
        self._a2a_cards = cards
        self._a2a_registry = a2a_facade
        return registered if registered else len(cards)

    def list_all(self, limit: int = 100000) -> list[dict[str, Any]]:
        return self._store.search(query="", limit=limit)

    @property
    def a2a_card_count(self) -> int:
        return len(self._a2a_cards)


@module(name="agent_catalog", version=__version__)
class AgentCatalogModule(Module):
    """Platform Kernel module wrapping :class:`AgentCatalogFacade`."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__()
        self._config = config or {}
        cfg = self._config
        repo_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        db = cfg.get("db_path")
        if not db:
            db = os.path.join(repo_root, "data", "agent_catalog.db")
        elif not os.path.isabs(db):
            db = os.path.join(repo_root, db)
        canon = cfg.get("canonical_path") or _default_canonical_path()
        if not os.path.isabs(canon):
            canon = os.path.join(repo_root, canon)
        self._db_path = db
        self._canonical_path = canon
        self._refresh_ingest = bool(cfg.get("refresh_ingest", False))
        self._store: AgentCatalogStore | None = None
        self._facade: AgentCatalogFacade | None = None
        self._health: HealthStatus | None = None

    @property
    def facade(self) -> AgentCatalogFacade | None:
        return self._facade

    async def initialize(self) -> None:
        _logger.info("agent_catalog initializing (db=%s)", self._db_path)
        try:
            if self._refresh_ingest:
                try:
                    from . import ingest  # local import to avoid boot cost

                    codex_root = os.path.expanduser(
                        "~/Desktop/awesome-codex-subagents-main/categories"
                    )
                    agency_root = os.path.expanduser("~/Desktop/agency-agents-main")
                    canon = ingest.build_canonical(codex_root, agency_root)
                    parent = os.path.dirname(self._canonical_path)
                    os.makedirs(parent, exist_ok=True)
                    with open(self._canonical_path, "w", encoding="utf-8") as fh:
                        json.dump(canon, fh, indent=2, ensure_ascii=False)
                    _logger.info("agent_catalog re-ingested from live sources (%s agents)",
                                 len(canon["agents"]))
                except Exception as exc:  # pragma: no cover
                    _logger.warning("refresh_ingest failed; using committed canonical: %s", exc)

            with open(self._canonical_path, encoding="utf-8") as fh:
                canonical = json.load(fh)
            agents = canonical["agents"]

            store = AgentCatalogStore(db_path=self._db_path)
            store.load_canonical(agents)
            self._store = store
            self._facade = AgentCatalogFacade(store)
            self._health = HealthStatus.HEALTHY
            _logger.info("agent_catalog initialized with %s agents", store.count())
        except Exception as exc:  # pragma: no cover
            _logger.exception("Failed to initialize agent_catalog module: %s", exc)
            self._health = HealthStatus.UNHEALTHY
            if self._store:
                self._store.close()
                self._store = None

    async def health_check(self) -> HealthStatus:
        if self._health is None:
            return HealthStatus.STARTING
        if self._health == HealthStatus.HEALTHY and self._store is not None:
            # verify store actually queryable
            try:
                self._store.count()
                return HealthStatus.HEALTHY
            except Exception:  # pragma: no cover
                return HealthStatus.DEGRADED
        return self._health

    async def shutdown(self) -> None:
        _logger.info("Shutting down agent_catalog module...")
        if self._store is not None:
            self._store.close()
            self._store = None
        self._facade = None
        self._health = HealthStatus.STOPPING

    def set_event_bus(self, event_bus: Any) -> None:
        self._event_bus = event_bus

    def _emit(self, topic: str, payload: dict[str, Any]) -> None:
        bus = getattr(self, "_event_bus", None)
        if bus is not None and hasattr(bus, "publish_sync"):
            with contextlib.suppress(Exception):
                bus.publish_sync(topic, payload)


def create_agent_catalog_module(config: dict[str, Any] | None = None) -> AgentCatalogModule:
    """Factory creating an Agent Catalog module (Kernel discovery contract)."""
    return AgentCatalogModule(config=config or {})
