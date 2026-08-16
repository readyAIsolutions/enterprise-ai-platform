# PlatformOS boot verification — recipe + kernel API (verified 2026-08-03, updated 2026-08-04)

Verifying a new module actually BOOTS HEALTHY is separate from passing pytest.
A module's N unit tests can all pass AND it can still fail to initialize in the
kernel. This is the reliable way to prove boot, plus the kernel API surface that
is not obvious from the docstrings.

## IMPORTANT — the discovery bug is FIXED (2026-08-04)

Earlier this file documented that `ModuleRegistry.discover()` never imported
module packages, so `record.module_class` stayed None and `initialize_all()`
silently initialized nothing. **That bug is now fixed** in `platform_kernel.py`:

- `ModuleRegistry.discover()` now calls `self.import_module(name)` for each
  discovered `modules/<name>/` dir BEFORE binding the record, so the `@module`
  decorator fires and populates `_MODULE_REGISTRY`, then `record.module_class`
  is bound. **All 38 modules now bind and boot HEALTHY** through a real
  `PlatformOS.start()` (previously 27/37 bound, only via incidental imports).
- The fix had an ordering subtlety: the record must be added to `self._records`
  BEFORE `import_module(name)` is called, because `import_module()` returns None
  early if `record is None`. Insert `self._records[name] = record` first.
- `import_module()` still degrades gracefully (catches ImportError, returns
  None, leaves `module_class` None) so an unimportable module never kills
  discovery — it just stays unbound. Regression test:
  `tests/test_platform_kernel.py::test_discover_imports_and_binds_decorated_classes`
  and `test_discover_does_not_crash_on_unimportable_module`.

**Therefore the old manual `import_all_modules()` workaround is no longer
required.** You do NOT need to pre-import every module to register it. Discovery
handles it. The rest of this file (live-instance smoke + kernel API facts)
remains valid and important.

## Boot-verification recipe

```python
import asyncio
from pathlib import Path
from enterprise.platform_kernel import PlatformOS

async def main():
    base = Path(__file__).resolve().parent.parent
    PlatformOS.reset_instance()                # singleton — reset for a clean boot
    os = PlatformOS.instance()
    os.initialize(config_path=Path(base / "config.yaml"))   # SYNC, returns None
    await os.start()
    bound = {r.name: r.instance for r in os._module_registry.list_modules()
             if r.instance is not None}
    assert "memory" in bound, "module not initialized!"
    # ... functional smoke on bound["memory"] / bound["mcp_tools"] ...
    await os.shutdown()
```

Smoke the LIVE instances, not just imports — this is what catches method-
signature mismatches that unit tests inside the module never exercised.

## Kernel API facts (read from platform_kernel.py, verified at runtime)

- `PlatformOS` is a thread-safe SINGLETON: use `PlatformOS.instance()`; `PlatformOS.reset_instance()` to clear it between boots.
- `initialize(config_path: Optional[Path], modules_path: Optional[Path])` — SYNC (returns None), no await.
- `start()` / `shutdown()` are async. There is NO `stop()` — `await os.stop()` raises AttributeError.
- **Lifecycle now supports `await os.pause()` / `await os.resume()`** (added 2026-08-04). `pause()` stops the health-poll task; `resume()` re-initializes UNHEALTHY/UNKNOWN instances and restarts polling. Valid only from RUNNING/DEGRADED/RECOVERING (pause) and PAUSED (resume). The `LifecycleState.PAUSED -> RECOVERING` transition had to be added to the state table for resume to work.
- `initialize_all()` now honors `startup_timeout_sec` via `asyncio.wait_for` — a hung `initialize()` fails a module to UNHEALTHY instead of blocking boot (the timeout is read from `config.yaml lifecycle.startup_timeout_sec`).
- `registry = os._module_registry` (private attr; no public getter).
- `registry.list_modules()` → list of `ModuleRecord`. Fields: `name` (str), `path`, `version`, `module_class`, `instance`, `enabled`, `required`, `priority`, `config`. NOTE: there is NO `.module_name` field — it is `.name`.
- `registry.get_instance(name)` → the initialized `Module` or None.

## Method-signature traps hit on the memory/mcp_tools modules (read before smoke)

- `MemoryModule.remember(user_id, content, memory_type=..., metadata=..., importance=...)`
  — positional order is `(user_id, content)`, NOT `(content, user_id)`.
- `MemoryModule.search(query, k=None, user_id=None, memory_type=None, metadata_filter=None)`.
- `ScoredMemory` wraps a `MemoryEntry` — the text is at `.memory.content`, NOT `.content`.
- All facade methods live on the `@module`-decorated instance you get from `get_instance(name)`.
- `mcp_tools` facade: `list_tools()` returns plain dicts, `call_tool(name, args_dict)` is sync.

## Common shutdown bug when all modules finally boot

Once discovery actually boots every module, latent per-module bugs surface that
were hidden when nothing initialized. Real example: `modules/ai_defense/
ai_defense.py` `shutdown()` referenced `HealthStatus.STOPPED`, which does NOT
exist (it's a LifecycleState, not a HealthStatus). The kernel's own
`Module.shutdown()` sets terminal state, so a module should NOT set
`self._status = HealthStatus.STOPPED` — just log and return. After booting a
full platform, always assert `shutdown_all()` returns no `False` entries.

TL;DR: discovery is fixed — don't re-add `import_all_modules()`. Boot the
platform, assert live instances, smoke them, and verify clean shutdown using
`platform_kernel` directly.
