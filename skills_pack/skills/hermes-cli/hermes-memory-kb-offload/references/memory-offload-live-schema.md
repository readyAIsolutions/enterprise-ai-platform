# Working Hermes Memory → KB Offload (live schema)

When Hermes memory is full (5,000-char cap), dump entries into the ENI knowledge base
`~/.eni/kb/patterns.db`. The bundled helper script is stale — this inline method matches the
live `patterns` table and is idempotent (INSERT OR REPLACE on a content hash).

## Where memory lives
- Default profile: `~/.hermes/memories/MEMORY.md` (entries separated by `§`)
- User profile: `~/.hermes/memories/USER.md` (target = "user")
- Profile-specific variant: `~/.hermes/profiles/<name>/memories/MEMORY.md`

## Inline offload (run via execute_code / python)

```python
import sqlite3, hashlib, json, time
from pathlib import Path

pattern_db = Path.home()/".eni"/"kb"/"patterns.db"
mem = Path.home()/".hermes"/"memories"/"MEMORY.md"
user = Path.home()/".hermes"/"memories"/"USER.md"

def read_entries(path, target):
    if not path.exists(): return []
    parts = [p.strip() for p in path.read_text().split("§") if p.strip()]
    return [{"target": target, "content": p} for p in parts]

entries = read_entries(mem, "memory") + read_entries(user, "user")
con = sqlite3.connect(pattern_db); cur = con.cursor(); now = int(time.time())
for e in entries:
    content = e["content"]
    h = hashlib.sha256(f"hermes_memory:{e['target']}:{content}".encode()).hexdigest()
    cur.execute("""
        INSERT OR REPLACE INTO patterns
        (pattern_hash, pattern_type, title, content, metadata, source_profile, tags, created_at, updated_at, access_count)
        VALUES (?,?,?,?,?,?,?,?,?,0)
    """, (h, "hermes_memory", content.split(".")[0][:60], content,
          json.dumps({"target": e["target"], "original_entry": content}),
          "default", json.dumps(["memory","offload"]), now, now))
con.commit()
cur.execute("SELECT COUNT(*) FROM patterns WHERE source_profile='default' AND pattern_type='hermes_memory'")
print("hermes_memory rows (default):", cur.fetchone()[0])
con.close()
```

## Verify retrievability (don't assume)
```sql
sqlite3 ~/.eni/kb/patterns.db \
  "SELECT substr(title,1,50) FROM patterns WHERE pattern_type='hermes_memory' AND source_profile='default' ORDER BY id DESC LIMIT 8;"
```

## Notes
- Idempotent: re-running upserts the same rows by hash (bumps nothing because INSERT OR REPLACE
  rewrites; safe to re-run each session).
- After offload you may free space in memory normally; the KB is the durable copy.
- Patterns live across skills.db / patterns.db / sessions.db / vectors.db in the universal KB layout.
