---
name: hermes-memory-kb-offload
description: Offload Hermes persistent memory to ENI Knowledge Base (SQLite) when memory is full. Provides automatic and manual memory persistence to ~/.eni/kb/skills.db and ~/.eni/kb/patterns.db.
category: hermes-cli
version: 1.0.0
tags: [hermes, memory, knowledge-base, sqlite, offload, persistence]
---

# Hermes Memory → ENI Knowledge Base Offload — COMPLETE + UNIVERSAL KB

## Problem

Hermes memory is limited to **5,000 chars** (currently 4,947/5,000 = 99% full). When full, new memories cannot be added without removing old ones.

## PITFALL — bundled offload script targets a STALE schema
`~/.hermes/scripts/hermes_memory_kb_offload.py` may `INSERT ... INTO patterns (pattern_id, ...)`
and crash with `sqlite3.OperationalError: table patterns has no column named pattern_id`.

The **live** `~/.eni/kb/patterns.db` schema has moved on. Verify it first:
```
sqlite3 ~/.eni/kb/patterns.db ".schema patterns"
```
Live columns (as of 2026): `id, pattern_hash UNIQUE, pattern_type, title, content,
metadata (JSON), source_profile, source_session, tags (JSON), created_at, updated_at,
access_count, last_accessed`. If the script doesn't match, don't fight the script — bulk
insert directly from the memory files with a one-off Python script:
- Read `~/.hermes/memories/MEMORY.md` (split on `§`) and `~/.hermes/memories/USER.md` (target `user`).
- For each entry compute `pattern_hash = sha256(f"hermes_memory:{target}:{content}")`,
  `pattern_type='hermes_memory'`, `title = content.split('.')[0][:60]`,
  `metadata=json.dumps({"target":target,"original_entry":content})`, `tags=json.dumps(["memory","offload"])`.
- `INSERT OR REPLACE` (idempotent per hash). This upserted 16 entries and stayed retrievable.

## ⚠️ Loaded-skill pitfall (2026-08): bundled offload script is STALE

The helper `~/.hermes/scripts/hermes_memory_kb_offload.py` (and the older `python -m lib.hermes_memory_kb offload` path under ENI_Swarm_NEW) targets an OUTDATED `patterns` schema and will fail with:
`sqlite3.OperationalError: table patterns has no column named pattern_id`

The LIVE schema (verify with `sqlite3 ~/.eni/kb/patterns.db ".schema patterns"`) uses:
`id INTEGER PRIMARY KEY AUTOINCREMENT, pattern_hash TEXT UNIQUE, pattern_type TEXT, title TEXT, content TEXT, metadata TEXT, source_profile TEXT, source_session TEXT, tags TEXT, created_at INTEGER, updated_at INTEGER, access_count INTEGER, last_accessed INTEGER`
with `pattern_hash` unique (NOT `pattern_id`). Don't "fix" the DB. Use the working inline method in `references/memory-offload-live-schema.md`, or update the helper to the live columns (`INSERT OR REPLACE INTO patterns (pattern_hash, pattern_type, title, content, metadata, source_profile, tags, created_at, updated_at, access_count) VALUES (?,?,?,?,?,?,?,?,?,0)` with `pattern_hash = sha256("hermes_memory:<target>:<content>")`).

## Solution — EXPANDED TO UNIVERSAL KB

Offload memory entries to the **ENI Knowledge Base** at `~/.eni/kb/` which now has:

### Original Offload (Complete)
- `patterns.db` — Hermes memories offloaded (30 entries)
- `skills.db` — Skills, patterns, sessions
- Daemon on port 8765 with MCP/LSP servers
- Auto-offload cron at 90% threshold (hourly)

### Universal KB Expansion (Complete)
**New: `lib/hermes_kb_universal.py`** — Multi-database architecture:
- `patterns.db` — All knowledge patterns (memories, tool results, commands, skills, configs, sessions)
- `skills.db` — Hermes skills registry with metadata
- `sessions.db` — Session tracking with statistics
- `operations.db` — Every operation (tools, commands, file ops, git, tests, skill loads)
- `vectors.db` — Ready for embeddings

**Captures EVERYTHING Hermes Does:**
- All 15 tool executions (bash, file_read, file_write, file_edit, glob, grep, task_*, agent, web_*, mcp, lsp)
- All 24 command executions (/help, /commit, /review, /compact, /config, /doctor, /memory, /skills, /tasks, /diff, /cost, etc.)
- File operations (read, write, edit, delete, create)
- Git commits, test results, skill loads, config changes
- Full session transcripts

### MCP Server (Complete)
**New: `lib/mcp_kb_server.py`** — 15 MCP tools exposed via stdio/HTTP

### LSP Server (Complete)
**New: `lib/lsp_kb_server.py`** — Full LSP support (hover, definition, references, completions, diagnostics)

### ENI Mini Context (Complete)
**New: `lib/eni_kb_context.py`** — Unified client for minis

### Auto-Capture (Complete)
**New: `lib/hermes_auto_capture.py`** — Monkey-patches Hermes internals

## Memory Entry Format

Hermes memory entries (from MEMORY.md) are declarative facts:
```markdown
- "User prefers concise responses"  (target: user)
- "Project uses pytest with xdist"  (target: memory)
```

## Storage Strategy

### Option 1: Patterns Table (Recommended)
Store each memory as a pattern with `source_type = 'hermes_memory'`:

```sql
INSERT INTO patterns (
    pattern_id, name, category, description, verb, noun,
    params, required, example, execution_mode, entrypoint,
    python_handler, http_endpoint, source_files, source_type,
    confidence, metadata, extracted_at, forged, skill_id
) VALUES (
    'hermes_mem_<hash>', 'Memory: <summary>', 'hermes_memory',
    '<full memory content>', 'remember', 'fact',
    '{}', '[]', '', 'passive', '',
    '', '', '', 'hermes_memory',
    1.0, '{"target": "user|memory", "original_entry": "..."}',
    <timestamp>, 0, NULL
);
```

### Option 2: Skills Table
Store as skills with `skill_id` prefix `hermes_memory_`:

```sql
INSERT INTO skills (
    skill_id, glyph, verb, noun, description, dsl_spec,
    mcp_schema, lsp_capability, execution_mode, entrypoint,
    python_handler, http_endpoint, wenyan_hash, rtk_hash,
    pxpipe_png, created_at, updated_at, pattern_signature,
    usage_count, fitness
) VALUES (
    'hermes_memory_<hash>', '', 'remember', 'fact',
    '<full memory content>', '{}', '{}', '{}',
    'passive', '', '', '', '', '', '',
    <timestamp>, <timestamp>, '', 0, 0.0
);
```

## Python API

```python
from lib.hermes_memory_kb import HermesMemoryKB

kb = HermesMemoryKB()

# Offload all memory entries
kb.offload_all()

# Offload specific entries
kb.offload_entries([
    {"content": "User prefers concise responses", "target": "user"},
    {"content": "Project uses pytest with xdist", "target": "memory"},
])

# Search offloaded memories
results = kb.search("pytest")
for r in results:
    print(r["description"])

# Restore to Hermes memory
kb.restore_to_hermes(max_entries=50)
```

## Capturing PROJECT LEARNINGS (not just memory) — the durable store_pattern pattern

The strongest use of the KB is capturing REUSABLE technical lessons so future
builds are faster. The canonical write path is `hermes_kb_universal.store_pattern`
(it writes to the LIVE `~/.eni/kb/patterns.db`), NOT ad-hoc SQL — the live
patterns table uses columns `pattern_hash, pattern_type, title, content,
metadata, source_profile, source_session, tags`, which do NOT match the older
`extractor.py` schema. Never INSERT into it directly; go through the API.

```python
import sys, os
sys.path.insert(0, r"/home/hunter/Desktop/Enterprise Builder/ENI_Swarm_NEW/lib")
from hermes_kb_universal import store_pattern, search_patterns

pid = store_pattern(
    pattern_type="acpeso_project",   # category: project / system_admin / hermes
    title="Download-gate pattern: like/comment verified server-side",
    content="<the full reusable lesson, prose, ~200-500 chars>",
    metadata={"domain": "AC PE$0 site", "saved": "2026-08-02"},
    profile="default",
    session="acpeso-capture-2026-08-02",
    tags=["gate", "soundcloud", "anti-abuse"],
)
```

KEY properties:
- **Idempotent** — `store_pattern()` hashes `pattern_type:title:content` and on a
  duplicate just bumps `access_count` + returns the SAME id (no new row). So a
  permanent "capture seed" script can be re-run safely every session.
- **Verify retrievability**, don't assume: `search_patterns(query="stripe")` returns
  dicts with `.get('title')`/`.get('id')`. If a search you'd expect to hit doesn't,
  the pattern may be missing or under a different pattern_type — fix it.
- **Store the technique + the root cause + the FIX**, not the one-off narrative.
  A reusable lesson names the durable rule (e.g. "normalize relative URLs before
  handing to a third-party API", "dynamic HTML must be no-store or it goes stale").
- Build a **permanent capture script** (`capture_acpeso.py` style) that accumulates
  every `add()` call, keep it idempotent, and re-run it after any notable build so
  the KB grows without duplicating.
- This is how "add everything useful we built to our knowledge base so we can build
  programs better in the future" is executed in practice.

## CLI Usage

```bash
# Offload all current Hermes memory to ENI KB
hermes-memory-kb offload

# Offload only user-profile memories
hermes-memory-kb offload --target user

# Search offloaded memories
hermes-memory-kb search "prefers"

# Restore memories to Hermes (merges with existing)
hermes-memory-kb restore --max 50

# Show stats
hermes-memory-kb stats

# Auto-offload when memory > 90% full (add to cron)
hermes-memory-kb auto-offload --threshold 90
```

## Automatic Offload (Cron)

Add to crontab:
```bash
# Every hour, check memory usage and offload if >90%
0 * * * * /home/hunter/.hermes/scripts/hermes_memory_kb_offload.py auto --threshold 90
```

## Integration with Hermes

The Hermes `memory` tool can be extended to:
1. Check memory usage before `add`
2. Auto-offload oldest entries when >90% full
3. Search KB when memory search fails
4. Restore on session start

## Schema for Hermes Memory Pattern

```python
HERMES_MEMORY_PATTERN = {
    "pattern_id": "hermes_mem_<sha256(content)[:12]>",  # Unique ID
    "name": "Memory: <first 50 chars of content>",
    "category": "hermes_memory",
    "description": "<full memory content>",
    "verb": "remember",
    "noun": "fact",
    "params": "{}",
    "required": "[]",
    "example": "",
    "execution_mode": "passive",
    "entrypoint": "",
    "python_handler": "",
    "http_endpoint": "",
    "source_files": "",
    "source_type": "hermes_memory",
    "confidence": 1.0,
    "metadata": '{"target": "user|memory", "session": "<session_id>", "timestamp": <unix>}',
    "extracted_at": <unix_timestamp>,
    "forged": 0,
    "skill_id": None,
}
```

## Files

- `~/Desktop/Enterprise Builder/ENI_Swarm_NEW/lib/hermes_kb_universal.py` — Main module (CANONICAL, verified 2026-08-02). NOTE: the older `~/Desktop/Projects/ENI_Swarm_NEW/lib/` path listed in older docs is EMPTY/not a real lib dir anymore — do NOT point there.
- `~/Desktop/Enterprise Builder/ENI_Swarm_NEW/lib/hermes_memory_kb.py` — Memory-specific KB helper
- `~/.hermes/scripts/hermes_memory_kb_offload.py` — CLI script (NOTE: uses OLD extractor schema — a `patterns.db` with `pattern_id/name/category/description`. The LIVE `~/.eni/kb/patterns.db` now uses `pattern_hash/pattern_type/title/content`. Do NOT INSERT via that old schema; use `hermes_kb_universal.store_pattern`.)
- `~/.hermes/scripts/hermes_kb.py` — **CANONICAL Hermes bridge** (wrapper over `hermes_kb_universal`, VERIFIED 2026-08-03): `offload | save | search | stats | auto`. Use THIS for memory/chat/lesson persistence to the LIVE db.
- `~/.eni/kb/patterns.db` — Live pattern KB (pattern_hash, pattern_type, title, content, metadata, source_profile, source_session, tags, ...)
- `~/.eni/kb/skills.db` — Skills + glyphs registry
- `~/Desktop/Enterprise Builder/ENI_Swarm_NEW/capture_acpeso.py` — Example idempotent project-capture seed script

## VERIFIED Hermes <-> KB bridge (2026-08-03)

**STOP using ad-hoc SQL.** Use the canonical universal-lib path so writes land in the
LIVE `~/.eni/kb/patterns.db` with the correct columns. Wrapper script:

```bash
python3 ~/.hermes/scripts/hermes_kb.py offload            # persist MEMORY.md+USER.md sections
python3 ~/.hermes/scripts/hermes_kb.py save --type user --title "T" --content "C" --tags a,b
python3 ~/.hermes/scripts/hermes_kb.py search "query"
python3 ~/.hermes/scripts/hermes_kb.py stats              # patterns_total / by_type
python3 ~/.hermes/scripts/hermes_kb.py auto               # cron: offload if memory changed
```

Direct lib usage (same effect):
```python
import sys; sys.path.insert(0, r"/home/hunter/Desktop/Enterprise Builder/ENI_Swarm_NEW/lib")
from hermes_kb_universal import store_pattern, search_patterns, offload_hermes_memory
pid = store_pattern(pattern_type="hermes", title="...", content="...", tags=["..."], profile="default", session="...")
res = search_patterns(query="...")
```

**Auto-offload cron (installed 2026-08-03):** every 5 min runs `hermes_kb.py auto`,
which offloads only when MEMORY.md/USER.md byte size changed (idempotent marker at
`~/.hermes/.kb_offload_marker`). So Hermes memory/chat/lessons persist to the KB
automatically forever.

**Workflow for future sessions:** whenever you'd add a Hermes memory, ALSO
`python3 ~/.hermes/scripts/hermes_kb.py save --type ... --title ... --content ...`
(or rely on auto-offload which snapshots MEMORY.md). To look something up from a past
lesson, `python3 ~/.hermes/scripts/hermes_kb.py search "..."`.


## Pitfalls & verified runtime behavior (2026-08-07)

- **The auto-cron's idempotency IS a byte-size sum, and that is correct.** `cmd_auto`
  computes `cur = os.path.getsize(MEMORY.md) + os.path.getsize(USER.md)` and compares it to
  the marker file `~/.hermes/.kb_offload_marker`. If equal it prints `no change, skip` and
  returns 0 — **do not treat that as a failure**; it means the current memory state is
  already persisted. Verified live: MEMORY.md 4988 + USER.md 2012 = 7000, marker `7000` →
  correctly skipped. Only when the sum changes does it re-offload and rewrite the marker.
- **A cron/scheduled directive may say to run the OLD script**
  (`cd .../Projects/ENI_Swarm_NEW && python3 -m lib.hermes_memory_kb auto --threshold 90`).
  That path/`__main__` module is dead (old extractor schema, empty lib dir). The ONLY live
  entry point is the installed cron `hermes_kb.py auto` (runs every 5 min per crontab).
  When a job instruction references the old invocation, run the canonical bridge instead.
- **Verify the offload landed, don't assume:** `hermes_kb.py stats` groups live `patterns.db`
  rows by `pattern_type`. Offloaded Hermes memories show up as counts under `memory` (46)
  and `user` (2) — NOT a `hermes_memory` type and NOT under `pattern_id/name/category`
  (that's the dead extractor schema). `patterns_total`/`operations_total` confirm global health.
  Sanity-level steady state seen: patterns_total≈139, operations_total≈126.
- **Reading the wrapper/script files:** read_file/terminal outputs here can come back mangled by
  the ENI output-compression overlay (a `carrier_*.png` + head/tail summary) and read_file's
  dedup can return `status:'unchanged'` with no `content` key (KeyError on `r['content']`).
  To get clean source, read through the shell instead:
  `python3 -c "print(open('/home/hunter/.hermes/scripts/hermes_kb.py').read())"` in terminal.
  Use that trick for any Hermes script/skill file in this environment.

## PITFALL — schema drift (the bundled script FAILS)

`~/.hermes/scripts/hermes_memory_kb_offload.py offload` raises
`table patterns has no column named pattern_id` on the live DB. The live
`patterns` schema uses `id` PK + `pattern_hash` UNIQUE (see
`references/memory-kb-schema-drift-fix.md` for the exact schema + a working
`INSERT OR REPLACE` snippet keyed on `pattern_hash`). If the script errors,
fall back to that snippet (run via execute_code), never assume the script works.

## Testing

```bash
# Test offload
cd ~/Desktop/Projects/ENI_Swarm_NEW
python -m lib.hermes_memory_kb offload

# Verify in KB — NOTE: live patterns.db schema uses id/pattern_hash/pattern_type/title/content,
# NOT pattern_id. The bundled offload script (~/.hermes/scripts/hermes_memory_kb_offload.py) is
# STALE against this schema and throws "table patterns has no column named pattern_id" — use the
# corrected INSERT in references/patterns-db-current-schema.md instead. See that ref for the live schema.
sqlite3 ~/.eni/kb/patterns.db "SELECT id, substr(title,1,50), pattern_type FROM patterns WHERE source_type='hermes_memory' ORDER BY id DESC LIMIT 10;"

# Test search
python -m lib.hermes_memory_kb search "concise"

# Test restore
python -m lib.hermes_memory_kb restore --max 10
```