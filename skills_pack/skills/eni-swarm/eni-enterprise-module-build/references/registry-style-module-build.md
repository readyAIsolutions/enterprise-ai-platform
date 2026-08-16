# Building a registry/CRUD-style module (look_and_feel example)

Session 2026-08-05: built the `look_and_feel` module (visual design registry:
parse a structured text format -> JSON store -> programmatic API + CLI) into
the enterprise repo. The generic module-build steps were clean; these are the
non-obvious, reusable details that bit during that build.

## Mini-module anatomy (registry/facade pattern)
```
modules/<name>/__init__.py       # @module(name,version) class + create_<name>_module factory + __all__ + __version__
modules/<name>/<name>.py         # the real classes (Registry, Parser, CLI, model)
modules/<name>/tests/test_<name>.py
data/<name>_modules.txt          # seed data file (in repo data/)
```
`__init__.py` imports kernel via the dual try/except (absolute `enterprise.platform_kernel`
then parent-insert fallback) EXACTLY like compression_bridge — copy that preamble verbatim.

## Config.yaml registration
Add a block under `modules:` with `enabled/priority/required/startup_timeout_sec/
health_check_interval_sec/config:`. The kernel's ModuleRegistry reads `modules.<name>`
from config.yaml; without it the module is discovered but booted with defaults —
only add it to get explicit priority/config. Append at the END of the modules list
(just before the `# ── Logging ──` section), indent 2 spaces to match siblings.

## Config path resolution (registry_path / data path)
Module config strings can be relative or `~`. Do BOTH in `initialize()`:
```python
p = Path(cfg).expanduser()
if not p.is_absolute():
    p = Path(__file__).resolve().parent.parent.parent / p   # repo root
```
Regression to avoid: a relative "data/x.txt" with no root-anchor silently 404s
and the module just starts empty (health still reports healthy).

## Mimic the platform's own helpers instead of importing them into the facade
The kernel `Module` base already exposes `self._config`, `self._status`,
`HealthStatus`, `status`, `name`, `version`, `module_id`. Don't reinvent.

## Pitfall: a method named `list()` shadows the builtin → mypy breaks
If the registry class has a `def list(self)` method, then inside that class any
use of the builtin type `list[...]` in an annotation resolves to the METHOD, so
mypy fails with confusing errors:
- `error: "list?[...]" has no attribute "__iter__"` at a `for` loop
- `error: Function "....list" is not valid as a type` at `-> list[Entry]`
Fix: rename the method (e.g. `all_modules()` / `items()`), never `list`.

## Enum vs string in tests (self-tests AND unit tests)
`GuardAction.ALLOW == "allow"` is `False`. When asserting action values in the
test file, compare `.value` (or the enum member), not the enum to a bare string —
otherwise a green guard shows as a FAIL in your own test.

## Housekeeping a new module (mypy/ruff strict)
- `config: dict | None` is rejected under `strict=true` (`Missing type arguments
  for generic type "dict"`). Use `dict[str, Any] | None` and import `Any`.
- `from __future__ import annotations` at top; stdlib imports at top (no lazy
  base64 etc.) — mirrors the secret_broker lesson.
- ruff E501 >100 cols: wrap `_DEFAULT_DATA = str(Path(...) / "data" / f)`.
- pytest fixture args need explicit type: `def test_x(tmp_path: Path)` (ANN001).
- The repo CI runs the FULL pytest suite as the merge gate; run
  `python3 -m pytest -q -p no:cacheprovider` (repo runs ~4200 tests, ~2 min).
