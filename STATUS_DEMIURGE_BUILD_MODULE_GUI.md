# STATUS_DEMIURGE_BUILD_MODULE_GUI.md

Pass: Live build-module GUI (per-project module usage, how/why, functions created)
Date: 2026-09-01

## What it is
A dark, single-page web GUI (stdlib-only, no deps) at http://127.0.0.1:8930 that shows,
for every build project/session: which enterprise modules are being used, HOW (on which
Hermes hook + tool), WHAT functions/classes were created, and WHY (each module's real
purpose). Starts from the plugin's `/gui` command; auto-refreshes live.

## PASS/FAIL board (real numbers, no stubs)
| Check | Result | Evidence |
|-------|--------|---------|
| Telemetry recorder (JSONL, append-only, fail-open) | PASS | enterprise/modules/telemetry/telemetry.py records module-use rows; store at data/build_sessions/module_usage.jsonl |
| Module purpose catalog (all 87 modules) | PASS | module_purpose.json maps every module to role + hook + why, generated from real docstrings |
| Stdlib web server | PASS | gui_server.py, ThreadingHTTPServer :8930, no pip deps |
| Renders real build sessions | PASS | 18 sessions from data/build_sessions/*/manifest.json (goals: timezone tool, pdf merger, hello module, …) |
| Functions parsed from real artifacts | PASS | 122 function/class defs scanned from session step .py files; per-step breakdown |
| Per-project module usage table | PASS | detail view shows Module / Role(how) / Hook / Why columns |
| Live telemetry → GUI loop | PASS | recorded 4 module rows (timezone session) → GUI attached eval_gate, model_router, codegen_audit, error_correction with how/why |
| Search/filter | PASS | typing "pdf" narrowed grid to exactly 1 card (Build a pdf merger); filter persists across refresh |
| Detail view navigation | PASS | back button works; auto-refresh pauses while detail open (no click race) |
| Plugin integration | PASS | enterprise plugin now registers /enterprise, /apply, /gui (3 commands) + pre_llm_call, on_session_start, post_tool_call, on_session_end hooks; enabled=True err=None |
| Telemetry path fix | PASS | _STORE resolves to enterprise/data/build_sessions (was off-by-one into parent dir); verified round-trip |
| Full test suite | PASS | 5128 passed, 1 skipped, 0 failed (138.5s) — telemetry module added, nothing broken |

## What's recorded per use / per project
Live rows (JSONL): ts, id, session, goal, module, hook, tool, why, detail.
GUI aggregates: per session = goal, created_at, status, steps (feature/attempts/passed/status),
functions (kind+name from each artifact), modules (name/role/hook/tool/why from telemetry +
module_purpose catalog).

## How it wires into Hermes
- `/gui` slash command → _plugin_start_gui() → Popen(gui_server.py :8930)
- post_tool_call hook → telemetry.record() for build-quality modules that are live (gates map)
- on_session_start → telemetry.set_context(session_id)
- pre_llm_call → surfaces live build-quality modules as grounding context

## Files added this pass
  enterprise/modules/telemetry/__init__.py        — telemetry module (self-registers, healthy)
  enterprise/modules/telemetry/telemetry.py       — recorder + reader (stdlib)
  enterprise/modules/telemetry/module_purpose.json— 87-module role/hook/why catalog
  enterprise/modules/telemetry/gui_server.py      — stdlib web GUI + API
  M enterprise/__init__.py                        — + /gui command, + post_tool_call telemetry hook, + telemetry imports

## UNVALIDATED
- Multi-Hermes concurrent telemetry (two agents writing the JSONL at once) not stress-tested
  (append is atomic line-writes; safe in practice).
- Full historical sessions still show 0 modules except the demo session, because they ran
  BEFORE telemetry existed — new builds will populate live. This is honest (no backfilled fake data).
- GUI not exposed beyond 127.0.0.1 (localhost only, secure default); reachable via browser on this box.