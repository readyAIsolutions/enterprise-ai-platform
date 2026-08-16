# Model Miner + Hermes Controller enterprise modules (2026-08)

Build pattern for adding an "external tool wrapper" as an enterprise module, and
the architectural corrections LO made.

## LO's composition rule (IMPORTANT, will recur)
LO draws a hard line between two kinds of things:
1. **The locally-running model that handles Hermes** (ENI Hermes Controller, built
   on the :8931 local security model) = a **standalone, universally-bootable
   program** (infinite loop, ever-expanding catalog, cross-platform boot).
2. **Model Miner** (scan local models / rip training / integrate into KB+MCP+LSP)
   = a **proper enterprise MODULE**, NOT a standalone bootable program, NOT a
   dashboard button.

So before building anything, ask: is this "the model that drives Hermes" (→ bootable
program/service) or "a capability inside the platform" (→ enterprise module)?
LO explicitly rejected adding the miner to the dashboard and rejected it as a
standalone program — it belongs in `modules/<name>/` in the enterprise repo.

## Module skeleton (stdlib, graceful degradation)
- `modules/<name>/__init__.py`: `@module(name=..., version=...)` class extending
  `Module`; `initialize` / `health_check` / `shutdown`; a thin `XFacade` that
  degrades gracefully when an external package isn't importable.
- Wrap optional deps in try/except and expose `available()` so the module still
  boots/discovers and tests never crash on a box without the external package.
- `modules/<name>/tests/test_<name>.py`: meta fields, lifecycle, facade never
  raises, create-helper returns instance.
- `tests/integration/test_<name>_boot.py`: assert `ModuleRegistry(modules_path)
  .discover()` contains the module name (proves auto-discovery).

### Pitfalls
- `HealthStatus.STOPPED` does **NOT** exist — the enum member is `STOPPING`.
- Facade `process(**kw: Any)` triggers ANN401; add `# noqa: ANN401` on the line
  (kwargs are intentionally forwarded, don't type them).
- Only import what you use from the controller package (`from eni_controller import
  controller`) — submodule imports expanded only for use trigger F401.

## Ever-expanding catalog (infinite iterations)
The enterprise catalog (`eni_controller/enterprise.py` / any module-aware code)
must grow WITHOUT a hardcoded list. Pattern:
- `_fingerprint()` = sorted names of dirs under `modules/` (cheap).
- `refresh_if_changed()` re-scans only when the fingerprint changes; returns True
  when a NEW module appeared.
- Describe unlisted modules by introspecting README/docstring, fall back to file
  listing. Don't maintain a static capability dict as the only source.
- Verify: drop a fake `modules/zz_new/__init__.py`, assert count grows 42->43, then
  `refresh_if_changed()` returns False on next call (idempotent).

## Cross-platform boot (Windows + Linux) for the Hermes-handling program
- One pure-stdlib dispatcher `eni_miner_boot.py` that locates the package relative
  to its own file (works from any CWD/OS).
- Thin wrappers all delegate to it: `miner.bat` + `miner.ps1` (Windows),
  `miner.sh` + `miner.py` (Linux), plus a `.desktop` launcher (Linux) that execs a
  bash wrapper (GNOME desktop files reject `;`/quotes in Exec — use a separate
  launcher script).
- `--daemon` runs an INFINITE loop by default (`max_passes=None`);
  `max_passes=N` only for tests.
- systemd user service (like free-router / acpeso-tunnel / eni-controller) with
  Restart=on-failure; linger already on → auto-boot.

## Ruff on this box differs from the enterprise repo
- This standalone controller env enables BLE001/S110/PLW1510/DTZ005/RUF059 that the
  enterprise pyproject ignores. Intentional fail-closed `except Exception:` in
  boundary/router code → `# noqa: BLE001 - fail-closed wrapper`; try-except-pass →
  add `, S110`. `subprocess.run` → add `check=False` (PLW1510). `datetime.now()` →
  `.now().astimezone()` or `now(tz)` then strip tz for local-naive ISO (DTZ005).
- `# noqa: E402` on sys.path-insert-then-import in self-contained scripts is flagged
  RUF100 when E402 isn't enabled — drop those noqas there.
