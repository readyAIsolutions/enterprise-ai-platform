---
name: ruff-lint-gate-cleanup
description: >-
  Take a large codebase's lint/type/format checks to ZERO findings so a CI merge
  gate passes, using a fan-out swarm of parallel workers over disjoint file sets.
  Use when the user says "fix all the ruff errors / use the swarm to fix all / get
  lint clean / make the PR mergeable". Covers ruff (ANN*, ARG*, PTH*, UP*, SIM*,
  E402, B904, E722, F821...), mypy, and ruff format, plus the pitfalls of inline
  # noqa comments getting reflowed by the formatter, pytest fixture args that
  cannot be renamed, dead typing re-export shims, and distinguishing the real
  merge gate (often pytest) from advisory checks (continue-on-error).
---

# Ruff / Lint / Type-Check Gate Cleanup

Get every `ruff check` finding to 0 across a large, multi-module repo, keep
`ruff format` idempotent, don't regress pytest (usually the real merge gate), and
push. Best done with a **fan-out swarm over load-balanced, DISJOINT file groups** so
no two workers edit the same file.

## When to use
- User says "use swarm fix all", "fix the ruff errors", "get lint clean", "make
  the PR mergeable", "push the new version".
- A CI pipeline treats ruff/mypy as advisory (`continue-on-error: true`) but the
  user wants them genuinely at zero, not just under the threshold.

## The critical context: know the REAL merge gate
Read `.github/workflows/ci.yml` (or equivalent) FIRST. Common pattern:
- `pytest` is the hard gate.
- `ruff` and `mypy` run `continue-on-error: true` (advisory) — often non-strict
  (`mypy . --ignore-missing-imports`).
The user may still want advisory checks at zero. Always re-run pytest after lint
edits — that is what actually blocks the merge.

## Swarm fan-out pattern (the reliable way to do 1000+ findings)
1. Inventory: `git diff --name-only <base>~1 -- '*.py'` to get YOUR changed files
   (don't touch legacy files outside the diff — you didn't own them).
2. Per-file counts: `while read f; do n=$(ruff check "$f" 2>/dev/null | sed -n
   's/Found \([0-9]*\) errors.*/\1/p'); echo "$n|$f"; done < files.txt` (blank = 0).
3. Partition the NONZERO files into N load-balanced groups (greedy bin-pack by
   error count, N ~= your batch concurrency cap). Write each group to
   `/tmp/swarm_groups/group_N.txt` and a shared `STRATEGY.md`.
4. Fan out N `delegate_task` workers (batch mode), each with: its group file path,
   the STRATEGY.md path, and hard constraints (never change runtime behavior or
   public signatures; only edit files in YOUR group; run ruff to 0 then pytest on
   sibling tests; report before→after counts).
5. You (the orchestrator) close the stragglers — the swarm will leave a small tail
   (often `__init__.py` re-export shims, `# noqa` misplacement, single-line defs).
6. **Verify yourself — never trust worker self-reports.** Re-run
   `ruff check $(cat files.txt)` → must be `All checks passed!`, then the FULL
   pytest suite.

## Per-rule fix guidance (quick reference)
- **ANN401 (`Any` disallowed)**: prefer a precise type; where the value is genuinely
  runtime-dynamic (config values, signal `frame`, timestamps, validator payloads,
  arbitrary user data) keep `Any` and add `# noqa: ANN401`. `Any`→`object` is a
  format-stable alternative when the value is truly opaque. Prefer noqa over a wrong
  precise type.
- **ARG001/002/004/005 (unused args)**: rename with `_` prefix ONLY where safe
  (private helper, not a callback/abstract/override/serialized contract). For
  **pytest fixtures**: you CANNOT rename to `_` (breaks fixture injection by name) —
  keep the name and put `# noqa: ARG00x` on that exact arg line.
- **E402 (import not at top)**: intentional (optional-dep guards, sys.path tweaks).
  Add `# noqa: E402` on the line, don't reorder.
- **PTH (use pathlib)**: `os.path.join`→`Path / x`, `dirname`→`.parent`,
  `exists`→`.exists()`, `makedirs`→`Path.mkdir(parents=True, exist_ok=True)`,
  `open`→`Path.open/read_text/read_bytes`, `getsize`→`.stat().st_size`,
  `listdir`→`.iterdir()`, `splitext`→`.suffix`/`.stem`. Only convert where `os` isn't
  semantically required; else `# noqa`.
- **UP031 (`%` format)**: do NOT convert logging lazy-format strings — they're
  intentional. Convert real `%`→f-string in test/message code.
- **UP035/UP007**: migrate `Dict/List/Optional/Union` → dict/list/`X | None`/`A | B`
  where safe (py311 target-version). Remove the now-unused typing import.
- **B904**: `raise NewError(...)` inside except → add `from exc` (or `from None`).
- **E722**: `except:` → `except Exception:`.
- **F821 (undefined name)**: a REAL bug — add the import / define it. Run test to
  confirm it resolves.
- **PT009/011/012**: narrow `pytest.raises(Exception)` to the specific exception or
  add `# noqa: PT011`; use `pytest.raises` in pytest tests; restructure
  `pytest.raises` to hold only the call when there are multiple statements.
- **SIM102/105/113/115**: collapse nested ifs, `contextlib.suppress`, `enumerate`,
  wrap `open` in `with`.

## Pitfalls (each cost real time — internalize these)
1. **`ruff format` reflows multi-line signatures and MISPLACES inline `# noqa`
   comments onto the WRONG argument** (e.g. the noqa ends up on `protocol` but the
   actually-unused arg is `registry`), silently re-creating ARG001/ANN401 errors and
   breaking format-idempotency. AFTER any format run, re-lint AND re-check
   `ruff format --check` idempotency; inspect each misplaced noqa and move it to the
   correct arg's line (or the `def` line for the whole function).
2. **`Any`→`object` where truly opaque** is a format-stable ANN401 fix that survives
   reflow (unlike a trailing `# noqa` that the formatter can detach). Use it for
   `**kwargs`, dynamic config, signal `frame`.
3. **Dead typing re-export shims**: many module `__init__.py` files have
   `from typing import Any, Dict, Optional  # noqa: F401` purely as re-exports.
   Check no downstream code imports `Dict`/`Optional` from them; if none, collapse to
   `from typing import Any  # noqa: F401`. This is the classic swarm tail.
4. **Terminal/tool output can collapse long strings** (a long OpenAPI key shows as
   `sk-abc...0ABC`). When a test "should pass" but fails on string content, verify
   actual bytes with `od -c` / `git show HEAD:path` + `ast.literal_eval`, not by
   reading the collapsed display. Restoring a "cleaner-looking" short string can
   break a regex match.
5. **mypy `Source file found twice under different module names`** is often an
   environment/path-mapping artifact (conftest inserts sys.path so a root module
   resolves as both `<module>` and `<package>.<module>`), NOT a real type error from
   your edits. Confirm against the diff scope before chasing it; CI runs it advisory.
6. **`python` may not be on PATH** (only `python3`/`pytest`). Use `pytest` / `python3`
   directly and run the suite in the background with notify-on-complete.

## Verification checklist (run in order, BEFORE commit)
1. `ruff check $(cat files.txt)` → `All checks passed!` (0 errors).
2. `ruff format --check $(cat files.txt)` → all already formatted (idempotent).
3. Full `pytest -q` → green at the baseline count, no regressions.
4. `git status --short` → only your intended files changed, no stray non-.py files,
   no worker touched outside its group (compare changed set vs assigned set).
5. Commit with a message summarizing the rules fixed + the before→after count, and
   note the merge gate (pytest) status. Push to the same branch.

The swarm reasoning convention: end worker task contexts/summaries with a CRITICAL
block (what I understood / approach / what changed file-by-file / issues+noqa
reasons / verification with real numbers) so the orchestrator gets verifiable
self-reports and each worker actually runs its own checks.

## Linked files
- `references/swarm-fanout-recipe.md` — concrete commands + partition script +
  delegate_task batch layout for the whole fan-out flow (inventory, load-balanced
  disjoint groups, fan-out, tail-closing, verification). Reach for this when
  starting a fresh cleanup so you don't re-derive the mechanics.

