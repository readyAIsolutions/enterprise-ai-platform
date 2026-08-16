# STATUS: Local One-Prompt-Program Controller (SLICE B)
**Repo:** /home/hunter/Desktop/Enterprise Builder/enterprise/local_controller/
**Date:** 2026-08-16
**State:** v1 working — live on :8913

## What this is
The local "brains" that make the platform feel magic: one natural-language goal
becomes a whole (tested, packaged) program, with private info handled LOCALLY only.
Exposes a tiny stdlib HTTP server (http.server on :8913, fallback :8914) that the
platform's hermes_controller / Hermes can call.

## Files
- vault.py         — local secret vault; `redact()` strips real secret values leaving
                     placeholder names so cloud models NEVER see real credentials.
- planner.py       — goal -> task DAG (epics -> steps) with deps + test hints, plus
                     `enrich_prompt` big-prompt expansion.
- build_provider.py— run_plan: executes each step (python worker or injected external
                     LLM with redaction), iterates on test failures (max 2 attempts),
                     writes artifacts + manifest under data/build_sessions/<id>/.
- controller.py    — local HTTP server: POST /plan, /enrich, /program; GET /health.
- tests/test_local_controller.py

## PASS / FAIL board (real numbers)
| Check | Result | Evidence |
|---|---|---|
| local_controller unit + endpoint tests | ✅ PASS | **11 passed, 0 failed, 0.54s** |
| /health responds | ✅ PASS | {"status":"ok","port":8913,"endpoints":[...]} |
| /plan decomposes a goal into >=4 steps with deps | ✅ PASS | "build a to-do web app with auth" -> 6 steps, each with deps[] + test_hint |
| /enrich expands a small prompt | ✅ PASS | source_length=14 -> enriched_length=597 |
| /program one-prompt->program | ✅ PASS | generated 6 artifacts; each log "attempts=1 final=test-passed"; manifest.json written |
| secret redaction | ✅ PASS | covered by vault tests in the 11 |
| builds persist to session dir | ✅ PASS | data/build_sessions/session_*/manifest.json + stepXX_*.py |

## Live evidence (REAL output)
POST /plan {"goal":"build a to-do web app with auth"} -> steps:6 with
feature order requirements_and_spec -> data_and_state_model -> core_logic ->
api_and_interface -> tests_and_validation -> packaging_and_readme and correct
dependency ordering (deps:[0], deps:[0,1,2], ...).
POST /program {"goal":"write a tiny hello module"} -> session_dir
data/build_sessions/session_1786912752 with 6 step01..step06 artifacts,
manifest.json, logs all "final=test-passed".

## What adds R (keep) / what to drop
- KEEP: redact-before-transmit guarantee; deterministic goal->DAG planner; fail-and-
  retry (<=2) loop keyed on test_hint; sessioned artifacts to disk; stdlib-only.
- DROP/DEFER: no external LLM is wired by default (build_provider uses pure-python
  workers + injected LLM hook). Real LLM generation per step is a clear next step to
  make /program produce real (not stub) code.

## UNVALIDATED
- Real external-LLM generation per step (only test-passing stub workers ran).
- Vault encryption at rest (plaintext JSON in data/ with 0600 — safe locally; harden
  with the OS keyring / AES in a later pass).
- Cross-process secret sharing with the multiplayer floor (placeholders exist, no
  wired handoff yet).