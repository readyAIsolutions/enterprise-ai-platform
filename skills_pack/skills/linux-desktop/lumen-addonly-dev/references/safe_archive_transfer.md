# Safe Archive / Bundle Transfer Pattern (LUMEN add-only)

Reusable recipe for a PORTABLE, INTEGRITY-CHECKED exporter / importer of a
selection of installed wallpapers (incl. Steam Workshop symlinks) as a
self-contained `.tar.gz` / `.tar.xz` bundle — with zip-slip protection,
tamper detection, and a Qt-free-at-import module. Built and proven in
`lumen/library_transfer.py` (CLAIM 4, LM01).

Why a separate pattern from `importer_module_pattern.md`: that file is about
*writing a wallpaper into the live `lumen/` library* (renderable guarantee,
`LIBRARY_DIR` patch target). This is about *archiving a bundle of folders and
reading it back safely* — zip-slip, manifest integrity, and `tarfile` + mypy
typing. Different class of bug.

## MODULE SHAPE (Qt-free at import)
- Pure stdlib only at top level: `tarfile`, `hashlib`, `json`, `pathlib`,
  `shutil`, `typing`, `lzma`. Lazy-import `lumen.config` (for `default_root`)
  and `lumen.library_stats` (favorites via `StatStore`) INSIDE the one
  function that needs them — keeps import clean (no PyQt/QtWebEngine/Xlib
  transitively pulled).
- Public API complete: define `__all__` listing every exported symbol
  (`BundleError`, `CollectionManifest`, `WallpaperEntry`, `export_bundle`,
  `import_bundle`, `verify_bundle`, `scan_entries`, `build_manifest`,
  `default_root`, `self_test`, ...). A `__all__`-complete module is easy to
  import-smoke and to verify nothing leaked.
- CLI via a `if __name__ == "__main__": sys.exit(_main(sys.argv[1:]))`
  with subcommands: `export`, `verify`, `list`, `import`, `self-test`.
  Import path is `python -m lumen.library_transfer` (NOT `python -m lumen`).

## ZIP-SLIP PROTECTION (critical)
- NEVER use `tar.extract(path=...)` — that writes member names verbatim and a
  crafted `../../etc/cron.d/evil` escapes the target dir.
- On read, screen EVERY member name:
  ```python
  name = member.name
  if name.startswith("/") or ".." in PurePosixPath(name).parts:
      raise BundleError(f"unsafe path in archive: {name}")
  dest = (target_root / name).resolve()
  if target_root.resolve() not in dest.parents and dest != target_root:
      raise BundleError(f"path escapes target: {name}")
  ```
- Then write member content from the stream, never trusting the name on disk:
  ```python
  fh = tar.extractfile(member)          # -> IO[bytes] | None
  if fh is None:
      raise BundleError(f"cannot read member: {name}")
  with fh:
      (dest).write_bytes(fh.read())
  ```
- Test it: craft a bundle with a member named `evil/../../escape.txt` and
  assert `import_bundle` / `verify_bundle` raises `BundleError` and that
  NOTHING was written outside the target root.

## TAMPER DETECTION (manifest integrity)
- Write a `collection.json` manifest into the archive carrying every
  (id, relpath, file_sha256). Stamp `integrity_sha256 = sha256(serialized_blob)`
  over the JSON string (`json.dumps(..., sort_keys=True, separators=(",",":"))`).
- On read, recompute and compare; mismatch => reject with a SPECIFIC error
  (so a corrupted/edited bundle is refused, not crashed on).
- Reading a corrupted manifest MUST raise a clean `BundleError`, NOT a raw
  `json.JSONDecodeError`. Wrap the read:
  ```python
  try:
      raw = tar.extractfile(manifest_member).read().decode("utf-8")
      return json.loads(raw)
  except (OSError, ValueError, json.JSONDecodeError) as exc:
      raise BundleError(f"corrupt collection.json: {exc}") from exc
  ```
  (Caught by `_read_manifest`; a self_test that deliberately corrupts a bundle
  will otherwise surface a raw `JSONDecodeError` and fail the gate.)

## COMPRESSION + MYPY `tarfile` TYPING GOTCHAS
- Choose mode by filename suffix: ends `.tar.xz` / `.txz` (or `compression="xz"`
  arg) => `w:xz`; else `w:gz`. `tarfile.open(name, "r:*")` auto-detects on read.
- `zstandard` is NOT installed in this env (confirmed `import zstandard`
  failed) — only `gzip` + `xz` are supported. Do NOT add a `w:zstd` branch.
- **mypy**: `tarfile.open` has overloads keyed on the `mode` literal. Passing a
  plain `str` fails ("Argument \"mode\" ... Literal ... not compatible"). Type
  the mode explicitly:
  ```python
  from typing import Literal
  _READ_MODE: Literal["r:*"] = "r:*"
  def _write_mode(name: str, compression: str) -> Literal["w:gz", "w:xz"]:
      ...
  tf = tarfile.open(name, _READ_MODE)            # or the returned Literal
  ```
- `extractfile()` returns `IO[bytes] | None`; mypy errors on `with
  tar.extractfile(member):` because it may be None. Assign to a var, guard
  `if fh is None: raise ...`, THEN `with fh:`. (See the write-side snippet above.)

## SAFE IMPORT SEMANTICS
- `dry_run=True` by DEFAULT. `import_bundle(..., dry_run=True)` only lists what
  WOULD be written (read-only preview) — safe for a live library probe.
- Existing ids: skipped unless `force=True`. On `force`, do atomic per-entry
  remove-then-reimport with ROLLBACK (restore the removed folder) on any error.
- Workshop symlinks: dereference on export (`tar` follows the symlink and stores
  the real content). On import, produce a CLEAN native `lumen.json` wallpaper so
  the bundle is self-contained on any machine (no dangling Workshop path).

## IMPORT-SMOKE (leash proof, stricter than the basic QT:False probe)
The offscreen conftest already has PyQt6 in `sys.modules`, so an in-process
assert is a false-fail. Prove the MODULE is clean with a FRESH subprocess that
prints the ACTUAL pulled top-level modules and asserts a denylist EMPTY:
```python
# in tests/test_*.py
def test_import_pulls_no_qt():
    code = ("import sys, runpy, types;"
            "mod = types.ModuleType('__main__');"
            "sys.argv=['x','self-test'];"   # if you want to also exercise CLI
            "import lumen.library_transfer;"
            "pulled=[m.split('.')[0] for m in sys.modules];"
            "blocked={'PyQt6','PySide6','Xlib','PySide2','PyQt5'};"
            "leaked=[m for m in pulled if m in blocked];"
            "print('PULLED_QT:'+repr(leaked));"
            "print('OK' if not leaked else 'LEAK')")
    rc = subprocess.run([sys.executable, "-c", code],
                        capture_output=True, text=True, cwd=REPO_ROOT)
    assert "PULLED_QT:[]" in rc.stdout, rc.stdout + rc.stderr
```
Assert the exact `PULLED_QT:[]` token (not just "no PyQt") so a future leak of
Xlib via a lazy top-level import is caught.

## TEST-FIXTURE PITFALL (library scanners double-count symlinks)
A `scan_entries`/recursive library walk will DOUBLE-COUNT a symlinked
subfolder if the symlink TARGET lives INSIDE the library root. When faking a
wallpaper that has a `workshop/` symlink, put the REAL target OUTSIDE the
library root (e.g. `root.parent / "_real_wp_scene"`), and have the symlink
point to it. Also use `mkdir(parents=True, exist_ok=True)` in fixtures — a bare
`mkdir()` on a nested path raises `FileNotFoundError` and fails 18/22 tests
until fixed.

## VERIFY YOURSELF (headless, live-safe)
```
cd ~/Desktop/apps/lumen
.venv/bin/python -m pytest tests/test_library_transfer.py -q   # 22 passed
.venv/bin/python -m flake8 lumen/library_transfer.py tests/test_library_transfer.py
.venv/bin/python -m mypy --follow-imports=skip lumen/library_transfer.py
.venv/bin/python -m lumen.library_transfer verify --file <bundle> --json   # read-only preview
```
Lint config lives in a HIDDEN `.flake8` (narrow rules F821/F822/F823/F831/E9 +
line-length <=100 convention) and `pyproject.toml` (mypy `--follow-imports=skip`).
`search_files` does NOT index hidden files — discover lint/mypy config via the
terminal (`cat .flake8`, `cat pyproject.toml`), not by grepping.
