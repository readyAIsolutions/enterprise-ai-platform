# Read-only state access for LUMEN add-only modules (no config writes)

When an ADD-ONLY module must READ existing Lumen state for a diagnostic /
capture / report (never mutate LO's config), use these read-only recipes.

## Boot-guard / safe-mode state — READ-ONLY
- Path: `from lumen.safety import GUARD_FILE` (== `~/.config/lumen/boot_guard.json`).
- DO NOT construct `BootGuard()` — its `__init__` calls `_save()` and WRITES the
  guard file. Parse the JSON directly instead:
  ```python
  from pathlib import Path
  from lumen.safety import GUARD_FILE
  p = Path(GUARD_FILE)
  data = json.loads(p.read_text()) if p.exists() else {}
  is_safe_mode = bool(data.get("safe_mode", False))
  consecutive_crashes = int(data.get("consecutive_crashes", 0))
  ```
- `safe_mode.self_test()` IS safe to call from your aggregator: it sets
  `safety.GUARD_FILE = <temp>` then restores it in `finally`, so it never writes
  LO's real guard. Verify by reading the source for `GUARD_FILE = tmp_guard` +
  `finally: safety.GUARD_FILE = saved_guard`. (Confirmed: it only REDIRECTS to a
  temp file — no real-config write.)

## Profiles — read-only
- `from lumen.profiles import ProfileStore`
- `ProfileStore.load(path)` REQUIRES a path (no default). For the conventional
  store pass `str(DATA_DIR / "profiles.json")`; a missing file yields an EMPTY
  store (never raises). Do NOT call `ProfileStore.load()` with no args
  (TypeError -> your collector silently returns an error dict).

## Leash-safe "no top-level Qt import" test
- A module may lazily `from PyQt6.QtCore import QT_VERSION_STR` INSIDE a function
  (best-effort version probe). That loads PyQt6 into sys.modules but does NOT open
  a display / create QApplication — it's leash-safe.
- But a test that uses `ast.walk(tree)` to flag Qt imports will FALSE-POSITIVELY
  flag that lazy import. Scan ONLY top-level statements:
  ```python
  qt = {"PyQt6", "PySide6", "PySide2", "PyQt5", "qtpy"}
  for node in tree.body:                 # top-level only — NOT ast.walk
      if isinstance(node, ast.Import):
          for a in node.names:
              assert not a.name.startswith(tuple(qt))
      elif isinstance(node, ast.ImportFrom):
          assert (node.module or "") not in qt
  ```

## Config-drift guard test is a known FALSE POSITIVE
- `tests/test_config.py::ConfigSchemaTest::test_no_config_key_drift_between_code_and_schema`
  regex `\b(?:cfg|config|self\.cfg|get_config\(\))\.(?:get|set)\(\s*["']...`
  matches a LOCAL `cfg.get("rules")` / `cfg.get("default_wallpaper_id")` inside
  `scheduler.py` / `library_stats.py` `to_config()` / `from_config()` — those are
  nested dicts, NOT the app config. The flagged keys are not real schema drift.
  Do NOT "fix" it by editing those siblings; it's a guard-test bug. Attribute to
  the config/core owner and report under PRE-EXISTING.
