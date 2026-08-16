# Live `patterns.db` schema + corrected offload (2026-08-11)

The bundled offload script (`~/.hermes/scripts/hermes_memory_kb_offload.py`) and the
SKILL.md examples reference an OLD schema (`pattern_id`, `name`, `category`) that no
longer matches the live database. Running it now fails with:

```
sqlite3.OperationalError: table patterns has no column named pattern_id
```

## Current live schema (`~/.eni/kb/patterns.db`)

```sql
CREATE TABLE patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_hash TEXT UNIQUE NOT NULL,
    pattern_type TEXT NOT NULL,      -- memory, user, tool_result, command_result, file_op, git_commit, test_result, skill, config, session
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT,                   -- JSON
    source_profile TEXT,
    source_session TEXT,
    tags TEXT,                       -- JSON array
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    access_count INTEGER DEFAULT 0,
    last_accessed INTEGER
);
CREATE INDEX idx_patterns_type ON patterns(pattern_type);
CREATE INDEX idx_patterns_hash ON patterns(pattern_hash);
CREATE INDEX idx_patterns_profile ON patterns(source_profile);
CREATE INDEX idx_patterns_created ON patterns(created_at);
```

## Correct working offload (memory files → patterns.db)

Memory files: `~/.hermes/memories/MEMORY.md` and `~/.hermes/memories/USER.md` (also
profile copies under `~/.hermes/profiles/<name>/memories/`). Entries are `§`-separated.

```python
import sqlite3, hashlib, json, time
from pathlib import Path
pattern_db = Path.home()/".eni"/"kb"/"patterns.db"
mem  = Path.home()/".hermes"/"memories"/"MEMORY.md"
user = Path.home()/".hermes"/"memories"/"USER.md"

def entries(path, target):
    if not path.exists(): return []
    return [{"target": target, "content": p.strip()}
            for p in path.read_text().split("§") if p.strip()]

rows = entries(mem, "memory") + entries(user, "user")
con = sqlite3.connect(pattern_db); cur = con.cursor(); now = int(time.time())
for e in rows:
    h = hashlib.sha256(f"hermes_memory:{e['target']}:{e['content']}".encode()).hexdigest()
    cur.execute("""
        INSERT OR REPLACE INTO patterns
        (pattern_hash, pattern_type, title, content, metadata, source_profile, tags, created_at, updated_at, access_count)
        VALUES (?,?,?,?,?,?,?,?,?,0)""",
        (h, "hermes_memory", e["content"].split(".")[0][:60], e["content"],
         json.dumps({"target": e["target"]}), "default", json.dumps(["memory","offload"]), now, now))
con.commit()
print("offloaded", con.execute("SELECT COUNT(*) FROM patterns WHERE source_profile='default' AND pattern_type='hermes_memory'").fetchone()[0])
con.close()
```

`INSERT OR REPLACE` keyed on `pattern_hash` makes it idempotent (re-runs update, no dups).

## Verifying the offload actually persisted (retrievability, not assumption)

```bash
sqlite3 ~/.eni/kb/patterns.db \
  "SELECT id, substr(title,1,40) FROM patterns WHERE pattern_type='hermes_memory' AND source_profile='default' ORDER BY id DESC LIMIT 10;"
```

## Workflow note (LO preference)
When Hermes persistent memory fills up (5,000 char cap), LO's standing expectation is to
offload to this KB rather than silently dropping entries. Run the corrected snippet above
the same session the memory hit ~90%+, then you are free to prune/consolidate the in-Hermes
copy knowing it is preserved.
