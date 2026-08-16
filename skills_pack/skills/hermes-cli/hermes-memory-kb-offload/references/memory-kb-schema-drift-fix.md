# Hermes Memory → KB Offload — schema drift fix (patched in practice)

## Symptom
Running the bundled `~/.hermes/scripts/hermes_memory_kb_offload.py offload` fails:

```
sqlite3.OperationalError: table patterns has no column named pattern_id
```

## Root cause
The script targets an older `patterns` table schema. The LIVE schema at
`~/.eni/kb/patterns.db` has changed:

```sql
CREATE TABLE patterns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pattern_hash TEXT UNIQUE NOT NULL,
  pattern_type TEXT NOT NULL,      -- memory, user, tool_result, command_result, ...
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
```

There is no `pattern_id` / `pattern_hash`-as-id mismatch: the unique key is
`pattern_hash` and the PK is `id`.

## Working offload (correct schema)
Read the memory store (`~/.hermes/memories/MEMORY.md` with `§` separators,
`USER.md` for the user profile), hash each entry with
`sha256("hermes_memory:" + target + ":" + content)`, and `INSERT OR REPLACE`
into `patterns` using the live columns:

```python
import sqlite3, hashlib, json, time
from pathlib import Path
con = sqlite3.connect(str(Path.home()/".eni"/"kb"/"patterns.db"))
cur = con.cursor()
now = int(time.time())
for entry in entries:  # [{target, content}]
    h = hashlib.sha256(f"hermes_memory:{entry['target']}:{entry['content']}".encode()).hexdigest()
    cur.execute("""
      INSERT OR REPLACE INTO patterns
      (pattern_hash, pattern_type, title, content, metadata, source_profile, tags, created_at, updated_at, access_count)
      VALUES (?,?,?,?,?,?,?,?,?,0)
    """, (
      h, "hermes_memory",
      entry["content"].split(".")[0][:60] or entry["content"][:60],
      entry["content"],
      json.dumps({"target": entry["target"], "original_entry": entry["content"]}),
      "default", json.dumps(["memory","offload"]), now, now,
    ))
con.commit()
```

## Verify (don't assume)
```bash
sqlite3 ~/.eni/kb/patterns.db "SELECT substr(title,1,50), source_profile FROM patterns WHERE pattern_type='hermes_memory' ORDER BY id DESC LIMIT 6;"
```

## Note
Memory is ~5,000 char cap. When full, offload FIRST to ~/.eni/kb/patterns.db,
THEN trim the memory store, so nothing is lost. Idempotency comes from
`INSERT OR REPLACE` on `pattern_hash` — re-running is safe.
