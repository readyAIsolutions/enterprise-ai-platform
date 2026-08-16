# Offline Fallback Engine + Isolated Registry Tests

Technique from the master-class rebuild of `modules/triadforge` (a wrapper around an
external `~/Desktop/TriadForge` package). Generalizes to ANY ENI module whose real
engine lives outside the repo: make the module functional + HEALTHY + fully testable
even when that external dependency is absent.

## The offline fallback engine (ScanCore) pattern

When a module wraps an external package, do NOT let it degrade to UNHEALTHY when the
package is missing. Layer in an internal, stdlib-only engine so the module works
offline AND has a deterministic, dependency-free test surface.

- Add a module-level availability flag for the fallback, e.g. `SCANCORE_AVAILABLE = True`
  (always true — stdlib-only, zero deps). Keep the external flag (`TRIADFORGE_AVAILABLE`)
  from the existing try/except import block.
- `__init__` selects `self._engine = "external" if EXT_AVAILABLE else "internal"`.
- `health_check()` returns HEALTHY when EITHER flag is true AND the store is initialized;
  UNHEALTHY only when BOTH are patched false.
- Route every facade method (run_scan / export_sarif / fix_snippet / list_findings) by
  `self._engine`. The internal engine implements the SAME duck-typed surface as the
  external store (add_target/get_target/create_scan/update_scan/list_findings/
  export_sarif/fix_snippet) so the module just delegates.
- The internal engine performs REAL orchestration, not stubs: run a scan against a
  config, aggregate findings into per-scan lists, transition scan states
  (pending->running->completed/error), and export well-formed SARIF 2.1.0. Give it a
  small rule catalog (`_RULES`) with stable rule_ids/severity/message/fix so SARIF is
  deterministic and assertable.
- Expose high-level convenience facades (`scan_web/scan_source/scan_llm`) that
  add-a-target + run-scan in one call and route to the active engine.

## Pitfall: typed target for the external store

If the external package happens to be INSTALLED on the dev box (not just the fallback),
your offline tests will silently run the EXTERNAL path and fail. `_add_target` must
branch on `self._engine`:
- external store expects its OWN model object (e.g. `Target(mode=TargetMode(...))`),
  NOT a dict.
- internal ScanCore accepts a dict or a duck-typed object.

Build a dict in `add_web_target/add_source_target/...`, then `_add_target` converts to
the right shape per engine. Don't assume the external package is absent just because the
task says "wraps external engine" — check at runtime.

## Pitfall: force the offline engine in facade tests

To make facade-routing tests deterministic regardless of whether the external package
is installed, monkeypatch the flags before constructing the module in a fixture:
`monkeypatch.setattr(tfmod, "TRIADFORGE_AVAILABLE", False)` +
`SCANCORE_AVAILABLE = True`, then assert `mod._engine == "internal"`.

## Pitfall: registry tests must be isolated from sibling modules

`ModuleRegistry().discover()` imports EVERY `modules/<name>/__init__.py`. One unrelated
broken sibling (e.g. a `threat_model` file with a misplaced `from __future__ import`
causing SyntaxError) will fail all your registry tests even though YOUR module is fine.
Fix: point `ModuleRegistry(modules_path=<tmp_path>)` at a temp dir containing ONLY your
module's package (a one-line `__version__ = "..."` `__init__.py` is enough). Discovery
then imports `enterprise.modules.<name>` (the REAL package, already imported) and binds
`record.module_class` correctly — without touching broken siblings. Never assert against
the real `modules/` dir.

## Pitfall: metadata via instance, not class

`TriadForgeModule.name` on the CLASS returns the `name` property descriptor, not the
string. Assert class-level `_meta_name == "triadforge"` / `_meta_version`, and
`instance.name` / `instance.version` for the property accessors. `_meta_name/_meta_version`
are set on the class by the `@module` decorator.

## Test-count target for "master class"

Zero tests is unacceptable. A rebuilt module should carry a real suite (15-35 tests is a
healthy range) grouped by concern: lifecycle/INIT+health, offline engine scans returning
findings, SARIF well-formedness, facade routing to the active engine, idempotent
shutdown, and kernel-registry registration. No stubs — assert real results.
