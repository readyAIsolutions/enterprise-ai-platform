# Creator-Module Pattern (worked case study: `lumen/creator.py`)

Reference for any LUMEN add-only module that WRITES into the library (turns a
URL / local HTML / image / video / GLSL shader into a loadable wallpaper) and
needs to stay pure-stdlib + headless-testable.

## The headline pattern
A "creator"/asset-ingest module is the cleanest possible add-only unit:
pure stdlib + file IO, imports ONLY `lumen.config` (for `LIBRARY_DIR`) and
`lumen.wallpaper.model` (for the `Wallpaper` data model). It pulls NO PyQt /
QWebEngine / X11 / WebGL, so it unit-tests under the hard leash.

Dispatch shape that proved clean:
- `create_from_url(url)` -> native URL wallpaper (see "Native URL entry" below).
- `create_from_file(path)` -> branch on extension: `.html`/`.htm` (web),
  image (`.png/.jpg/.jpeg/.gif/.webp`), video (`.mp4/.webm/.mkv/.mov`),
  GLSL (`.frag/.glsl/.vert`). Copy siblings (css/js/images) for web, set
  `preview` for image, `audio=False` for video, emit `shader.glsl` for GLSL.
- `create(..., kind=...)` -> unified dispatcher.
- `self_test() -> (bool, str)` + `python -m lumen.creator --self-test`
  returning exit 0 = PASS.

## CRITICAL: `scan_library()` reads a MODULE-GLOBAL, not `config.LIBRARY_DIR`
`lumen/wallpaper/model.py` binds `LIBRARY_DIR` as a module-level global and
`scan_library()` reads THAT, NOT `lumen.config.LIBRARY_DIR`.

If a test wants to redirect the library to a tmp dir it MUST patch the right
module:
```python
import lumen.wallpaper.model as model
with patch.object(model, "LIBRARY_DIR", tmp_path):
    wps = model.scan_library()
```
Patching `lumen.config.LIBRARY_DIR` does NOTHING — `scan_library` never re-reads
config. (This burned a full test cycle before the fix; the assertion that the
created wallpaper shows up in `scan_library()` only passes with the correct
patch target.)

## Native URL entry (avoids the `.format()` trap)
DO NOT wrap a user URL in a hand-written iframe HTML file and `.format()` it.
The HTML/CSS contains literal braces (`body { margin: 0 }`) which `str.format`
treats as a field reference -> `KeyError: 'margin'`.

Instead, emit a manifest that points the engine directly at the URL:
```python
manifest = {
    "id": wid,
    "kind": "web",
    "entry": url,   # a bare http(s) URL — NO local index.html
}
```
This matches Wallpaper Engine "URL" semantics and produces a `Wallpaper` whose
`is_renderable()` is True without any local file. Use this for `create_from_url`.

NOTE: `is_url` is NOT a manifest key — it is a COMPUTED property on the model
(`kind == KIND_WEB and str(entry).startswith("http")`). Do not write `is_url`
into `lumen.json`; just store the URL as `entry` with `kind="web"` and the
property derives it. (An earlier version of this doc wrongly listed `is_url`
as a manifest field.)

### `is_url` is CASE-SENSITIVE — canonicalize the scheme (verified defect)
Because the property tests `entry.startswith("http")` case-SENSITIVELY, an
uppercase-scheme URL (`HTTPS://example.com`) is stored verbatim, `is_url`
returns False, and the entry is treated as a non-renderable LOCAL path — a
silent white-screen bug. model.py is CORE (untouchable), so fix it in the
creator by canonicalizing before storing:
```python
from urllib.parse import urlparse, urlunparse
parsed = urlparse(url)
if parsed.scheme not in ("http", "https") or not parsed.netloc:
    raise ValueError(...)
url = urlunparse(parsed)   # urlparse lower-cases the scheme -> is_url works
```
Lock it with `create("HTTPS://X/Y")` asserting `wp.is_url and wp.is_renderable()`.

If you MUST template HTML/JS with `.format()`, escape every literal brace as
`{{` / `}}` first, or use `string.Template` with `$field` placeholders.

## Enforce the renderable contract at creation (`_finalize` guard)
"Every produced wallpaper renders" is only TRUE if you enforce it. A
pathological source — an empty/undetectable directory, or a forced `kind` with
no matching media — otherwise writes a manifest whose entry file does not exist
=> a dead entry (`is_renderable() == False`) silently lands in the Library.
Route EVERY return path through one guard instead of returning the loaded
wallpaper directly:
```python
def _finalize(dest_root, wid):
    wp = _load_wallpaper(dest_root, wid)
    if not wp.is_renderable():
        shutil.rmtree(dest_root / wid, ignore_errors=True)  # no half-written entry
        raise ValueError(f"created entry {wid!r} is not renderable: ...")
    return wp
```
This turns a silent void into a loud, caught failure and keeps the Library
clean. Test both the empty-dir and forced-kind-without-media cases assert
`ValueError(match="not renderable")` AND that no folder is left behind.

## Library manifest / Wallpaper model fields (the contract)
A library wallpaper = a folder under `LIBRARY_DIR` containing `lumen.json`
whose keys map onto `Wallpaper` dataclass fields in
`lumen/wallpaper/model.py`. Fields successfully exercised by `creator.py`
(verify against model.py if it drifts):
- `id` (str, folder name; safe-char sanitized — see below)
- `kind` (one of the `KIND_*` constants: `web` / `image` / `video` / `shader`)
- `entry` (path or URL)
- `is_url` (bool) — True when `entry` is a URL
- `audio` (bool) — set False for video so it renders silently
- `preview` (path) — set for image wallpapers
- `shader` / `html` / `video` / `image` — kind-specific payload paths
- `fps`, `loop`, `volume`, `mute` — playback knobs

## ID sanitization
Folder/`id` names must be filesystem-safe. Build an ALLOWED-CHAR set explicitly
(`a-z0-9_.`) and drop everything else — including `-` — then collapse runs and
`_`-join. A naive regex like `[^a-z0-9_.-]` keeps `--`/`__`, which
`assert sanitize_id("a--b__c") == "a_b_c"` will then fail. Map, strip,
collapse, lower.

## Collision policy (UX-safe, test-friendly)
- `overwrite=True` + id exists -> reuse the same folder in place (overwrite
  `lumen.json` + assets). Test can then re-scan and find the SAME id back.
- `overwrite=False` + id exists -> auto-uniquify (`dup` -> `dup_2`, `dup_3`,
  ...) so a previously-created id NEVER silently clobbers a sibling's work and
  NEVER raises. Test asserts the second create returns a DIFFERENT id
  (`dup_2` != `dup`). This beats raising `FileExistsError`.

## Hard requirement: every produced wallpaper MUST render
In `self_test()`, assert `wp.is_renderable()` for every created entry (url,
html, image, video, glsl, dir-web). A wallpaper that isn't renderable is a
white/black void on LO's desktop — the exact failure class to prevent.

## Self-test exit-code caveat (already in umbrella Pitfalls)
Test the `--self-test` CLI IN-PROCESS by calling the module's main with
`["--self-test"]` AFTER monkeypatching the module global (here
`model.LIBRARY_DIR`). A `subprocess.run([... "lumen.creator", "--self-test"])`
will NOT see the parent's monkeypatch and always reports pass.
