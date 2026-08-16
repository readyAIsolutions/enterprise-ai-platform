#!/usr/bin/env python3
"""
Hermes Memory → ENI Knowledge Base Offload
===========================================
Offloads Hermes persistent memory (5000 char limit) to ENI KB SQLite databases.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

# ─── Paths ──────────────────────────────────────────────────────────────────
ENI_KB_DIR = Path.home() / ".eni" / "kb"
SKILLS_DB = ENI_KB_DIR / "skills.db"
PATTERNS_DB = ENI_KB_DIR / "patterns.db"

# Hermes memory files (profile-aware)
def _get_hermes_memory_paths() -> tuple[Path, Path]:
    # Check profile-specific first, then fallback to global
    profiles_dir = Path.home() / ".hermes" / "profiles"
    if profiles_dir.exists():
        for profile_dir in profiles_dir.iterdir():
            mem_dir = profile_dir / "memories"
            if mem_dir.exists():
                return (mem_dir / "MEMORY.md", mem_dir / "USER.md")
    # Fallback to global
    return (
        Path.home() / ".hermes" / "memories" / "MEMORY.md",
        Path.home() / ".hermes" / "memories" / "USER.md",
    )

HERMES_MEMORY_FILE, HERMES_USER_FILE = _get_hermes_memory_paths()


# ─── Database Helpers ───────────────────────────────────────────────────────

def _connect_skills() -> sqlite3.Connection:
    conn = sqlite3.connect(SKILLS_DB)
    conn.row_factory = sqlite3.Row
    return conn


def _connect_patterns() -> sqlite3.Connection:
    conn = sqlite3.connect(PATTERNS_DB)
    conn.row_factory = sqlite3.Row
    return conn


def _init_tables():
    """Ensure tables exist (they should already from ENI KB daemon)."""
    # patterns.db already has the right schema
    # skills.db already has skills/patterns/sessions tables
    pass


# ─── Core Functions ─────────────────────────────────────────────────────────

def _hash_content(content: str) -> str:
    """Generate deterministic 12-char hash for pattern_id."""
    return hashlib.sha256(content.encode()).hexdigest()[:12]


def _parse_hermes_memory() -> list[dict[str, Any]]:
    """Parse Hermes MEMORY.md and USER.md files."""
    entries = []

    for file_path, target in [(HERMES_MEMORY_FILE, "memory"), (HERMES_USER_FILE, "user")]:
        if not file_path.exists():
            continue
        content = file_path.read_text()
        # Parse format: "- fact" or "## Section\n- fact"
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("- ") or line.startswith("* "):
                fact = line[2:].strip()
                if fact:
                    entries.append({
                        "content": fact,
                        "target": target,
                        "source_file": file_path.name,
                    })

    return entries


def offload_entries(entries: list[dict[str, Any]] | None = None, target: str | None = None) -> int:
    """
    Offload memory entries to ENI KB patterns table.

    Args:
        entries: List of {"content": str, "target": "user|memory"} dicts.
                 If None, reads from Hermes memory files.
        target: Filter by target ("user" or "memory")

    Returns:
        Number of entries offloaded.
    """
    _init_tables()

    if entries is None:
        entries = _parse_hermes_memory()

    if target:
        entries = [e for e in entries if e.get("target") == target]

    if not entries:
        print("No entries to offload")
        return 0

    conn = _connect_patterns()
    cursor = conn.cursor()
    offloaded = 0

    for entry in entries:
        content = entry["content"]
        pattern_id = f"hermes_mem_{_hash_content(content)}"
        name = f"Memory: {content[:50]}"
        metadata = {
            "target": entry.get("target", "memory"),
            "source_file": entry.get("source_file", "MEMORY.md"),
            "original_entry": content,
            "offloaded_at": int(time.time()),
        }

        # Upsert pattern
        cursor.execute("""
            INSERT OR REPLACE INTO patterns (
                pattern_id, name, category, description, verb, noun,
                params, required, example, execution_mode, entrypoint,
                python_handler, http_endpoint, source_files, source_type,
                confidence, metadata, extracted_at, forged, skill_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            pattern_id,
            name,
            "hermes_memory",
            content,
            "remember",
            "fact",
            "{}",
            "[]",
            "",
            "passive",
            "",
            "",
            "",
            "",
            "hermes_memory",
            1.0,
            json.dumps(metadata),
            int(time.time()),
            0,
            None,
        ))
        offloaded += 1

    conn.commit()
    conn.close()

    print(f"Offloaded {offloaded} memory entries to ENI KB (patterns.db)")
    return offloaded


def search_memories(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search offloaded memories in ENI KB."""
    conn = _connect_patterns()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT pattern_id, name, category, description, metadata, extracted_at
        FROM patterns
        WHERE source_type = 'hermes_memory'
        AND (description LIKE ? OR name LIKE ?)
        ORDER BY extracted_at DESC
        LIMIT ?
    """, (f"%{query}%", f"%{query}%", limit))

    results = []
    for row in cursor.fetchall():
        metadata = json.loads(row["metadata"]) if row["metadata"] else {}
        results.append({
            "pattern_id": row["pattern_id"],
            "name": row["name"],
            "category": row["category"],
            "content": row["description"],
            "target": metadata.get("target", "unknown"),
            "source_file": metadata.get("source_file", "unknown"),
            "offloaded_at": metadata.get("offloaded_at", row["extracted_at"]),
        })

    conn.close()
    return results


def restore_to_hermes(max_entries: int = 50, target: str | None = None) -> int:
    """
    Restore memories from ENI KB to Hermes memory files.
    Merges with existing entries (avoids duplicates).
    """
    conn = _connect_patterns()
    cursor = conn.cursor()

    sql = """
        SELECT description, metadata
        FROM patterns
        WHERE source_type = 'hermes_memory'
    """
    params = []
    if target:
        sql += " AND json_extract(metadata, '$.target') = ?"
        params.append(target)
    sql += " ORDER BY extracted_at DESC LIMIT ?"
    params.append(max_entries)

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("No memories to restore")
        return 0

    # Read existing memories to avoid duplicates
    existing = set()
    for f in [HERMES_MEMORY_FILE, HERMES_USER_FILE]:
        if f.exists():
            for line in f.read_text().splitlines():
                line = line.strip()
                if line.startswith("- ") or line.startswith("* "):
                    existing.add(line[2:].strip())

    # Prepare new entries
    new_memory = []
    new_user = []

    for row in rows:
        content = row["description"]
        metadata = json.loads(row["metadata"]) if row["metadata"] else {}
        t = metadata.get("target", "memory")

        if content not in existing:
            if t == "user":
                new_user.append(f"- {content}")
            else:
                new_memory.append(f"- {content}")

    # Write back
    restored = 0
    if new_memory:
        HERMES_MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing_content = HERMES_MEMORY_FILE.read_text() if HERMES_MEMORY_FILE.exists() else ""
        with HERMES_MEMORY_FILE.open("a") as f:
            if existing_content and not existing_content.endswith("\n"):
                f.write("\n")
            for entry in new_memory:
                f.write(f"{entry}\n")
                restored += 1

    if new_user:
        HERMES_USER_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing_content = HERMES_USER_FILE.read_text() if HERMES_USER_FILE.exists() else ""
        with HERMES_USER_FILE.open("a") as f:
            if existing_content and not existing_content.endswith("\n"):
                f.write("\n")
            for entry in new_user:
                f.write(f"{entry}\n")
                restored += 1

    print(f"Restored {restored} memory entries to Hermes ({len(new_memory)} memory, {len(new_user)} user)")
    return restored


def get_stats() -> dict[str, Any]:
    """Get statistics about offloaded memories."""
    conn = _connect_patterns()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM patterns WHERE source_type = 'hermes_memory'")
    total = cursor.fetchone()[0]

    cursor.execute("""
        SELECT json_extract(metadata, '$.target') as target, COUNT(*)
        FROM patterns
        WHERE source_type = 'hermes_memory'
        GROUP BY target
    """)
    by_target = dict(cursor.fetchall())

    cursor.execute("""
        SELECT MIN(extracted_at), MAX(extracted_at)
        FROM patterns
        WHERE source_type = 'hermes_memory'
    """)
    min_ts, max_ts = cursor.fetchone()

    conn.close()

    return {
        "total_offloaded": total,
        "by_target": by_target,
        "oldest": min_ts,
        "newest": max_ts,
        "skills_db_size": SKILLS_DB.stat().st_size if SKILLS_DB.exists() else 0,
        "patterns_db_size": PATTERNS_DB.stat().st_size if PATTERNS_DB.exists() else 0,
    }


def auto_offload(threshold_pct: int = 90) -> bool:
    """
    Check Hermes memory usage and offload if over threshold.

    Returns True if offload was performed.
    """
    # Read current memory files
    total_chars = 0
    for f in [HERMES_MEMORY_FILE, HERMES_USER_FILE]:
        if f.exists():
            total_chars += len(f.read_text())

    usage_pct = (total_chars / 5000) * 100

    if usage_pct >= threshold_pct:
        print(f"Memory usage {usage_pct:.1f}% >= {threshold_pct}%, offloading...")
        offload_entries()
        return True
    else:
        print(f"Memory usage {usage_pct:.1f}% < {threshold_pct}%, no offload needed")
        return False


# ─── CLI ────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Hermes Memory → ENI KB Offload")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # offload
    p = sub.add_parser("offload", help="Offload Hermes memory to ENI KB")
    p.add_argument("--target", choices=["user", "memory"], help="Filter by target")

    # search
    p = sub.add_parser("search", help="Search offloaded memories")
    p.add_argument("query", help="Search query")
    p.add_argument("--limit", type=int, default=20)

    # restore
    p = sub.add_parser("restore", help="Restore memories to Hermes")
    p.add_argument("--max", type=int, default=50, dest="max_entries")
    p.add_argument("--target", choices=["user", "memory"])

    # stats
    sub.add_parser("stats", help="Show offload statistics")

    # auto
    p = sub.add_parser("auto", help="Auto-offload if memory > threshold")
    p.add_argument("--threshold", type=int, default=90, help="Threshold percentage")

    args = parser.parse_args()

    if args.cmd == "offload":
        entries = _parse_hermes_memory()
        if args.target:
            entries = [e for e in entries if e["target"] == args.target]
        offload_entries(entries)

    elif args.cmd == "search":
        results = search_memories(args.query, args.limit)
        if results:
            for r in results:
                print(f"  [{r['pattern_id']}] {r['target']}: {r['content'][:80]}...")
        else:
            print("No matches found")

    elif args.cmd == "restore":
        restore_to_hermes(args.max_entries, args.target)

    elif args.cmd == "stats":
        stats = get_stats()
        print(f"Total offloaded: {stats['total_offloaded']}")
        print(f"By target: {stats['by_target']}")
        print(f"Oldest: {stats['oldest']}")
        print(f"Newest: {stats['newest']}")
        print(f"skills.db: {stats['skills_db_size']:,} bytes")
        print(f"patterns.db: {stats['patterns_db_size']:,} bytes")

    elif args.cmd == "auto":
        auto_offload(args.threshold)


if __name__ == "__main__":
    main()