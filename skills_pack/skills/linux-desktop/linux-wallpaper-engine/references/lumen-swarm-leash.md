# LUMEN swarm add-only build — the LEASH + headless verification

Applies when acting as a LUMEN swarm / ENI-mini builder (LMxx, workspace N):
you are asked to build ONE unclaimed add-only sub-module, prove it HEADLESS,
and write `STATUS_LM<id>.md`. This is the inverse of the live "verify on
`DISPLAY=:0.0`" rule elsewhere in this skill — swarm builders must NOT touch
the GUI/WebGL/GPU path at all.

## THE LEASH (safety-critical, recurring)
Lumen's full app has hard-rebooted LO's AMD RX5700XT 4-monitor rig (every
shader instantiates its own Chromium WebGL context; 4 simultaneous HW surfaces
hang the driver). During a swarm build the GUI/WebGL/GPU path is OFF-LIMITS:

- NEVER run `python -m lumen` / `.venv/bin/python -m lumen` (opens the GUI).
- NEVER let any code grab the X display or construct a `QWebEngineView` /
  WebGL / GPU context.
- The app stays CLOSED for the entire build.

ALLOWED: edit / fix / harden modules, `pytest`, `flake8`, `mypy`,
import-smoke ONLY.

The runtime check is handed to LO on his real X11 desktop — you prove
correctness headlessly and report what still needs the display in UNVALIDATED.

## Prove leash-safety headlessly (the import-smoke proof)
After importing your add-only module, assert that NO Qt/GUI symbols were
pulled into the process. A module that only uses pure-Python siblings
(`config`, `perf`, `model`) and lazy-imports any Qt-using module will leave
`sys.modules` empty of `PyQt6`:

```python
import sys, lumen.<your_module> as M
qt = [m for m in sys.modules if m == "PyQt6" or m.startswith("PyQt6.")]
assert not qt, f"leash violated: {qt}"
print("LEASH_OK: no Qt/GPU path entered")
```

If your module MUST touch a Qt-using API, import it LAZILY INSIDE the function
that needs it (so module import never triggers it), and keep the test path off
that function. This is why `recommend.py` builds its `HardwareProfile` from
`lumen.config` with a lazy `import lumen.config` inside `profile_from_config`,
and never imports `lumen.utils.monitors` at module scope (that needs a
`QApplication`).

## Verification stack for a swarm build (no GUI)
1. `python3 -m py_compile lumen/<new>.py tests/test_<new>.py` — syntax gate.
2. `python3 -m pytest tests/test_<new>.py -q` — real-number behavioral tests.
3. import-smoke WITH the no-`PyQt6` assertion above.
4. `flake8` / `mypy` if available. If the sandbox lacks them (PEP 668
   externally-managed env; do NOT `pip install --break-system-packages` — it can
   harm the host), SUBSTITUTE py_compile + import-smoke and note in STATUS that
   strict lint was substituted. The substitute is sufficient to prove both
   syntax and leash-safety.
5. Confirm the module is ADD-ONLY: only NEW files exist; no core sibling was
   edited. Grep the repo for any non-additive change you might have made.

## STATUS_LMxx.md convention (LUMEN swarm)
Each builder owns ONE unclaimed add-only sub-module and writes
`/home/hunter/Desktop/apps/lumen/STATUS_LM<id>.md`:
- Line 1 EXACTLY: `[state: DONE|IN-PROGRESS|BLOCKED]`
- A PASS/FAIL board with REAL numbers as evidence (not prose).
- A "what adds R / what to drop" list.
- An UNVALIDATED section for anything needing the real display / live data /
  UI wiring.
Claim your module up front (state it in STATUS so siblings don't collide).
Re-run the self-test, harden, update STATUS — loop until DONE.

## Worked example (LM10 → lumen/recommend.py)
LM10 built `lumen/recommend.py` (wallpaper recommendation + GPU-budget
auto-assignment) reusing `lumen.perf.gpu_fragment_load` for identical numbers
to the live engine — pure Python, no Qt. Verified: 9/9 pytest, import-smoke
showed 0 `PyQt6` modules loaded, per-surface cost model locked (1080p shader =
139,968,000 frag/s; video x0.40; image nominal 2,000,000; 4K shader =
559,872,000). `auto_assign` guarantees a renderable (non-blank) wallpaper per
screen even when over budget — an explicit anti-white-screen safety net.
Unvalidated: real 4-display geometry (needs the physical host) and the
`config.assignments` write-back wiring (left to the UI owner).
