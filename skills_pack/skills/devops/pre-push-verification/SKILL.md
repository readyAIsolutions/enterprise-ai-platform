---
name: pre-push-verification
description: >-
  Mandatory pre-git-push checklist for ANY project with CI. Run every time before
  `git push` so lint, format, and the test gate are green and nothing is half-fixed.
  Encodes the ruff/mypy/pytest/format verification loop proven out on the
  enterprise-ai-platform repo (and the pitfalls: formatter reflowing # noqa onto the
  wrong arg, and restoring test strings that silently break regex-matcher tests).
---

# PRE-PUSH VERIFICATION

Triggers on: any `git push`, any "push to git", "commit and push", "make it mergeable",
or before opening a PR. Do this EVERY time — never push blind.

## 1. Snapshot what changed
```bash
cd <repo>
git diff --name-only HEAD -- '*.py' > /tmp/prepush_files.txt
wc -l /tmp/prepush_files.txt          # know your scope
git status --short | grep -vE '\.py$' # should be empty (no stray non-py files)
```

## 2. Ruff lint -> 0 errors
```bash
ruff check $(cat /tmp/prepush_files.txt)
```
Must print `All checks passed!`. If not, fix. Full enabled rule set (F,E,W,I,N,C4,B,SIM,
EM,RET,RSE,TID,TCH,ARG,PTH,T20,PT,UP,ANN). CI often runs ruff `continue-on-error`, but the
user's quality bar ("fix all") wants a real 0. Only suppress with `# noqa` where the rule
genuinely can't be satisfied (see pitfalls).

## 3. Ruff format -> idempotent
```bash
ruff format --check $(cat /tmp/prepush_files.txt)
```
If it says "N files would be reformatted", run `ruff format` on them, THEN re-run `ruff check`
— formatting reflow can orphan/misplace inline `# noqa` comments (critical pitfall #1 below).

## 4. pytest (the real merge gate) -> all pass
```bash
pytest -q -p no:cacheprovider
```
Run the FULL suite, not just the touched files. Note: on this box use `pytest` (python3
has no `python` alias). A failure in a file you edited means you broke it — fix it.

## 5. mypy (advisory in CI) -> no NEW errors
Run it the way CI does: `mypy . --ignore-missing-imports`. Note the pre-existing
platform_kernel double-mapping artifact (`enterprise.platform_kernel` vs `platform_kernel`
via conftest sys.path juggling) — it's an environment quirk, not something your edits
caused, and CI treats mypy as `continue-on-error`.

## 6. Scope check (swarm/multi-worker safety)
Confine edits to the intended file set. If you fanned out a swarm, verify no worker touched
files outside its group (overlapping edits = lost work / corruption):
```bash
comm -23 <(git diff --name-only HEAD -- '*.py' | sort -u) <(cat /tmp/prepush_files.txt | sort -u)
# must be empty
```

## 7. Commit + push to the SAME branch
```bash
git add -A && git commit -m "..." && git push origin <branch>
```

## 8. Post-push sanity
`git status --short` should be empty and `git log --oneline -1` should be your new commit.

---

## PITFALLS (learned the hard way)

1. **`ruff format` reflows multi-line signatures and moves `# noqa` to the WRONG arg.**
   After formatting, always re-run `ruff check`. A per-arg noqa must sit on the line of the
   actually-flagged arg. When format reflows a def, it can attach the comment to a neighbor
   that isn't the offender (then ruff flags the real one again). Fix by placing noqa on the
   correct line and re-checking, OR use a non-noqa fix (real type) that format can't break.

2. **Restoring a test's string from git can silently break a regex-matcher test.**
   When undoing a sibling/agent edit, don't blindly restore the committed line. E.g. an
   OpenAI-key placeholder test needs `sk-<alnum>{20,}` to match its detector; restoring a
   literal `sk-abc...0ABC` (short/dotted) made the regex match nothing => `map={}`, test
   failed. Verify the restored value still exercises the code path (run the test). Prefer a
   proper wrap (parenthesized adjacent string literals) to satisfy E501 over "fixing" the
   value.

3. **`python` vs `python3`**: on this box `python` is not on PATH. Use `pytest` (has the
   python3 shebang) or `python3`, never bare `python`.

4. **pytest fixture args injected by name can't be renamed to `_`** — that breaks fixture
   lookup. For genuinely-unused fixture args, keep the name and use `# noqa: ARG001` on
   that arg's line. Only rename non-fixture, non-public unused args with `_`.

5. **Genuine `Any` that must stay** (config values, signal `frame`, timestamps passed to a
   coercer, validator payloads, JSON): keep `Any` + targeted `# noqa: ANN401` on that
   annotation line rather than forcing a wrong precise type (wrong type is worse than a
   noqa — it lies to type-checkers).

6. **Dead typing re-export shims**: many `__init__.py` have `from typing import Any, Dict,
   Optional  # noqa: F401` where Dict/Optional are unused re-exports. Migrate to
   `from typing import Any` only — but confirm nothing downstream does
   `from module import Dict/Optional` first (it usually doesn't).

7. **Run the FULL pytest suite**, not just touched-module tests. The integration suite can
   catch cross-module breakage a single-module run misses.

## VERIFICATION SUMMARY FORMAT (report to user)
- ruff: N -> 0 errors across M files
- ruff format: idempotent / "X already formatted"
- pytest: X passed, Y skipped (real numbers)
- mypy: clean / pre-existing-artifact-only
- git: commit SHA, branch, push result
