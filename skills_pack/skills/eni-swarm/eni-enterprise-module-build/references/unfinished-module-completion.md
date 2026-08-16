# Completing scaffolded / unfinished enterprise modules + deterministic-hash pitfall

Session: v2.0.0 "Golden Boot" (2026-08-11). Three modules were scaffolded but
non-functional; the fix pattern is reusable whenever a module is "scaffolded but
won't boot."

## The "scaffolded-but-broken module" signature

A module dir exists with working inner logic but the package won't import / won't
register as a Kernel `@module`. Common causes:

1. `modules/<name>/__init__.py` **eagerly imports sibling submodules that don't
   exist** -> `ModuleNotFoundError` on any `import`.
   - Some such `__init__.py` guard the missing imports with
     `try: ... except ImportError: X = None`. Those silently disable the feature
     rather than failing — check for both eager AND guarded missing imports.
2. **No top-level `__init__.py` at all** -> package isn't discoverable by the
   Kernel registry (`modules/*/__init__.py` scan).
3. **No `@module(...)` decorator / no `create_<name>_module()` factory** -> even
   if it imports, it never registers/boots.

## Diagnostic checklist (run before writing anything)

- `python3 -c "import enterprise.modules.<name>"` from repo parent w/ PYTHONPATH=. — does it import?
- Grep `modules/<name>/__init__.py` for `from .X import` and compare against
  actual files present; list both eager and guarded imports.
- Check for `@module(` decorator + matching `create_<name>_module` factory.
- `git status` — a module that is entirely `??` untracked is suspect.

## Fix pattern (the 3 "finish" steps)

1. **Write every missing submodule** the `__init__.py` imports, matching the
   exact symbol names listed (classes + a `create_*` factory each). STDLIB only
   (sqlite3 for stores, dataclasses for models, math/statistics for drift).
2. **Add the Kernel registration**: copy the a2a pattern exactly —
   `from enterprise.platform_kernel import HealthStatus, Module, module` +
   `@module(name="<name>", version="1.0.0")` on a `Module` subclass with async
   `initialize`/`health_check`/`shutdown` + `set_event_bus`, plus a
   `create_<name>_module(config=None)` factory. The registration lives in
   module.py or __init__.py such that merely importing the package registers it.
3. **Remove the conftest namespace-package shims.** Before the real submodules
   existed, root/child `conftest.py` pre-registered the package in `sys.modules`
   as a lightweight namespace (dodging the broken `__init__`). Once it imports
   cleanly, delete those shims and replace child conftests with a minimal
   sys.path-insert only. Verify `import enterprise.modules.<name>` still works.

## Pytest invocation gotcha (avoid a false "hang")

- Running `pytest enterprise/` from the PARENT dir (passing the dir as an arg)
  can appear to hang. The canonical CI invocation runs **from inside the repo
  root** with `pytest -q` honoring pyproject `testpaths` — that is the
  authoritative green signal. Run per-directory / whole-suite from repo root.
- `pytest-timeout` is NOT installed; use `timeout Ns` around subprocess runs to
  avoid blocking on a hung test.

## Deterministic-hash pitfall (Python `hash()` is per-process randomized)

Python's builtin `hash(<str>)` is salted per-process (PEP 456 hash
randomization). Any code that uses `hash()` for feature hashing / embeddings /
retrieval ordering is NON-deterministic across runs -> flaky tests that
intermittently fail on ordering.

- Symptom: a vector-retrieval test passes 3x then fails with "expected v1 got v2".
- Fix: derive a stable int from `hashlib.md5(s.encode()).hexdigest()[:8]` (int,
  base 16). If you need SIGNED projection values, derive the sign from a bit of
  that int (e.g. `1.0 if (h & 1) == 0 else -1.0`) — do NOT use `h >= 0` because
  the md5 int is always non-negative and the whole row collapses to all-+1.

Example:
```python
import hashlib
h = int(hashlib.md5(f"{i}_{j}".encode()).hexdigest()[:8], 16)
row.append(1.0 if (h & 1) == 0 else -1.0)
```

## Version-bump toenail

`__version__` lives in repo-root `enterprise/__init__.py` AND in each module's
`__init__.py`. Bump the root one for the release.

## Verification bar (real numbers, run yourself)

- Per-module `pytest modules/<name>/ -q` -> all green (report counts).
- Full CI: from repo root `pytest -q -p no:cacheprovider` -> e.g. 4404 passed.
- `python3 scripts/verify_gold_boot.py` -> PASS, module count up.
- Kernel registry: `importlib.import_module(...)` then
  `'<name>' in _MODULE_REGISTRY`.
