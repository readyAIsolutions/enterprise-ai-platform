---
name: python-app-packaging
description: Package any Python program as three shippable targets — a web dashboard (Flask), a desktop app (PyQt6 WebView that bundles the dashboard), and an Android APK (buildozer + Kivy WebView). Use when LO asks to "give it a website / desktop app / android apk", or to ship a Python tool/bot as a product. Companion to linux-appimage-packaging (Linux-deep-dive).
---

# python-app-packaging

LO frequently wants a program shipped as **website + desktop app + android apk** (lumen is the exception: desktop-only linux by his rule). This skill is the reusable wrapper pattern that turns any Python program into those three targets with minimal code. The desktop and android targets both wrap the SAME local Flask dashboard, so you write the UI once.

## When to use
- LO: "make it have a website, a desktop app, and an android apk"
- Productizing a bot/script (DEMIURGE, StockBot, Demiurge3D all used this)
- Any "ship this as a real product" push

## The pattern (3 targets, 1 dashboard)
1. **web/ dashboard** — `web/app.py`, a Flask app.
2. **desktop/ launcher** — `desktop/launcher.py`, PyQt6 `QWebEngineView` that spawns the Flask app and loads it.
3. **android/** — `buildozer.spec` + `main.py` (Kivy `WebView` that spawns Flask in a thread).

All three point at one Flask server on a fixed PORT.

## Steps
1. Create `web/app.py` (see templates/web_app.py). Rules:
   - Import only `flask` at top. **Lazy-import the program core inside route handlers** so the server boots instantly and never crashes on a heavy import at startup.
   - `/` renders a dashboard (status + gate report JSON if present).
   - `/selftest` imports the core modules and returns JSON `{module: "ok"|"ERR ..."}` — this is your boot proof.
   - Pick a unique PORT per program (8081, 8082, 8093…).
2. Create `desktop/launcher.py` (templates/desktop_launcher.py): `subprocess.Popen([sys.executable, web/app.py])`, then a `QWebEngineView` loading `http://localhost:PORT/`. Terminate the server on app exit.
3. Create `android/buildozer.spec` + `android/main.py` (templates/). `main.py` runs Flask in a daemon thread and shows a `kivy_garden.webview.WebView` at `127.0.0.1:PORT`.
4. **Verify** (do this before claiming done):
   - Boot Flask: `curl -s -o /dev/null -w "%{http_code}" localhost:PORT/` → expect `200`; hit `/selftest` → expect JSON with all `ok`.
   - Boot desktop headless: `QT_QPA_PLATFORM=offscreen python desktop/launcher.py` with a `timeout`, then `curl` the port again → still `200`, process alive. (offscreen avoids needing an X display; the WebView errors about "desktop window properties" are harmless offscreen quirks, not failures.)
5. **Android APK is build-ready, not built here.** Compiling needs `buildozer` + the Android SDK (multi-GB, not on the dev box). Ship spec+main and tell LO: `cd android && buildozer android debug` on a build host.

## Pitfalls (learned the hard way)
- **PyQt6 ≠ PyQt6-WebEngine.** `QWebEngineView` lives in `PyQt6.QtWebEngineWidgets`, a SEPARATE pip package. A bare PyQt6 install gives `ModuleNotFoundError: No module named 'PyQt6.QtWebEngineWidgets'`. Fix: `pip install PyQt6-WebEngine`.
- **Flask is often missing** from a program venv that otherwise has pandas/sklearn/pyqt. `pip install flask`.
- **Flask 2.x incompatible with Python 3.14+.** Flask 2.3.2 (and earlier 2.x) uses `pkgutil.get_loader` which was removed in Python 3.14, causing `AttributeError: module 'pkgutil' has no attribute 'get_loader'` at startup. Fix: upgrade to Flask 3.x (`pip install flask>=3.1.3`). Pin `flask>=3.1.3,<4` in requirements to avoid this class of breakage.
- **exFAT USB drives** (e.g. the DEMIURGE plugged drive): Python runs fine there (no exec bit needed), but git repos are unhappy (no symlinks/permissions). Copy source with `tar`, not by relying on git. Don't put a real `.git` you depend on there.
- **Lumen-style native PyQt6 apps** are desktop-only by LO's rule — do NOT force a web dashboard or android target on them.
- **Heavy deps on Android:** pandas/sklearn in the APK make a big build but buildozer handles it; just list them in `requirements`.
- **Credential hygiene:** if the program uses an API key (e.g. OANDA), keep the key in exactly ONE program's `.env`; copy source only (exclude `.venv`, `build`, `__pycache__`, `.git`) when cloning into a new repo so the secret doesn't leak across "never intertwine" boundaries.
code
## Support files
- `templates/web_app.py` — generic Flask dashboard + /selftest.
- `templates/desktop_launcher.py` — PyQt6 WebView launcher.
- `templates/android_main.py` — Kivy WebView + threaded Flask.
- `templates/buildozer.spec` — requirements + INTERNET permission.
- `references/admin_ui_patterns.md` — admin dashboard UI patterns for checkbox mutual exclusion, empty-state stats, and OAuth localhost.
- `references/env-persistence-pattern.md` — environment variable persistence patterns for admin settings forms.

## Overlap note
This sits beside `linux-appimage-packaging` (which goes deeper on the Linux AppImage specifically). Prefer this skill when the ask is multi-target (web+desktop+android); use `linux-appimage-packaging` when LO specifically wants a self-contained Linux AppImage.
