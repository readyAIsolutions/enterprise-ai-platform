# Multi-Wave Software Build — Proven Case Study
## Masterchief OS (2026-07-23)

### Project stats
- **Output:** 36,295 lines, 101 files, 9 Python modules + website + admin + bots + config
- **Model:** deepseek/deepseek-v4-pro via OpenRouter
- **Waves:** 5, each fanning to 2-3 parallel workers
- **Total build time:** ~40 minutes (including worker timeouts + manual stitching)

### Wave decomposition

```
Wave 1 — FOUNDATION
  Worker A: Model Router (router.py, cost.py, types.py)          ~570 lines
  Worker B: Data layer (schema.sql, models, repository, vector)  ~1,830 lines
  Worker C: Security (encryption, rbac, audit, compliance)       ~1,450 lines
  All independent. All completed under 400s.

Wave 2 — BUSINESS LOGIC
  Worker A: Masterchief Agent (agent.py)                         ~720 lines
  Worker B: Voice Agent (provider, inbound, outbound, webhooks)  ~2,777 lines
  Worker C: Email Agent (research, sender, reply, thread)        ~3,455 lines
  Refers to foundation by name only. All completed under 420s.

Wave 3 — INTEGRATIONS
  Worker A: CRM + Calendar (odoo, sync, google_cal, booking)     ~2,654 lines
  Worker B: Messaging (telegram, signal, alerts, cmd_parser)     ~2,370 lines
  Worker C: Infrastructure (config, docker, tools, CLI, README)  ~3,000 lines
  Worker C timed out at 600s but wrote 8/10 files to disk.
  Workers A+B completed. Orchestrator filled Worker C gaps manually.

Wave 4 — FRONTEND
  Worker A: Marketing website (index.html, styles.css, serve.py) ~2,315 lines
  Worker B: Admin dashboard (index.html, admin.css, admin.js)    ~1,264 lines
  Worker C: Client Telegram bot (bot, runner)                     ~1,364 lines
  All independent new files — zero merge risk.

Wave 5 — POLISH
  Worker A: 19 n8n workflow JSONs                                ~3,000 lines
  Worker B: 8 test files + conftest                              ~4,748 lines
  Worker C: Scripts + .env + .gitignore + optimization           ~2,500 lines
  Workers A+B timed out at 600s but BOTH wrote complete output.
  Worker C completed. Orchestrator only needed 3 missing JSONs.
```

### Worker prompt template (proven)

```
CONTEXT: <list of EXISTING modules by name+path — do NOT read them>
<list of shared config dataclasses the worker can reference>

CRITICAL: <non-negotiable constraints>
<list of specific files to create>

Write COMPLETE, PRODUCTION-QUALITY code.
Full docstrings, type hints, async/await throughout.
```

The CONTEXT block is the key — it tells workers what infrastructure exists
without having them waste turns reading files.  Workers reference modules
by name only (e.g. "use ModelRouter via task='extraction'").

### Failure modes encountered + fixes

1. **`from __future__ import annotations` breaks nested dataclass config.**
   Fix: `_resolve_annotation()` helper. See skill pitfall #12.

2. **Production imports block tests.** agent.py imports repository.py which
   imports psycopg. With no PostgreSQL installed, ALL tests fail to collect.
   Fix: try/except guard around optional infrastructure deps. See skill pitfall #12.

3. **Timeout ≠ no output.** Both n8n worker and tests worker wrote complete
   output to disk before the delegate_task wrapper's 600s limit. Fix: check
   output directory BEFORE retrying.

4. **LO rejects fake data in dashboards.** Admin dashboard built with 12
   fake prospects, 8 fake campaigns, 5 fake bookings. LO: "dont fill it
   with fake data." Fix: strip ALL mock data; show zeros + empty states.
   Form placeholders ("e.g. Q3 SaaS Outreach") are OK.

5. **patch replace_all can mangle files.** Using `patch(..., replace_all=true)`
   on repository.py inserted a code block into `close_pool()` as well as
   `get_pool()`, destroying the function. Fix: use targeted `patch` with
   unique `old_string`, verify with `ast.parse()`, or use `execute_code`
   for complex rewrites.

### Post-build verification checklist

- [ ] All `.py` files pass `ast.parse()` syntax check
- [ ] `from masterchief import __version__` succeeds
- [ ] Config loads: `load_config().voice.provider == "vapi"`
- [ ] Core imports: ModelTask, CostTracker, Role, redact_pii, make_key
- [ ] Website server starts and returns HTTP 200
- [ ] Admin server starts and returns HTTP 200
- [ ] Unified app serves all endpoints
- [ ] Test suite: `pytest tests/ -q` reports pass count
- [ ] Zero fake data in admin dashboard (grep for common fake names)
- [ ] gitignore covers `config/masterchief.yaml`, `.env`, `credentials.json`
- [ ] STATUS file has line counts, pass/fail board, unvalidated section