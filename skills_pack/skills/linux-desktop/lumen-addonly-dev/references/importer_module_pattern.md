# importer_module_pattern.md — hardening a library-WRITING import/ingest module

Worked case study for the LUMEN swarm pattern of taking a shipped
`lumen/<mod>.py` that WRITES library entries (an importer / ingest module) and
hardening it so it can never leave a non-renderable "dead" entry in the user's
Library. Derived from the `lumen.importers/wallpaper_engine.py` pass (LM13,
cycle 3): Wallpaper Engine `.pkg` / `project.json` import.

The core product promise for any ingest path is the SAME one `creator.py`
enforces: **every wallpaper that lands in the Library must be `is_renderable()`,
or the import must fail loudly and leave no half-written folder.**

## 1. The test patch target is the MODULE'S OWN `LIBRARY_DIR`

A module that does `from lumen.config import LIBRARY_DIR` binds the global into
ITS OWN namespace (`lumen.<mod>.LIBRARY_DIR`). Redirecting
`lumen.config.LIBRARY_DIR` or `lumen.wallpaper.model.LIBRARY_DIR` does NOTHING
for it.

```python
# in tests
with patch.object(imp, "LIBRARY_DIR", tmp_lib):
    wp = imp.import_pkg(pkg)
# or
monkeypatch.setattr(lumen.importers.wallpaper_engine, "LIBRARY_DIR", tmp_lib)
```

(`scan_library()` is a separate consumer that reads `model.LIBRARY_DIR` — a
DIFFERENT global. Keep the two straight; the existing `test_importers.py`
patches `imp.LIBRARY_DIR` for this reason.)

## 2. The renderable guarantee (template)

After writing `lumen.json`, build the Wallpaper against the SAME root you wrote
to and assert it can paint; on failure delete the folder.

```python
(dest / "lumen.json").write_text(json.dumps(lumen_meta, indent=2))
wp = Wallpaper(LIBRARY_DIR, lumen_meta)
if not wp.is_renderable():
    shutil.rmtree(dest, ignore_errors=True)
    raise ValueError(f"Imported '{name}' is not renderable (kind={kind})")
return wp
```

For a function that returns `None` on failure instead of raising
(`import_we_project`), do the same but `return None` after `rmtree`. Either way
the half-written folder is gone — no silent void.

## 3. Keep `detect_kind()` (metadata-only, often test-LOCKED) separate from the on-disk planner

`detect_kind()` is a quick guess from `project.json` alone and a sibling test
may lock its contract (e.g. `scene -> KIND_WEB`). Do NOT mutate it to add
smart logic. Add a SECOND function that inspects the unpacked files:

```python
def _plan_import(meta: dict, dest: Path):
    """(kind, entry, original_type) from project.json + real files on disk."""
    raw = (meta.get("type") or "web").lower()
    explicit = (meta.get("content") or {}).get("file") or meta.get("file") or ""
    if raw in ("video", "video wallpaper"):
        kind = KIND_VIDEO
    elif raw in ("image", "image wallpaper"):
        kind = KIND_IMAGE
    elif raw in ("web", "web wallpaper"):
        kind = KIND_WEB
    else:  # scene / unknown -> best-effort fallback chain
        for k, exts in ((KIND_SHADER, _SHADER_EXTS), (KIND_WEB, _HTML_EXTS),
                        (KIND_VIDEO, _VIDEO_EXTS), (KIND_IMAGE, _IMG_EXTS)):
            ex = explicit if Path(explicit).suffix.lower() in exts else ""
            e = _resolve_entry(dest, k, ex)
            if e:
                return k, e, raw
        return None, None, raw
    return kind, _resolve_entry(dest, kind, explicit), raw
```

This is what lets a `scene` pack with a GLSL become a shader wallpaper, a
`scene` with only a preview video become a video wallpaper, etc.

## 4. Nested media -> store RELATIVE posix entry paths

Wallpaper Engine packs nest files under a subfolder. Discover top-level first,
then `rglob`, and store the entry as a relative posix path so
`Wallpaper.entry_path` / `preview_path` resolve it under `folder/`:

```python
def _first_media(dest, exts):
    for p in sorted(dest.iterdir()):
        if p.is_file() and p.suffix.lower() in exts:
            return p.name
    for p in sorted(dest.rglob("*")):
        if p.is_file() and p.suffix.lower() in exts:
            return p.relative_to(dest).as_posix()   # e.g. "v/clip.mp4"
    return ""

def _resolve_entry(dest, kind, explicit=""):
    if explicit:
        ep = dest / explicit
        if ep.exists() and ep.is_file():
            return explicit
        hits = [n for n in dest.rglob(explicit) if n.is_file()]
        if hits:
            return hits[0].relative_to(dest).as_posix()
    if kind == KIND_WEB:
        if (dest / "index.html").exists():
            return "index.html"
        hits = [n for n in dest.rglob("index.html") if n.is_file()]
        return hits[0].relative_to(dest).as_posix() if hits else ""
    if kind == KIND_VIDEO:
        return _first_media(dest, _VIDEO_EXTS)
    if kind == KIND_IMAGE:
        return _first_media(dest, _IMG_EXTS)
    if kind == KIND_SHADER:
        return _first_media(dest, _SHADER_EXTS)
    return ""
```

A bare top-level `p.name` breaks for nested packs (entry resolves to a missing
top-level file -> non-renderable). For `KIND_IMAGE` set `preview = entry` (image
paints from its preview/cover); for other kinds set `preview = _first_media(dest,
_IMG_EXTS)`.

## 5. Leash subprocess that does NOT pollute the real library

The conftest builds a `QApplication`, so an in-process "no Qt" check lies. Prove
the importer builds a wallpaper with ZERO QApplication in a FRESH subprocess,
and redirect `LIBRARY_DIR` to tmp so the probe never writes to
`~/.local/share/lumen`:

```python
lines = [
    "import os, io, json, zipfile, tempfile, sys",
    "os.environ.pop('DISPLAY', None)",
    "from lumen.importers import wallpaper_engine as imp",
    "from PyQt6.QtWidgets import QApplication",
    "assert QApplication.instance() is None, 'QApplication existed on import'",
    "lib = tempfile.mkdtemp()",
    "imp.LIBRARY_DIR = __import__('pathlib').Path(lib)",
    "buf = io.BytesIO()",
    "with zipfile.ZipFile(buf, 'w') as z:",
    "    z.writestr('project.json', json.dumps({'title':'Leash','type':'web'}))",
    "    z.writestr('index.html', '<html></html>')",
    "pkg = os.path.join(lib, 'leash.pkg')",
    "open(pkg, 'wb').write(buf.getvalue())",
    "wp = imp.import_pkg(pkg)",
    "assert QApplication.instance() is None, 'import built a QApplication'",
    "assert wp is not None and wp.is_renderable()",
    "print('LEASH_OK')",
]
code = "\n".join(lines)
env = dict(os.environ); env["QT_QPA_PLATFORM"] = "offscreen"; env.pop("DISPLAY", None)
proc = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT,
                      capture_output=True, text=True, timeout=120, env=env)
assert proc.returncode == 0 and "LEASH_OK" in proc.stdout
```

(Use a `list-of-lines` joined by `"\n"` — never a single string with `\n`
escapes, which is error-prone to edit.)

## 6. Verification cheat-sheet for an importer module

```bash
cd ~/Desktop/apps/lumen
.venv/bin/python -c "from lumen.importers import import_pkg, import_we_project, import_workshop_sources"   # import-smoke
.venv/bin/python -m pytest tests/test_<mod>.py -q
.venv/bin/python -m flake8 lumen/<mod>.py tests/test_<mod>.py
.venv/bin/python -m mypy lumen/<mod>.py        # grep output for '<mod>.py' -> 0 = your file clean
.venv/bin/python -m importlint check lumen/<mod>.py tests/test_<mod>.py
# full regression, isolating any OTHER builder's broken collection:
.venv/bin/python -m pytest -q --ignore=tests/test_preflight.py
```

## 7. Pitfalls specific to importers (summary)

- Patch the module's OWN `LIBRARY_DIR` binding, not config's or model's.
- Never leave a dead entry: rmtree + raise/return-None on `not is_renderable()`.
- Don't mutate a test-locked `detect_kind`; add `_plan_import` instead.
- Store nested-media entries as relative posix paths.
- One broken collection (another builder's `ImportError` test) aborts bare
  `pytest` — use `--ignore=<broken>` to get your regression number; don't fix
  the other builder's module.
