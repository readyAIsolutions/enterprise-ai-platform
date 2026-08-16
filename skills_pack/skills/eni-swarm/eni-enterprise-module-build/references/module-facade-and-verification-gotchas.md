# Module facade recipe + verification gotchas (session: look_and_feel module)

Building a new capability module for ~/Desktop/Enterprise Builder/enterprise.
Captures the module-facade shape, the CE/ruff/mypy/pytest verification loop, and
pitfalls hit in practice (from adding the `look_and_feel` visual-design registry
module).

## The module facade shape (what a green, auto-discovered module looks like)

```
enterprise/modules/<name>/
  __init__.py            # @module registration + exports + factory
  <name>.py              # real logic (Registry / Parser / service classes)
  data/<name>_*.txt      # bundled seed data -> enterprise/data/
  tests/__init__.py
  tests/test_<name>.py
```

`__init__.py` contract (copy the `compression_bridge` pattern):
- Import kernel with graceful fallback so it works from parent dir AND from
  inside enterprise/:
  ```python
  try:
      from enterprise.platform_kernel import HealthStatus, Module, module
  except ImportError:
      _parent = Path(__file__).resolve().parent.parent.parent.parent
      if str(_parent) not in sys.path:
          sys.path.insert(0, str(_parent))
      from enterprise.platform_kernel import HealthStatus, Module, module
  ```
- `@module(name="<name>", version="1.0.0")` on `class <Name>Module(Module)` with
  `initialize()` / `health_check()` / `shutdown()` (all `async`), and
  `__version__ = "1.0.0"` at the bottom (the registry's `_extract_version` reads it).
- A `create_<name>_module(config=None) -> <Name>Module` factory is the platform
  entrypoint; also export it in `__all__`.
- Config paths: resolve `~` with `.expanduser()`, and make relative paths
  absolute against `Path(__file__).resolve().parent.parent.parent` (enterprise/).
  Defaults like `_DEFAULT_DATA` should be split across lines to stay under ruff's
  100-char E501.

`config.yaml` entry (end of `modules:` block):
```yaml
  <name>:
    enabled: true
    priority: 9
    required: false
    startup_timeout_sec: 15
    health_check_interval_sec: 120
    config:
      registry_path: "~/.hermes/<name>_registry.json"
      default_modules_path: "data/<name>_modules.txt"
```

## Verification loop (pre-PR, do on the MODULE only)

CI treats ruff as advisory-only (the legacy codebase carries ~19k pre-existing
errors) and mypy as relaxed/informational (`mypy . --ignore-missing-imports`).
**pytest is the merge gate.** So: make your module pass rust/lint cleanly on its
OWN files, but don't chase a `ruff check .` or full-repo mypy to zero — they will
never be green and are not gating.

```bash
cd ~/Desktop/"Enterprise Builder"/enterprise
ruff check modules/<name>/          # want: All checks passed!
ruff format --check modules/<name>/ # want: N files already formatted
ruff format modules/<name>/         # if not; THEN re-ruff-check (format can reorder)
mypy modules/<name>/<name>.py modules/<name>/__init__.py  # want: no issues
python3 -m pytest modules/<name> -q -p no:cacheprovider   # want: all pass
```
Then boot-verify (see below) and run the FULL pytest suite once in the background
(`terminal background=true notify_on_complete=true`) — it is the actual gate.

Note: `python3` not `python` (there is no `python` on this box).

## PITFALL: don't name a registry/data method `.list()`

If a value-store class has a method named `list`, mypy strict resolves the
builtin `list` in that class's own return annotations to the METHOD, producing
confusing cascading errors, e.g.:
```
error: Function "...Registry.list" is not valid as a type
error: "list?[...Entry]" has no attribute "__iter__" (not iterable)
error: Statement is unreachable
```
Fix: name it `all_modules()` (or anything not a builtin). Then update callers.

## PITFALL: pytest fixture-arg annotations (ANN001/ARG001)

- `tmp_path` used → annotate `tmp_path: Path` (import Path in the test).
- `tmp_path` declared but unused → drop the parameter entirely (ARG001).
- Split `assert a and b` into two asserts (PT018).
- Don't alias `import HealthStatus as HS` (N817 CamelCase-as-acronym); use
  `import enterprise.platform_kernel as pk` then `pk.HealthStatus.HEALTHY`.
- Tests add the module's PARENT dir to `sys.path` before `from <name> import ...`
  (same trick as existing module tests). Pyright reports
  `import "enterprise.platform_kernel" could not be resolved` and
  `import "look_and_feel" ...` on tests — those are expected/cosmetic; CI mypy
  passes `--ignore-missing-imports`, and ruff on the module stays clean.

## PERFECT: boot-verify through the real PlatformOS

The module must auto-discover AND boot HEALTHY, not just import. Use the
singleton pattern (constructor takes no args):

```python
import asyncio, sys
from pathlib import Path
sys.path.insert(0, "/home/hunter/Desktop/Enterprise Builder")  # parent so `enterprise` resolves
from enterprise.platform_kernel import PlatformOS

async def main():
    PlatformOS.reset_instance()
    os_ = PlatformOS.instance()
    os_.initialize(config_path=Path("/home/hunter/Desktop/Enterprise Builder/enterprise/config.yaml"))
    names = [r.name for r in os_._module_registry.list_modules()]
    print("look_and_feel discovered:", "look_and_feel" in names)
    await os_.start()
    rec = os_._module_registry.get_record("look_and_feel")
    print("class bound:", rec.module_class is not None,
          "| instance:", rec.instance is not None,
          "| status:", rec.instance.status if rec.instance else None)
    print("platform state:", os_.state)

asyncio.run(main())
```
- `initialize(config_path=...)` takes a `Path`, NOT a `str` (str crashes on
  `.exists()`).
- The attribute is `_module_registry`, not `.registry`.
- A torch-backed unrelated module may log `CUDA error: out of memory` during
  `start()`; that does NOT block the platform reaching RUNNING and is unrelated
  to your module. Assert on YOUR module's discovery + HEALTHY, not on a clean log.
