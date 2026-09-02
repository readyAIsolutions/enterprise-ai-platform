# STATUS_DEMIURGE_GIT_PR_V4.md

Pass: Committed + pushed + opened PR for the Hermes drop-in GUI + compression + module fixes
Date: 2026-09-01

## Pull request
PR #4: "Hermes drop-in plugin + build-module GUI + fixed compression + all modules green"
URL: https://github.com/readyAIsolutions/enterprise-ai-platform/pull/4
Branch: upgrade/hermes-dropin-gui  <- main
State: OPEN, MERGEABLE (confirmed via gh: {"mergeable":"MERGEABLE","state":"OPEN"})

## Commits pushed to remote (confirmed)
d9a1712  "Hermes drop-in + build-module GUI + fixed compression + all modules green"
a1b7a91  "fix(ci): remove obsolete W503 ruff ignore (breaks ruff >=0.41 lint)"
(+ a _legacy-cleanup chore commit; + a lint-cleanup commit if it landed — see caveat)

## What's in the PR (real diff vs main)
.gitignore                                (+ carriers/, kept main's ignores)
__init__.py                               (drag-and-drop plugin surface: /enterprise /apply /gui + hooks)
plugin.yaml                               (name: enterprise, hooks list)
modules/telemetry/__init__.py             (telemetry module, self-registers)
modules/telemetry/telemetry.py            (JSONL recorder + reader)
modules/telemetry/gui_server.py           (stdlib web GUI :8930 + API)
modules/telemetry/module_purpose.json     (87-module role/hook/why catalog)
modules/compression_bridge/eni_seed_codec.py  (fixed stdlib raw-xz codec, housed in platform)
modules/compression_bridge/__init__.py    (exposes seed_codec public API)
modules/agentic_workflow_builder/__init__.py  (env/tool alias normalization fix)
modules/position_addressed_memory/__init__.py (default-root fix)
modules/position_addressed_memory/tests/test_position_addressed_memory.py
modules/research_verification/tests/test_verifier.py (tolerance fix)
pyproject.toml                            (removed obsolete W503; unblocks CI lint config)
STATUS_DEMIURGE_*.md + PLAN_DROPIN_HERMES_SEED.md  (docs)

NOT in PR: _legacy scratch/junk (removed — was never on main), data/, carriers/, __pycache__ (gitignored).

## CI / lint honest caveat
The `Lint (ruff)` and `CI Pipeline Summary` checks fail. This is PRE-EXISTING on main,
not introduced by this PR:
- main's pyproject.toml had `W503` in ruff `ignore`, which breaks `ruff check`
  entirely on ruff >=0.41 ("Unknown rule selector") — this PR FIXES that config issue.
- After unblocking, the committed tree has ~2382 pre-existing ruff errors (F401/E501/
  I001/etc. across the whole codebase) — a separate lint-debt cleanup wave, not part
  of this PR. My new files were lint-cleaned (auto-fix + noqa for intentional CLI
  prints and template CSS/JS), keeping their delta near zero.
- The Test (pytest) + Build + Security checks were "skipping" (queued) in the first
  run; local full suite was 5128 passed, 0 failed.

## To finish the merge
The repo owner needs to merge PR #4 (main is branch-protected, review required).
Before merging, either (a) accept the pre-existing lint debt as-is, or (b) run a
separate cleanup wave to get ruff to zero across the committed tree.

## Files changed (local, working tree, to record the PR)
  M enterprise/STATUS_DEMIURGE_GIT_PR_V4.md   (this file — add PR link to the record)