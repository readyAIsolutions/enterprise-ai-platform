# Headless Qt / PyWebEngine self-test abort — triage + fix recipe

When an ENI mini's self-test is a pytest suite that touches PyQt6 / PyWebEngine,
a red run can be caused by an UNCATCHABLE hard abort, not a logic defect. This is
the pattern ENI_LUMEN hit resuming LUMEN (PASS 4): the suite had regressed to
5 failures + 1 hard Chromium SIGABRT that killed the whole run.

## The failure mode
- Constructing a `QWebEngineView` (or any `QWebEngine*` surface) launches
  Chromium's GPU + renderer processes. In a displayless or sandboxed agent
  runtime these can fail with a C-level `qt_assert` -> `Fatal Python error:
  Aborted` (SIGABRT).
- SIGABRT is NOT a Python `Exception`, so a `try/except Exception` / `pytest.skip`
  guard INSIDE the test cannot catch it. The whole pytest process dies and every
  test after the abort is lost.
- Symptom in output: a few `F` lines, then `Fatal Python error: Aborted` with a
  traceback rooted in `libQt6WebEngineCore.so.6`. The run is reported as a
  crash/red, hiding the real per-test results.

## Triage (so you see the real RED)
1. Re-run with the suspect file deselected to surface ordinary assertion failures:
   `pytest -q -p no:randomly --deselect tests/test_surfaces.py --tb=line`
   (replace the file with whichever one constructs the view / aborts).
2. Read the `-F` lines. Those are the fixable harness bugs.
3. The abort itself is an ENVIRONMENT LIMITATION, not a code defect — confirm by
   checking it only fires where no working Chromium GPU context exists.

## Fix pattern (harness only — never touch the core)
Gate the aborting test behind an opt-in env var so it skips cleanly headless and
still runs on a real desktop:
```python
def test_web_wallpaper_constructs_offscreen():
    # Chromium init can hard-abort (SIGABRT) in a displayless/sandboxed env and
    # Python can't catch it, so only attempt when explicitly opted in.
    if not os.environ.get("LUMEN_RUN_WEBENGINE_TESTS"):
        pytest.skip("set LUMEN_RUN_WEBENGINE_TESTS=1 on a real X desktop to run")
    try:
        scr = _screen()
        w = WebWallpaper(scr, _wp("web", entry_path=None), interactive=False)
    except Exception as exc:  # pragma: no cover - env dependent
        pytest.skip(f"QWebEngine unavailable: {exc}")
    assert w.geometry().width() == scr.geometry().width()
```
Document in STATUS as KNOWN LIMITATION / UNVALIDATED (live path = LO's desktop).
Run on a capable host with: `LUMEN_RUN_WEBENGINE_TESTS=1 pytest tests/test_surfaces.py::test_web_wallpaper_constructs_offscreen`.

## Harness-staleness checklist (when the suite reads RED but the core is fine)
Run the failing tests individually with `--tb=long` and check the core's ACTUAL
behavior (read the source, don't trust the doc) before concluding a defect:
- **Wrong equality on a transform**: asserting `== (200,80)` for a "fill" / cover
  scale mode — the core correctly returns `>= target in both dims`
  (`KeepAspectRatioByExpanding`); overflow is cropped at paint time. Assert the
  cover contract (`>=` + source-aspect preserved), not exact size.
- **Missing fixture mkdir**: a test monkeypatches a cache/output dir but never
  creates it -> `FileNotFoundError` on write. Add `cachedir.mkdir(parents=True,
  exist_ok=True)` inside the fixture.
- **Doubled path from `folder == root/id`**: if the core model computes
  `folder = self.root / self.id`, the test must pass the ROOT (library dir) to
  the constructor, not `root/id`. Passing `root/id` doubles it to `root/id/id`.
- **Asserting a mutation the function doesn't do**: e.g. `build_shader_html`
  returns the cached path but does NOT mutate `wp.entry` (that's
  `ShaderWallpaper.__init__`'s job). Assert the file it writes, not the attr.

## Doc-vs-disk contradiction (worked example)
STATUS_LUMEN.md PASS 3 claimed `QTWEBENGINE_DISABLE_SANDBOX` is REQUIRED and "do
NOT remove"; STATUS_ENI_LUMEN.md PASS 3 claimed it was removed (GPU sandbox ON).
On-disk `grep` confirmed the ENI's version: no sandbox-disable in `app.py` or
`AppRun`. Per the protocol the on-disk contract wins; the master-status line was
stale. Always re-verify the disk, never trust the doc.
