# safe_mode.py — LUMEN boot/reset module (ENI_LUMEN sub-task B09)

Canonical home for the SAFE MODE lifecycle, built ADD-ONLY on top of
`lumen/safety.BootGuard` (the proven crash-counter core). Use this when a LUMEN
resume touches safe mode, the boot guard, `--reset-safe`, or `app.py`'s boot
bookkeeping.

## What the module is
- `lumen/safe_mode.py` (NEW, **no Qt import** — must run even when the GUI can't).
  Thin orchestration layer over `BootGuard`; it does NOT re-implement crash
  counting.
- `SafeMode`: `is_safe_mode()`, `crash_count()`, `status() -> dict`,
  `format_status() -> str`, `boot() -> SafeBoot`, `engage(reason)`,
  `reset(reason) -> dict` (the canonical clear).
- `SafeBoot` context manager: on enter, if already safe mode it REFUSES to paint
  (`should_paint()` False, no launch recorded); otherwise records a launch (which
  may itself tally a prior crash and trip safe mode via the proven guard). On
  NORMAL exit it calls `mark_clean_exit()` (resets the streak); on EXCEPTION exit
  it deliberately does NOT — so the next boot tallies this one as a crash.
- Module API: `reset()`, `engage()`, `status()`, `format_status()`, `check_boot()`,
  `resource_usage()`, `check_resources()`, `is_unsafe_to_paint()`, `self_test()`.
- CLI: `python -m lumen.safe_mode [--status|--reset|--engage [REASON]|--boot-dry-run|--check-resources|--self-test]`.
  - `--boot-dry-run` shows the paint-vs-safe decision WITHOUT persisting a launch.
  - `--check-resources` prints the live process-tree RSS vs `RSS_CAP` (read-only
    probe; never trips safe mode).
  - `--self-test` runs the FULL lifecycle in-process against a TEMP guard file
    (never LO's real `~/.config/lumen/boot_guard.json`) and exits **0 = PASS /
    1 = FAIL** — the swarm heartbeat's liveness probe. All 12 internal checks
    (fresh-not-safe, engage-trips+persists, reset-clears+zeros+persists, normal
    boot records survived, crash boot does NOT mark survived, low-RSS safe,
    breach detected but read-only probe does NOT trip) must pass for exit 0.
- `lumen/__main__.py --reset-safe` delegates to `safe_mode.reset()` (console
  message unchanged) — one source of truth for clearing a trip.

## Headless test recipe (tests/test_safe_mode.py — 29 passed, Qt-free)
Use this pattern whenever you touch safe mode / the boot guard:

1. **Isolate on-disk state.** `BootGuard` reads `safety.GUARD_FILE` and, on
   construct, WRITES the file if missing. Patch it to a temp path BEFORE using:
   ```python
   with patch.object(safety, "GUARD_FILE", tmp / "boot_guard.json"):
       ...
   ```
   `SafeMode.status()` reads `guard.path`, so patching `safety.GUARD_FILE` alone
   suffices. Do NOT also copy the constant into `safe_mode` — keep a single source
   of truth (avoids a stale-copy divergence the harness can't see).

2. **Test the CLI IN-PROCESS, never via subprocess.** A `python -m lumen.safe_mode`
   subprocess uses LO's REAL `~/.config/lumen/boot_guard.json` and would mutate it
   (even `--status` creates the file if absent). Call `safe_mode._cli([...])`
   directly; capture stdout with `contextlib.redirect_stdout` when asserting
   messages. For `--reset-safe` routing, call `lumen.__main__.main()` with
   `patch.object(sys, "argv", ["lumen", "--reset-safe"])` in-process.

3. **`SafeMode.format_status()` RETURNS the string — it does NOT print.** Don't
   wrap it in `redirect_stdout`; just `out = safe_mode.SafeMode().format_status()`
   and assert on `out`. (This is why a naive `_capture(safe_mode.SafeMode().format_status)`
   yields empty stdout.)

## Pitfalls when authoring a self-test / isolated harness
These bit B09 while adding the built-in `--self-test` and the resource-watchdog
tests — record them so the next resume doesn't re-learn them.

1. **`NameError: name 'safety' is not defined` when a module does `from lumen.safety
   import (...)`.** Importing *names* from a package does NOT bind the package
   name in the module namespace. If your function later references
   `safety.GUARD_FILE` (e.g. to redirect the guard file for an isolated test),
   you get a NameError. FIX: also `import lumen.safety as safety` (the module
   object) alongside the name imports. `safe_mode.py` does exactly this.

2. **Patch the CONSUMER module's name, not the SOURCE module's.** `safe_mode`
   imports `process_tree_rss` and `RSS_CAP` BY NAME
   (`from lumen.safety import process_tree_rss, RSS_CAP`), so `safe_mode` holds
   its own bound references. Mocking `safety.process_tree_rss` has NO effect on
   `safe_mode.resource_usage()` — you must patch `safe_mode.process_tree_rss`
   (and `safe_mode.RSS_CAP`). From inside `safe_mode` use
   `sys.modules[__name__]` as the patch target; from a test use
   `patch.object(safe_mode, "process_tree_rss", ...)`. Same rule any time a
   module re-exports an imported name and you want to stub it.

3. **Redirect `safety.GUARD_FILE` (not a constant copy).** As the recipe says,
   patch `safety.GUARD_FILE` to a temp path and let `SafeMode.status()` read
   `guard.path`. Don't duplicate the constant into `safe_mode` — a stale copy is
   the classic divergence a harness can't see.

## Crash-count quirk (proven core — do NOT "fix")
`BootGuard` only tallies a crash on the **2nd+ launch** that finds NO clean exit
since the previous launch. So to reach `consecutive_crashes >= SAFE_AFTER(2)` you
need **THREE crash-boots** (launch1 = baseline, launch2 = crash#1, launch3 =
crash#2 -> safe mode). A single fresh crash-boot counts 0.

Verify "exception does not mark survived" by asserting
`last_clean_exit < last_launch` (the clean-exit marker was left unset), NOT by
expecting `crash_count == 1`. Constants live in `lumen/safety.py`:
`CRASH_WINDOW=90s`, `SAFE_AFTER=2`, `RSS_CAP=2.2GB`.

## Follow-up — the `app.py` → `SafeMode()` swap (PREPARED, NOT applied)
`app.py`'s `run()` still reaches past `safe_mode` and pokes `lumen.safety.BootGuard`
directly: it calls `guard.is_safe_mode()`, `guard.mark_launch()`, and
`guard.engage_safe_mode("memory watchdog")` (the latter inside the 3s `QTimer`
resource-watchdog). **Correction to an earlier note:** app.py does NOT call
`mark_clean_exit`, nor does it hold a `QTimer` for boot clean-exit — the `QTimer`
is purely the RSS watchdog. A clean swap is to route these through `SafeMode()` /
`SafeBoot` so `safe_mode.py` is the single source of truth.

**Workflow rule (ENI protocol):** when the advance requires editing a *proven-core*
file (here `app.py`), do NOT apply it yourself — prepare `PROPOSED_app_boot_swap_to_safe_mode.diff`
(a unified diff) + a behaviour contract + a **risk note**, and flag it for MASTER
sanction. B09 did exactly this (artifact written to the project root; app.py left
unchanged on disk). This keeps ADD-ONLY while still delivering the plan.

**CRITICAL gotcha in the swap:** `SafeBoot` records a clean exit (and resets the
crash streak) ONLY on a normal `__exit__` / an explicit `boot.survived()`. Since
app.py currently never calls `mark_clean_exit`, the swap MUST add that call on the
clean GUI-exit path (wrap the GUI lifetime in `with sm.boot() as boot:`, or call
`boot.survived()` just before `return`). If you forget, every clean exit is
miscounted as a crash and SAFE MODE trips after 2 normal runs — a self-inflicted
boot-loop. Verify the 6 behaviour-contract items + a desktop smoke before landing.
The resource-watchdog block becomes
`if sm.check_resources(engage_on_breach=True): engine.drop_all_to_safe()`.
