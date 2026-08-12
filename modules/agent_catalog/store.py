"""Agent Catalog Store — SQLite-backed unified agent registry.

Holds every specialist agent from the fused catalog (Codex subagents + Agency
division agents) in a single normalized SQLite store, and exposes search /
filter / lookup / export operations. Falls back to the committed canonical JSON
when SQLite is unavailable (read-only mode).
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Iterable
from typing import Any


def _default_detail_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "agents")


def _default_canonical_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "agent_catalog.json")


class AgentCatalogStore:
    """Normalized, searchable store of specialist agents."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS agents (
        slug            TEXT PRIMARY KEY,
        name            TEXT NOT NULL,
        description     TEXT NOT NULL DEFAULT '',
        sources         TEXT NOT NULL DEFAULT '[]',
        categories      TEXT NOT NULL DEFAULT '[]',
        model           TEXT,
        model_reasoning_effort TEXT,
        sandbox_mode    TEXT,
        emoji           TEXT,
        color           TEXT,
        vibe            TEXT,
        instructions    TEXT NOT NULL DEFAULT '',
        origin_path     TEXT,
        search_tokens   TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_agents_name ON agents(name);
    CREATE INDEX IF NOT EXISTS idx_agents_sources ON agents(sources);
    """

    def __init__(self, db_path: str | None = None) -> None:
        self._lock = threading.RLock()
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._json_agents: list[dict[str, Any]] | None = None
        if db_path:
            self._conn = sqlite3.connect(db_path)
            self._conn.row_factory = sqlite3.Row
            with self._lock:
                self._conn.executescript(self.SCHEMA)

    # -- loaders ------------------------------------------------------------ #
    def load_canonical(self, agents: Iterable[dict[str, Any]]) -> int:
        """Bulk-load canonical agent records, replacing any existing rows."""
        rows = list(agents)
        with self._lock:
            if self._conn is not None:
                self._conn.execute("DELETE FROM agents")
                for r in rows:
                    self._conn.execute(
                        """
                        INSERT OR REPLACE INTO agents (
                            slug,name,description,sources,categories,model,
                            model_reasoning_effort,sandbox_mode,emoji,color,vibe,
                            instructions,origin_path,search_tokens
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            r.get("slug", ""),
                            r.get("name", ""),
                            r.get("description", ""),
                            json.dumps(r.get("sources") or []),
                            json.dumps(r.get("categories") or []),
                            r.get("model"),
                            r.get("model_reasoning_effort"),
                            r.get("sandbox_mode"),
                            r.get("emoji"),
                            r.get("color"),
                            r.get("vibe"),
                            r.get("instructions", ""),
                            r.get("origin_path"),
                            self._tokens(r),
                        ),
                    )
                self._conn.commit()
            else:
                self._json_agents = rows
        return len(rows)

    @staticmethod
    def _tokens(r: dict[str, Any]) -> str:
        parts = [
            r.get("slug", ""),
            r.get("name", ""),
            r.get("description", ""),
            " ".join(r.get("categories") or []),
        ]
        return " ".join(str(p) for p in parts).lower()

    # -- queries ------------------------------------------------------------ #
    def search(
        self,
        query: str = "",
        source: str | None = None,
        category: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        q = query.strip().lower()
        out: list[dict[str, Any]] = []
        with self._lock:
            if self._conn is not None:
                sql = "SELECT * FROM agents"
                wheres: list[str] = []
                params: list[Any] = []
                if q:
                    like = f"%{q}%"
                    wheres.append(
                        "(lower(name) LIKE ? OR lower(description) LIKE ? "
                        "OR search_tokens LIKE ?)"
                    )
                    params += [like, like, f"%{q}%"]
                if source:
                    wheres.append(
                        "EXISTS (SELECT 1 FROM json_each(sources) "
                        "WHERE json_each.value = ?)"
                    )
                    params.append(source)
                if category:
                    wheres.append(
                        "EXISTS (SELECT 1 FROM json_each(categories) "
                        "WHERE json_each.value = ?)"
                    )
                    params.append(category)
                if wheres:
                    sql += " WHERE " + " AND ".join(wheres)
                sql += " ORDER BY name LIMIT ?"
                params.append(limit)
                for row in self._conn.execute(sql, params):
                    out.append(self._row_to_agent(row))
            else:
                for a in self._json_agents or []:
                    if self._match(a, q, source, category):
                        out.append(a)
                    if len(out) >= limit:
                        break
        return out

    def get(self, slug: str) -> dict[str, Any] | None:
        slug = slug.lower()
        with self._lock:
            if self._conn is not None:
                row = self._conn.execute("SELECT * FROM agents WHERE lower(slug)=?", (slug,)).fetchone()
                return self._row_to_agent(row) if row else None
            for a in self._json_agents or []:
                if str(a.get("slug", "")).lower() == slug:
                    return a
        return None

    def categories(self) -> list[str]:
        seen: set[str] = set()
        with self._lock:
            if self._conn is not None:
                for row in self._conn.execute("SELECT categories FROM agents"):
                    seen.update(json.loads(row["categories"]))
            else:
                for a in self._json_agents or []:
                    seen.update(a.get("categories") or [])
        return sorted(seen)

    def sources(self) -> list[str]:
        seen: set[str] = set()
        with self._lock:
            if self._conn is not None:
                for row in self._conn.execute("SELECT sources FROM agents"):
                    seen.update(json.loads(row["sources"]))
            else:
                for a in self._json_agents or []:
                    seen.update(a.get("sources") or [])
        return sorted(seen)

    def count(self) -> int:
        with self._lock:
            if self._conn is not None:
                row = self._conn.execute("SELECT COUNT(*) AS n FROM agents").fetchone()
                return int(row["n"])
            return len(self._json_agents or [])

    @staticmethod
    def _row_to_agent(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "slug": row["slug"],
            "name": row["name"],
            "description": row["description"],
            "sources": json.loads(row["sources"]),
            "categories": json.loads(row["categories"]),
            "model": row["model"],
            "model_reasoning_effort": row["model_reasoning_effort"],
            "sandbox_mode": row["sandbox_mode"],
            "emoji": row["emoji"],
            "color": row["color"],
            "vibe": row["vibe"],
            "instructions": row["instructions"],
            "origin_path": row["origin_path"],
        }

    @staticmethod
    def _match(
        a: dict[str, Any],
        q: str,
        source: str | None,
        category: str | None,
    ) -> bool:
        if q:
            blob = " ".join(
                str(a.get(k, ""))
                for k in ("slug", "name", "description")
            ).lower()
            blob += " " + " ".join(a.get("categories") or []).lower()
            if q not in blob:
                return False
        if source and source not in (a.get("sources") or [a.get("source")]):
            return False
        if category and category not in (a.get("categories") or []):
            return False
        return True

    def faceted_overview(self) -> dict[str, Any]:
        return {
            "total": self.count(),
            "categories": self.categories(),
            "sources": self.sources(),
        }

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
