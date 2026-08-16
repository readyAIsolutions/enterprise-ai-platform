# Module-Build Concrete Pitfalls (agent_catalog session)

Concrete gotchas hit while building `modules/agent_catalog/` — check these before
debugging a new platform module.

## Kernel enumerations
- `HealthStatus` has NO `.STOPPED`. The terminal/stopping value is
  `HealthStatus.STOPPING`. `shutdown()` should set `self._health = HealthStatus.STOPPING`.
  Enum members: HEALTHY, DEGRADED, UNHEALTHY, STARTING, STOPPING, UNKNOWN.
- `health_check()` must return `HealthStatus.STARTING` when never initialized
  (that is the not-yet-booted value, and tests assert on it).

## Registry / discovery API (easy to mis-call)
- `module_registry.discovered` is a **bool** (did discovery run?), NOT a list.
  To list loaded modules call `registry.list_modules()` which returns
  `ModuleRecord` objects — NOT names. Membership test: check
  `registry.get_record('name').module_class is not None`, or
  `registry.get_instance('name')` returns the instance.
- A discovered-but-not-booting module shows the record with `module_class=None`
  and gets silently skipped by `initialize_all()`. Always confirm the module's
  `__init__.py` actually runs (the `@module(...)` decorator + a top-level import
  that triggers it). `record.module_class = <class ...>` means binding worked.

## create_platform / config_path
- `create_platform(config_path=...)` expects a `pathlib.Path`, not a `str`.
  Passing a str raises `AttributeError: 'str' object has no attribute 'exists'`.
  Use `Path('enterprise/config.yaml')` and `Path('enterprise/modules')`.
- Gold-boot verification script needs the repo PARENT on sys.path:
  `cd ~/Desktop/Enterprise Builder && PYTHONPATH=. python3 enterprise/scripts/verify_gold_boot.py`
  (run from parent, not from inside `enterprise/`, or `import enterprise` fails).

## Python syntax (esp. when building dataclass kwargs)
- `[*mylist or []]` is a SyntaxError — the unpack `*` cannot be applied directly
  to a boolean-`or` expression. Parenthesize: `[*(a or []), *(b or [])]`.
- Same bug surfaced twice while constructing `capabilities=[...]` fields.

## Flagging committed data through .gitignore
- The repo globally ignores `data/` and `*.db`. If a module's OFFLINE BACKBONE is
  a data file inside `modules/<name>/data/`, it will silently not get committed.
  Add targeted negations so only the one canonical file is tracked:
  ```
  data/
  !modules/agent_catalog/data/
  !modules/agent_catalog/data/agent_catalog.json
  ```
  Generated `.db` and per-item dumps stay ignored (regenerable). Verify with
  `git check-ignore <path>` (prints the path if still ignored).

## Default paths should resolve against repo root
- If a config `db_path`/`canonical_path` is relative, resolve it against the
  repo root (3x dirname of `__file__`), not CWD — otherwise boots from a
  different CWD silently point at the wrong file.

## Lint/type gates are advisory in this repo
- `ci.yml`: ruff + mypy jobs are "Advisory only"; **pytest is the real gate**.
  Existing modules carry dozens of ruff findings (skill_factory=129,
  task_harness=10) and PASS CI. Fix real issues (F401 unused imports, E501 line
  length, the `[*(a or [])]` syntax) but don't chase PTH (pathlib) / ANN401
  (`Any` in duck-typed callbacks) — repo-wide convention accepts them.
- Write the module's own `tests/` with `-> None` returns and typed fixtures
  (`tmp_path: Path`, `agents: list[dict[str, Any]]`) so ANN passes on new files.
- mypy (relaxed, `--ignore-missing-imports`) errors to avoid introducing:
  union-attr on `mod.facade` — `assert mod.facade is not None` before calling.

## Boot success criterion
`verify_gold_boot.py` prints `GOLD BOOT VERIFY PASS` and the module name appears
in `IMPORTED MODULE PACKAGES`. A `Loading weights ...` HF progress bar and an
`mlops_lifecycle: No module named feature_label_store` warning are PRE-EXISTING
repo noise, not caused by your module.
