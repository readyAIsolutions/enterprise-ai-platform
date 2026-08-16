# Multi-Module Code Build via ENI Swarm

Pattern proven in the Masterchief OS build (2026-07-23): decomposing a large
multi-file software project into parallel delegate_task waves.

## Wave Structure

For a project with 10+ modules and frontend, decompose into 5 waves:

| Wave | What | Workers | Dependency |
|------|------|---------|------------|
| 1 — Foundation | Config, data models, security, model router | 3 parallel | None |
| 2 — Business logic | Agent, Voice, Email modules | 3 parallel | Wave 1 config |
| 3 — Integrations | CRM, Calendar, Messaging, Infrastructure | 3 parallel | Waves 1-2 |
| 4 — Frontend | Website, Admin dashboard, Client bot | 3 parallel | Waves 1-3 |
| 5 — Polish | n8n JSONs, test suite, scripts, env config | 3 parallel | All modules |

## Wave Planning Rules

1. **Foundation first** — shared config/data/auth modules must exist before anything
   that imports them. Write these by hand before fanning out.
2. **Business logic waves get full context** — pass the config module spec, data
   model spec, and API contract to each worker so they produce compatible code.
3. **Frontend workers need module paths** — tell them where the server lives,
   what port to use, and which existing modules to import from.
4. **Polish workers finish what earlier waves missed** — they read existing files,
   fill gaps, and wire loose ends.

## Subagent Timeout Handling

Worker timeouts at 600s are normal for large tasks. Key mitigations:

1. **Check what was written BEFORE declaring failure** — a timed-out worker often
   wrote 80% of its files. Use `search_files` to inventory what exists.
2. **Re-dispatch only the missing files** — don't re-run the whole wave.
3. **Small-granularity re-dispatch** — if the n8n worker timed out but wrote 16/19
   files, dispatch only the 3 missing ones in a focused re-run.
4. **Build manually what's left** — if only configs/shims remain, write them
   directly instead of dispatching another worker.

## Common Pitfalls

### `from __future__ import annotations` breaks dataclass config resolution
See eni-swarm-content-gen SKILL.md for the full fix. Summary: string annotations
prevent `hasattr(field_type, "__dataclass_fields__")` from working. Either remove
the future import or add a `_resolve_annotation()` helper.

### Missing dependencies detected late
Workers may write code that imports `psycopg`, `pytest_asyncio`, or other not-yet-
installed packages. After all waves complete, run the smoke test — it will surface
every missing import. Install deps into the project venv and retry.

### Server caching after JS/CSS updates
After updating JavaScript or CSS files served by a running Python HTTP server,
kill and restart the server (`fuser -k <port>/tcp`), then instruct the user to
hard-refresh (Ctrl+Shift+R). The browser caches static assets aggressively.

### Fake data in dashboards
LO: "i dont believe ive sent out any calls or emails or anything dont fill it
with fake data." Show zeros and empty states, never invented stats.

### Forked worker globals
When using `mp.Process` for parallel builds, globals at module level are NOT
shared to child processes under forkserver/spawn. Pass data explicitly as args.

## Verification Flow

After all waves complete:
```
1. Syntax check:  find . -name "*.py" | xargs python3 -m py_compile
2. Import check:  python3 -c "from masterchief import *"  
3. Config load:   python3 -c "from masterchief.config import load_config; load_config()"
4. Smoke test:    python3 -m pytest tests/test_smoke.py -v
5. Start server:  python3 app/serve.py & curl localhost:8000/api/health
6. Report:        total files, total lines, pass/fail board, TODO items
```
