# Scoped lint/format cleanup before PR (and knowing the real merge gate)

Applies when pushing a large multi-wave change (e.g. an enterprise boost) to a
branch-protected repo whose CI runs `ruff`/`mypy` as ADVISORY jobs and `pytest`
as the actual merge gate. Goal: land the PR green without spending days chasing
style rules CI ignores.

## Know the real gate first
- Read `.github/workflows/ci.yml` BEFORE linting. Find which jobs are
  `continue-on-error: true` (advisory; do NOT block merge) vs which are required
  (block merge).
- Common enterprise setup: lint + type-check are `continue-on-error: true`,
  `pytest` is the required gate. That means the fastest path to mergeable is
  "tests green + no NEW real bugs", NOT "zero ruff violations".
- Mirror the CI mypy invocation exactly. CI's `--ignore-missing-imports`
  (non-strict) is much looser than a bare `mypy .`. A scoped run that passes a
  file list can surface an artifact error that does NOT exist under CI's exact
  command — confirm against the CI command before fixing anything.

## Critical pitfall: DON'T reformat the whole repo
- `ruff format` run repo-wide is destructive on a legacy codebase with tens of
  thousands of pre-existing violations. My first pass silently reformatted
  ~275 legacy files that were NOT part of the change.
- ALWAYS scope format+fix to ONLY the files in your diff:
  `ruff format --no-cache $(git diff --name-only <base>...HEAD -- '*.py')`
  or list your changed modules explicitly.
- After the pass, verify the diff is clean:
  `git status --porcelain` must show ZERO stray/legacy files outside the
  intended set before committing. Revert any strays with `git checkout -- <f>`.
- Only then commit the cleanup as a separate chore commit so it's reviewable.

## Which rules to actually fix vs leave
Fix (real bugs / CI-visible):
- F401 unused imports — remove genuinely unused, keep re-exports in
  `__init__.py` with `# noqa: F401` (intentional public API surface).
- F811 redefined name (duplicate import of same symbol) — a real bug; merge the
  imports.
- E722 bare except, B904 raise-from chaining, B024 abc non-abstract — real, fix
  the ones that are meaningful.
Do NOT chase (strict-style, advisory, high effort / low value):
- ANN* missing type annotations, ARG* unused args, PTH* pathlib, UP*, E501 long
  lines, PT* pytest style, TID* import placement. On a big codebase these are
  often thousands of findings; zeroing them is a huge manual annotation pass
  that does not move the merge gate (CI `continue-on-error` + non-strict mypy).
- If the user insists on zero, say so plainly and size the real cost (hundreds
  of annotations across tests) before starting.

## Pitfall: formatter pass can confound the merge gate
Reformatting legacy files that HAPPEN to contain the changed module's deps can
re-fire CI lint on untouched code and make the PR noisy. Keeping the diff
scoped to changed files avoids this.

## Kernel booting pitfall discovered in this session
`ModuleRegistry.discover()` in `platform_kernel.py` enumerated modules from the
filesystem but never `import`ed them, so 0/38 modules booted even though tests
passed. Symptom: "all tests green but nothing boots." Fix: import each module
package before binding it into the registry. If a big rebuild "passes but boots
nothing," check discover() actually imports.
