#!/usr/bin/env python3
"""
Hermes Universal Local Knowledge Base
======================================
Captures EVERYTHING Hermes does and exposes via MCP + LSP.
- Tool executions, command runs, file operations
- Git commits, test results, session transcripts
- Skills, configs, patterns, memories
- Cross-session, cross-profile persistence
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import sqlite3
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# ─── Configuration ──────────────────────────────────────────────────────────

KB_DIR = Path.home() / ".eni" / "kb"
KB_DIR.mkdir(parents=True, exist_ok=True)

PATTERNS_DB = KB_DIR / "patterns.db"
SKILLS_DB = KB_DIR / "skills.db"
SESSIONS_DB = KB_DIR / "sessions.db"
OPERATIONS_DB = KB_DIR / "operations.db"  # NEW: all operations log
VECTORS_DB = KB_DIR / "vectors.db"        # NEW: embeddings for semantic search

# ─── Database Schemas ───────────────────────────────────────────────────────

SCHEMAS = {
    "patterns": """
        CREATE TABLE IF NOT EXISTS patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_hash TEXT UNIQUE NOT NULL,
            pattern_type TEXT NOT NULL,  -- memory, user, tool_result, command_result, file_op, git_commit, test_result, skill, config, session
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata TEXT,  -- JSON
            source_profile TEXT,
            source_session TEXT,
            tags TEXT,  -- JSON array
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            access_count INTEGER DEFAULT 0,
            last_accessed INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_patterns_type ON patterns(pattern_type);
        CREATE INDEX IF NOT EXISTS idx_patterns_hash ON patterns(pattern_hash);
        CREATE INDEX IF NOT EXISTS idx_patterns_profile ON patterns(source_profile);
        CREATE INDEX IF NOT EXISTS idx_patterns_created ON patterns(created_at);
    """,
    "skills": """
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            category TEXT,
            description TEXT,
            content TEXT NOT NULL,  -- Full SKILL.md
            version TEXT,
            tags TEXT,  -- JSON array
            dependencies TEXT,  -- JSON array
            file_path TEXT,
            enabled INTEGER DEFAULT 1,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            last_used INTEGER,
            use_count INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_skills_category ON skills(category);
        CREATE INDEX IF NOT EXISTS idx_skills_enabled ON skills(enabled);
    """,
    "patterns_skills": """
        CREATE TABLE IF NOT EXISTS pattern_skills (
            pattern_id INTEGER NOT NULL,
            skill_id INTEGER NOT NULL,
            PRIMARY KEY (pattern_id, skill_id)
        );
        CREATE INDEX IF NOT EXISTS idx_pattern_skills_pattern ON pattern_skills(pattern_id);
        CREATE INDEX IF NOT EXISTS idx_pattern_skills_skill ON pattern_skills(skill_id);
    """,
    "sessions": """
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            profile TEXT,
            title TEXT,
            start_time INTEGER NOT NULL,
            end_time INTEGER,
            message_count INTEGER DEFAULT 0,
            tool_calls INTEGER DEFAULT 0,
            commands_run INTEGER DEFAULT 0,
            files_changed INTEGER DEFAULT 0,
            summary TEXT,
            metadata TEXT,  -- JSON
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_profile ON sessions(profile);
        CREATE INDEX IF NOT EXISTS idx_sessions_time ON sessions(start_time);
    """,
    "operations": """
        CREATE TABLE IF NOT EXISTS operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            op_id TEXT UNIQUE NOT NULL,
            session_id TEXT,
            profile TEXT,
            op_type TEXT NOT NULL,  -- tool, command, file_read, file_write, file_edit, git, test, skill_load, config_change
            tool_name TEXT,
            command_name TEXT,
            input_data TEXT,  -- JSON
            output_data TEXT,  -- JSON
            result TEXT,  -- success, error, partial
            error_message TEXT,
            duration_ms INTEGER,
            working_dir TEXT,
            git_commit TEXT,
            tags TEXT,  -- JSON array
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ops_session ON operations(session_id);
        CREATE INDEX IF NOT EXISTS idx_ops_type ON operations(op_type);
        CREATE INDEX IF NOT EXISTS idx_ops_tool ON operations(tool_name);
        CREATE INDEX IF NOT EXISTS idx_ops_time ON operations(created_at);
        CREATE INDEX IF NOT EXISTS idx_ops_profile ON operations(profile);
    """,
    "vectors": """
        CREATE TABLE IF NOT EXISTS vectors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_id INTEGER NOT NULL,
            embedding TEXT NOT NULL,  -- JSON array of floats
            model TEXT NOT NULL,  -- embedding model used
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_vectors_pattern ON vectors(pattern_id);
    """,
    "config_snapshots": """
        CREATE TABLE IF NOT EXISTS config_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile TEXT NOT NULL,
            config_key TEXT NOT NULL,
            config_value TEXT,
            config_type TEXT,  -- yaml, json, env, cli
            file_path TEXT,
            changed_by TEXT,  -- user, auto, cron, skill
            previous_value TEXT,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_config_profile ON config_snapshots(profile);
        CREATE INDEX IF NOT EXISTS idx_config_key ON config_snapshots(config_key);
        CREATE INDEX IF NOT EXISTS idx_config_time ON config_snapshots(created_at);
    """,
    "file_tracking": """
        CREATE TABLE IF NOT EXISTS file_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            operation TEXT NOT NULL,  -- read, write, edit, delete, create
            session_id TEXT,
            profile TEXT,
            content_hash TEXT,  -- SHA256 of content
            content_preview TEXT,
            line_count INTEGER,
            size_bytes INTEGER,
            git_status TEXT,  -- clean, modified, staged, untracked
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_file_path ON file_tracking(file_path);
        CREATE INDEX IF NOT EXISTS idx_file_session ON file_tracking(session_id);
        CREATE INDEX IF NOT EXISTS idx_file_time ON file_tracking(created_at);
    """
}

# ─── Database Manager ───────────────────────────────────────────────────────


class KBManager:
    """Manages all knowledge base databases."""

    def __init__(self):
        self._connections: dict[str, sqlite3.Connection] = {}
        self._init_all()

    def _get_conn(self, db_path: Path) -> sqlite3.Connection:
        if str(db_path) not in self._connections:
            conn = sqlite3.connect(str(db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-32768")  # 32MB cache
            self._connections[str(db_path)] = conn
        return self._connections[str(db_path)]

    def _init_all(self):
        for name, schema in SCHEMAS.items():
            db_map = {
                "patterns": PATTERNS_DB,
                "skills": SKILLS_DB,
                "patterns_skills": SKILLS_DB,
                "sessions": SESSIONS_DB,
                "operations": OPERATIONS_DB,
                "vectors": VECTORS_DB,
                "config_snapshots": PATTERNS_DB,
                "file_tracking": OPERATIONS_DB,
            }
            conn = self._get_conn(db_map[name])
            # Split schema by statement and execute each
            for stmt in schema.split(";"):
                stmt = stmt.strip()
                if stmt:
                    try:
                        conn.execute(stmt)
                    except sqlite3.OperationalError as e:
                        # Ignore "already exists" or cross-db FK errors
                        if "already exists" not in str(e).lower() and "foreign key" not in str(e).lower():
                            raise
            conn.commit()

    @contextmanager
    def transaction(self, db_name: str):
        """Context manager for transactions."""
        db_map = {
            "patterns": PATTERNS_DB,
            "skills": SKILLS_DB,
            "sessions": SESSIONS_DB,
            "operations": OPERATIONS_DB,
            "vectors": VECTORS_DB,
            "config": PATTERNS_DB,
            "files": OPERATIONS_DB,
        }
        conn = self._get_conn(db_map[db_name])
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def close_all(self):
        for conn in self._connections.values():
            conn.close()
        self._connections.clear()


# ─── Global Instance ────────────────────────────────────────────────────────

_kb: KBManager | None = None


def get_kb() -> KBManager:
    global _kb
    if _kb is None:
        _kb = KBManager()
    return _kb


# ─── Core Operations ────────────────────────────────────────────────────────


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _now() -> int:
    return int(time.time())


def store_pattern(
    pattern_type: str,
    title: str,
    content: str,
    metadata: dict | None = None,
    profile: str | None = None,
    session: str | None = None,
    tags: list[str] | None = None,
) -> int | None:
    """Store a pattern in the knowledge base. Returns pattern ID."""
    kb = get_kb()
    pattern_hash = _hash_content(f"{pattern_type}:{title}:{content}")

    with kb.transaction("patterns") as conn:
        # Check if exists
        existing = conn.execute(
            "SELECT id FROM patterns WHERE pattern_hash = ?", (pattern_hash,)
        ).fetchone()
        if existing:
            # Update access count
            conn.execute(
                "UPDATE patterns SET access_count = access_count + 1, last_accessed = ?, updated_at = ? WHERE id = ?",
                (_now(), _now(), existing["id"]),
            )
            return existing["id"]

        cursor = conn.execute(
            """INSERT INTO patterns
               (pattern_hash, pattern_type, title, content, metadata, source_profile, source_session, tags, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                pattern_hash,
                pattern_type,
                title,
                content,
                json.dumps(metadata or {}),
                profile or os.environ.get("HERMES_PROFILE", "default"),
                session,
                json.dumps(tags or []),
                _now(),
                _now(),
            ),
        )
        return cursor.lastrowid


def store_operation(
    op_type: str,
    input_data: dict | None = None,
    output_data: dict | None = None,
    result: str = "success",
    error_message: str | None = None,
    duration_ms: int | None = None,
    tool_name: str | None = None,
    command_name: str | None = None,
    session_id: str | None = None,
    profile: str | None = None,
    working_dir: str | None = None,
    git_commit: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Store an operation (tool call, command, file op, etc.). Returns op_id."""
    kb = get_kb()
    op_id = str(uuid.uuid4())[:12]

    with kb.transaction("operations") as conn:
        conn.execute(
            """INSERT INTO operations
               (op_id, session_id, profile, op_type, tool_name, command_name,
                input_data, output_data, result, error_message, duration_ms,
                working_dir, git_commit, tags, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                op_id,
                session_id,
                profile or os.environ.get("HERMES_PROFILE", "default"),
                op_type,
                tool_name,
                command_name,
                json.dumps(input_data or {}),
                json.dumps(output_data or {}),
                result,
                error_message,
                duration_ms,
                working_dir or os.getcwd(),
                git_commit,
                json.dumps(tags or []),
                _now(),
            ),
        )
    return op_id


def store_file_op(
    file_path: str,
    operation: str,
    content: str | None = None,
    session_id: str | None = None,
    profile: str | None = None,
    line_count: int | None = None,
    git_status: str | None = None,
) -> int:
    """Track a file operation."""
    kb = get_kb()
    content_hash = _hash_content(content) if content else None
    preview = content[:500] if content else None

    with kb.transaction("files") as conn:
        cursor = conn.execute(
            """INSERT INTO file_tracking
               (file_path, operation, session_id, profile, content_hash, content_preview,
                line_count, size_bytes, git_status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                file_path,
                operation,
                session_id,
                profile or os.environ.get("HERMES_PROFILE", "default"),
                content_hash,
                preview,
                line_count,
                len(content) if content else 0,
                git_status,
                _now(),
            ),
        )
        return cursor.lastrowid


def store_config_change(
    profile: str,
    config_key: str,
    config_value: str | None,
    config_type: str = "yaml",
    file_path: str | None = None,
    changed_by: str = "user",
    previous_value: str | None = None,
) -> int:
    """Track a configuration change."""
    kb = get_kb()

    with kb.transaction("config") as conn:
        cursor = conn.execute(
            """INSERT INTO config_snapshots
               (profile, config_key, config_value, config_type, file_path, changed_by, previous_value, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                profile,
                config_key,
                config_value,
                config_type,
                file_path,
                changed_by,
                previous_value,
                _now(),
            ),
        )
        return cursor.lastrowid


def store_session(
    session_id: str,
    profile: str,
    title: str | None = None,
    metadata: dict | None = None,
) -> int:
    """Start tracking a session."""
    kb = get_kb()

    with kb.transaction("sessions") as conn:
        cursor = conn.execute(
            """INSERT OR REPLACE INTO sessions
               (session_id, profile, title, start_time, message_count, tool_calls, commands_run, files_changed, metadata, created_at)
               VALUES (?, ?, ?, ?, 0, 0, 0, 0, ?, ?)""",
            (
                session_id,
                profile,
                title or f"Session {session_id[:8]}",
                _now(),
                json.dumps(metadata or {}),
                _now(),
            ),
        )
        return cursor.lastrowid


def update_session_stats(
    session_id: str,
    message_delta: int = 0,
    tool_delta: int = 0,
    command_delta: int = 0,
    file_delta: int = 0,
) -> None:
    """Update session counters."""
    kb = get_kb()

    with kb.transaction("sessions") as conn:
        conn.execute(
            """UPDATE sessions SET
               message_count = message_count + ?,
               tool_calls = tool_calls + ?,
               commands_run = commands_run + ?,
               files_changed = files_changed + ?
               WHERE session_id = ?""",
            (message_delta, tool_delta, command_delta, file_delta, session_id),
        )


def end_session(session_id: str, summary: str | None = None) -> None:
    """End a session."""
    kb = get_kb()

    with kb.transaction("sessions") as conn:
        conn.execute(
            "UPDATE sessions SET end_time = ?, summary = ? WHERE session_id = ?",
            (_now(), summary, session_id),
        )


def search_patterns(
    query: str | None = None,
    pattern_type: str | None = None,
    profile: str | None = None,
    tags: list[str] | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Search patterns with filters."""
    kb = get_kb()

    sql = "SELECT * FROM patterns WHERE 1=1"
    params = []

    if query:
        sql += " AND (title LIKE ? OR content LIKE ?)"
        params.extend([f"%{query}%", f"%{query}%"])

    if pattern_type:
        sql += " AND pattern_type = ?"
        params.append(pattern_type)

    if profile:
        sql += " AND source_profile = ?"
        params.append(profile)

    if tags:
        for tag in tags:
            sql += " AND tags LIKE ?"
            params.append(f"%{tag}%")

    sql += " ORDER BY last_accessed DESC NULLS LAST, created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with kb.transaction("patterns") as conn:
        rows = conn.execute(sql, params).fetchall()
        results = []
        for row in rows:
            # Update access count
            conn.execute(
                "UPDATE patterns SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
                (_now(), row["id"]),
            )
            results.append(dict(row))
        conn.commit()
        return results


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)


def semantic_search(
    query: str,
    limit: int = 10,
    min_similarity: float = 0.3,
    model_name: str = "all-MiniLM-L6-v2",
) -> list[dict]:
    """
    Semantic search using vector embeddings.
    
    Args:
        query: Search query text
        limit: Maximum number of results
        min_similarity: Minimum cosine similarity threshold (0-1)
        model_name: Embedding model to use
    
    Returns:
        List of pattern dicts with similarity scores, sorted by relevance
    """
    kb = get_kb()
    
    # Import sentence-transformers lazily
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise RuntimeError("sentence-transformers not installed. Run: pip install sentence-transformers")
    
    # Load model
    model = SentenceTransformer(model_name)
    
    # Generate query embedding
    query_embedding = model.encode(query).tolist()
    
    # Get all vectors from database
    with kb.transaction("vectors") as conn:
        rows = conn.execute(
            "SELECT pattern_id, embedding FROM vectors WHERE model = ?",
            (model_name,)
        ).fetchall()
    
    if not rows:
        return []
    
    # Compute similarities
    results = []
    for row in rows:
        pattern_id = row["pattern_id"]
        stored_embedding = json.loads(row["embedding"])
        
        similarity = _cosine_similarity(query_embedding, stored_embedding)
        
        if similarity >= min_similarity:
            # Get pattern details
            with kb.transaction("patterns") as conn:
                pattern = conn.execute(
                    "SELECT * FROM patterns WHERE id = ?", (pattern_id,)
                ).fetchone()
            
            if pattern:
                pattern_dict = dict(pattern)
                pattern_dict["similarity"] = similarity
                results.append(pattern_dict)
    
    # Sort by similarity descending
    results.sort(key=lambda x: x["similarity"], reverse=True)
    
    # Update access counts for returned patterns
    if results:
        with kb.transaction("patterns") as conn:
            for r in results[:limit]:
                conn.execute(
                    "UPDATE patterns SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
                    (_now(), r["id"]),
                )
            conn.commit()
    
    return results[:limit]


def get_stats() -> dict:
    """Get knowledge base statistics."""
    kb = get_kb()
    stats = {}

    with kb.transaction("patterns") as conn:
        stats["patterns_total"] = conn.execute("SELECT COUNT(*) FROM patterns").fetchone()[0]
        stats["patterns_by_type"] = dict(
            conn.execute("SELECT pattern_type, COUNT(*) FROM patterns GROUP BY pattern_type").fetchall()
        )
        stats["patterns_by_profile"] = dict(
            conn.execute("SELECT source_profile, COUNT(*) FROM patterns GROUP BY source_profile").fetchall()
        )

    with kb.transaction("operations") as conn:
        stats["operations_total"] = conn.execute("SELECT COUNT(*) FROM operations").fetchone()[0]
        stats["operations_by_type"] = dict(
            conn.execute("SELECT op_type, COUNT(*) FROM operations GROUP BY op_type").fetchall()
        )
        stats["operations_by_tool"] = dict(
            conn.execute("SELECT tool_name, COUNT(*) FROM operations WHERE tool_name IS NOT NULL GROUP BY tool_name ORDER BY COUNT(*) DESC LIMIT 20").fetchall()
        )

    with kb.transaction("sessions") as conn:
        stats["sessions_total"] = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    with kb.transaction("files") as conn:
        stats["files_tracked"] = conn.execute("SELECT COUNT(*) FROM file_tracking").fetchone()[0]
        stats["files_by_op"] = dict(
            conn.execute("SELECT operation, COUNT(*) FROM file_tracking GROUP BY operation").fetchall()
        )

    with kb.transaction("config") as conn:
        stats["config_changes"] = conn.execute("SELECT COUNT(*) FROM config_snapshots").fetchone()[0]

    # DB sizes
    for db_name, db_path in [
        ("patterns", PATTERNS_DB),
        ("skills", SKILLS_DB),
        ("sessions", SESSIONS_DB),
        ("operations", OPERATIONS_DB),
        ("vectors", VECTORS_DB),
    ]:
        if db_path.exists():
            stats[f"{db_name}_db_size_kb"] = db_path.stat().st_size // 1024

    return stats


# ─── Hermes Memory Offload (Enhanced) ───────────────────────────────────────


def offload_hermes_memory(profile: str | None = None) -> dict:
    """Offload Hermes MEMORY.md and USER.md to knowledge base."""
    profiles_to_check = []

    if profile:
        profiles_to_check.append(profile)
    else:
        # Check all profiles
        hermes_profiles = Path.home() / ".hermes" / "profiles"
        if hermes_profiles.exists():
            for p in hermes_profiles.iterdir():
                if p.is_dir():
                    profiles_to_check.append(p.name)
        profiles_to_check.append("default")

    results = {"offloaded": 0, "skipped": 0, "errors": []}

    for prof in profiles_to_check:
        for mem_type in ["memory", "user"]:
            # Try profile-specific first
            mem_file = Path.home() / ".hermes" / "profiles" / prof / "memories" / f"{mem_type.upper()}.md"
            if not mem_file.exists():
                # Try global
                mem_file = Path.home() / ".hermes" / "memories" / f"{mem_type.upper()}.md"
            if not mem_file.exists():
                results["skipped"] += 1
                continue

            try:
                content = mem_file.read_text()
                if not content.strip():
                    results["skipped"] += 1
                    continue

                # Split into sections for better searchability
                sections = _split_memory_sections(content)

                for i, (section_title, section_content) in enumerate(sections):
                    if section_content.strip():
                        pid = store_pattern(
                            pattern_type=mem_type,
                            title=f"{mem_type}: {section_title}" if section_title else f"{mem_type} (part {i+1})",
                            content=section_content,
                            metadata={
                                "source_file": str(mem_file),
                                "profile": prof,
                                "section_index": i,
                                "total_sections": len(sections),
                            },
                            profile=prof,
                            tags=[mem_type, prof, "hermes", "auto-offload"],
                        )
                        if pid:
                            results["offloaded"] += 1

            except Exception as e:
                results["errors"].append(f"{prof}/{mem_type}: {e}")

    return results


def _split_memory_sections(content: str) -> list[tuple[str, str]]:
    """Split memory content into logical sections."""
    sections = []
    current_title = ""
    current_content = []

    for line in content.split("\n"):
        if line.startswith("§") or line.startswith("##") or line.startswith("# "):
            if current_content:
                sections.append((current_title, "\n".join(current_content)))
            current_title = line.lstrip("§# ").strip()
            current_content = [line]
        else:
            current_content.append(line)

    if current_content:
        sections.append((current_title, "\n".join(current_content)))

    if not sections:
        sections = [("full", content)]

    return sections


# ─── Skills Sync ────────────────────────────────────────────────────────────


def sync_skills() -> dict:
    """Sync all Hermes skills to knowledge base."""
    skills_dir = Path.home() / ".hermes" / "skills"
    results = {"synced": 0, "updated": 0, "errors": []}

    if not skills_dir.exists():
        return results

    kb = get_kb()

    for skill_dir in skills_dir.iterdir():
        if not skill_dir.is_dir():
            continue

        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        try:
            content = skill_md.read_text()
            # Parse frontmatter
            import yaml
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = yaml.safe_load(parts[1])
                    name = frontmatter.get("name", skill_dir.name)
                    category = frontmatter.get("category", "")
                    description = frontmatter.get("description", "")
                    version = frontmatter.get("version", "1.0.0")
                    tags = frontmatter.get("tags", [])
                    deps = frontmatter.get("required_commands", []) + frontmatter.get("required_environment_variables", [])
                else:
                    name = skill_dir.name
                    category = ""
                    description = ""
                    version = "1.0.0"
                    tags = []
                    deps = []
            else:
                name = skill_dir.name
                category = ""
                description = ""
                version = "1.0.0"
                tags = []
                deps = []

            with kb.transaction("skills") as conn:
                existing = conn.execute("SELECT id, content FROM skills WHERE name = ?", (name,)).fetchone()

                if existing and existing["content"] == content:
                    # Update last_used
                    conn.execute(
                        "UPDATE skills SET last_used = ?, use_count = use_count + 1 WHERE id = ?",
                        (_now(), existing["id"]),
                    )
                    results["synced"] += 1
                else:
                    if existing:
                        conn.execute(
                            """UPDATE skills SET category=?, description=?, content=?, version=?, tags=?, dependencies=?, file_path=?, updated_at=?, last_used=?, use_count=use_count+1
                               WHERE id = ?""",
                            (category, description, content, version, json.dumps(tags), json.dumps(deps),
                             str(skill_md), _now(), _now(), existing["id"]),
                        )
                        results["updated"] += 1
                    else:
                        conn.execute(
                            """INSERT INTO skills
                               (name, category, description, content, version, tags, dependencies, file_path, created_at, updated_at, last_used, use_count)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                            (name, category, description, content, version, json.dumps(tags), json.dumps(deps),
                             str(skill_md), _now(), _now(), _now()),
                        )
                        results["synced"] += 1

        except Exception as e:
            results["errors"].append(f"{skill_dir.name}: {e}")

    return results


# ─── CLI ────────────────────────────────────────────────────────────────────


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Hermes Universal Knowledge Base")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # offload
    p_off = sub.add_parser("offload", help="Offload Hermes memory")
    p_off.add_argument("--profile", help="Specific profile")

    # search
    p_search = sub.add_parser("search", help="Search knowledge base (FTS)")
    p_search.add_argument("query", nargs="?", default="")
    p_search.add_argument("--type", help="Pattern type filter")
    p_search.add_argument("--profile", help="Profile filter")
    p_search.add_argument("--tags", nargs="+", help="Tag filters")
    p_search.add_argument("--limit", type=int, default=20)

    # semantic search
    p_semantic = sub.add_parser("semantic", help="Semantic search using vector embeddings")
    p_semantic.add_argument("query", help="Search query")
    p_semantic.add_argument("--limit", type=int, default=10)
    p_semantic.add_argument("--min-similarity", type=float, default=0.3)
    p_semantic.add_argument("--model", default="all-MiniLM-L6-v2")

    # stats
    sub.add_parser("stats", help="Show statistics")

    # sync skills
    sub.add_parser("sync-skills", help="Sync Hermes skills to KB")

    # operations
    p_ops = sub.add_parser("operations", help="Query operations")
    p_ops.add_argument("--session", help="Session ID filter")
    p_ops.add_argument("--type", help="Operation type filter")
    p_ops.add_argument("--tool", help="Tool name filter")
    p_ops.add_argument("--limit", type=int, default=50)

    # session
    p_sess = sub.add_parser("session", help="Session management")
    p_sess.add_argument("action", choices=["start", "end", "stats"])
    p_sess.add_argument("--session-id", help="Session ID")
    p_sess.add_argument("--profile", default="default")
    p_sess.add_argument("--title", help="Session title")
    p_sess.add_argument("--summary", help="Session summary")

    # auto offload
    p_auto = sub.add_parser("auto", help="Auto-offload if threshold exceeded")
    p_auto.add_argument("--threshold", type=int, default=90)

    args = parser.parse_args()

    if args.cmd == "offload":
        result = offload_hermes_memory(args.profile)
        print(json.dumps(result, indent=2))

    elif args.cmd == "search":
        results = search_patterns(
            query=args.query or None,
            pattern_type=args.type,
            profile=args.profile,
            tags=args.tags,
            limit=args.limit,
        )
        print(json.dumps(results, indent=2, default=str))

    elif args.cmd == "semantic":
        results = semantic_search(
            query=args.query,
            limit=args.limit,
            min_similarity=args.min_similarity,
            model_name=args.model,
        )
        print(json.dumps(results, indent=2, default=str))

    elif args.cmd == "stats":
        print(json.dumps(get_stats(), indent=2))

    elif args.cmd == "sync-skills":
        result = sync_skills()
        print(json.dumps(result, indent=2))

    elif args.cmd == "operations":
        kb = get_kb()
        sql = "SELECT * FROM operations WHERE 1=1"
        params = []
        if args.session:
            sql += " AND session_id = ?"
            params.append(args.session)
        if args.type:
            sql += " AND op_type = ?"
            params.append(args.type)
        if args.tool:
            sql += " AND tool_name = ?"
            params.append(args.tool)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(args.limit)

        with kb.transaction("operations") as conn:
            rows = conn.execute(sql, params).fetchall()
            print(json.dumps([dict(r) for r in rows], indent=2, default=str))

    elif args.cmd == "session":
        if args.action == "start":
            sid = args.session_id or str(uuid.uuid4())[:8]
            store_session(sid, args.profile, args.title)
            print(f"Started session: {sid}")
        elif args.action == "end":
            if not args.session_id:
                print("Error: --session-id required")
                sys.exit(1)
            end_session(args.session_id, args.summary)
            print(f"Ended session: {args.session_id}")
        elif args.action == "stats":
            kb = get_kb()
            with kb.transaction("sessions") as conn:
                if args.session_id:
                    row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (args.session_id,)).fetchone()
                else:
                    row = conn.execute("SELECT * FROM sessions ORDER BY start_time DESC LIMIT 1").fetchone()
                if row:
                    print(json.dumps(dict(row), indent=2, default=str))
                else:
                    print("No session found")

    elif args.cmd == "auto":
        # Check memory usage
        import shutil
        # This would check Hermes memory size - simplified for now
        result = offload_hermes_memory()
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()