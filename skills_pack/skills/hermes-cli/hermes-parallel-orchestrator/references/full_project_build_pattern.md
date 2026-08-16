# Full Software Project Build Pattern (ENI Swarm — Code Builds)

Captured from the Masterchief OS build session (2026-07-23). This is the pattern
for building complete multi-module software projects using parallel delegate_task
workers.

## When to Use

- Building a complete software platform from a detailed spec/roadmap
- Multi-module Python projects with interdependent packages
- Projects requiring 50+ files across 10+ directories
- User says "use eni swarm full power" or "fully build this"

## Wave Decomposition

Break the project into **independent waves** — each wave fans out 2-3 parallel
workers that don't depend on each other's output.

### Wave 1: Foundation (data + config + shared types)
- **Worker A**: Data models + database schema (SQLAlchemy/dataclasses + DDL)
- **Worker B**: Configuration system + env loading
- **Worker C**: Shared types/enums + utility modules

These are INDEPENDENT — each worker only needs the project spec, not the others'
output. Write all three simultaneously.

### Wave 2: Core Logic (business domain modules)
- **Worker A**: Core agent/business logic
- **Worker B**: Integration layer A (e.g., voice/calling)
- **Worker C**: Integration layer B (e.g., email/messaging)

These depend on Wave 1's config and data types but NOT on each other. Workers
should import from the project structure but can stub any missing peer modules.

### Wave 3: Integration + Infrastructure
- **Worker A**: External service integrations (CRM, calendar, etc.)
- **Worker B**: Messaging/notification layer
- **Worker C**: Docker + deployment + config YAMLs

### Wave 4: Frontend (if applicable)
- **Worker A**: Marketing/landing website
- **Worker B**: Admin dashboard/control panel
- **Worker C**: Client-facing interfaces (bots, widgets)

### Wave 5: Polish + Tests
- **Worker A**: Test suite (all modules)
- **Worker B**: Scripts (setup, launch, health checks)
- **Worker C**: Final integration + docs + STATUS

## Worker Prompt Template

Every worker needs the SAME context. Copy-paste this structure:

```
Project: <name> at <absolute path>
Existing modules: [list what's already built, with brief descriptions]
DO NOT read existing files — reference them by name and interface only.

CREATE:
1. <path> — <description with EXACT interface requirements>
2. <path> — <description>
...

Write COMPLETE, PRODUCTION-QUALITY code with docstrings, type hints, async.
```

## Critical Guardrails

1. **Config-first architecture** — Wave 1 MUST include the config module.
   Workers in later waves import from it. Without this, every worker invents
   its own config convention.

2. **Explicit module interfaces** — Every worker prompt must specify EXACTLY
   what functions/classes/methods each file exports. "Build the voice module"
   is too vague. "Build VoiceProvider ABC with create_call/get_status/end_call
   abstract methods, plus VapiProvider and MockProvider implementations" is
   correct.

3. **No fake data rule** — Workers building admin dashboards or demo interfaces
   must NOT populate them with invented sample data. Empty states with zeros
   and "No data yet" messages are the default. LO will reject fake data.

4. **Post-wave smoke test** — After each wave completes, syntactically verify
   every file and run import checks before dispatching the next wave.

5. **Parallel within waves, sequential across waves** — Never dispatch Wave N+1
   until Wave N's smoke test passes. Foundation bugs cascade.

## Common Failure Modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| Tests ERROR on collection | Production module imports psycopg/redis at module level | Make external-service imports optional with try/except |
| Config loads as dict, not dataclass | `from __future__ import annotations` stringifies type hints | Add `_resolve_annotation()` helper or remove the import |
| Worker times out at 600s | Too many files specified in one worker prompt | Cap at ~8 files per worker, split into sub-waves |
| BaseRepository not defined | Earlier patch mangled the file, deleting the base class | Always re-verify file syntax with ast.parse() after patching |

## Model Selection

For code-build workers:
- **deepseek/deepseek-v4-pro** — Best for large code generation, long context
- **anthropic/claude-sonnet-4** — Better for architecture and reasoning-heavy modules

Workers will exhaust tokens fast. Budget ~150K-300K input tokens per worker
for a full module build. The Stitcher (you, the orchestrator) should use
the cheapest available model — you're just verifying and routing.

## Verification Checklist

After ALL waves complete:

```
[] All .py files pass ast.parse() syntax check
[] All config YAML files parse with yaml.safe_load()
[] All JSON files parse with json.load()
[] Core module imports succeed (from masterchief.config import load_config)
[] Config loads as proper dataclass (cfg.voice.provider == "vapi", not AttributeError)
[] Smoke test: 10+ core assertions pass
[] Server boots and responds with HTTP 200
[] No fake/mock data in any dashboard or status display
[] STATUS file written with PASS/FAIL board
[] Total line count reported
```

## Session Reference

Built: Masterchief OS (~/Desktop/masterchief/) — 101 files, 36,295 lines
Time: ~40 minutes across 5 waves of 3 parallel workers each
Model: deepseek/deepseek-v4-pro via OpenRouter