# D3D mini-build recipe (ADD-ONLY) — proven end-to-end loop

Condensed, copy-pasteable verification loop for a DEMIURGE3D mini-builder
(D3Dnn / Bnn). Distilled from the D3D13 G-code QA report build, which ran
clean end-to-end with zero course-corrections. Complements the conceptual
sections in SKILL.md ("Choosing an unclaimed ADD-ONLY sub-module", "ENI
mini-builder sub-task + STATUS convention"). Use this for the *order and the
exact commands*; use those sections for the *rationale*.

## 0. Hard rules (non-negotiable)
- ADD-ONLY. Build a NEW module; never edit `gcodeparser.py`, `cli.py`,
  `forge/__init__.py`, `server.py` printer routes, or any sibling STATUS.
- Read-only by construction: a forge/QA consumer must not import `moonraker`,
  `httpx`, `requests`, `urllib`, `socket`, `telnetlib`.
- Do NOT start prints / send gcode. This is forging + QA only.

## 1. Find an unclaimed gap (disk, not rumor)
```bash
cd /home/hunter/Desktop/demiurge-3d
# a) who claims what
search_files STATUS_*.md  for  "Owner:|builder:|Module:"
# b) does the candidate module + its test already exist?
search_files backend/forge  for  "<candidate>.py"
search_files backend/tests  for  "test_<candidate>.py"
```
A module with NO `test_*.py` is a real, unclaimed gap (e.g. `gcodeparser.py`
had none -> build a consumer + the missing coverage). A module that EXISTS with
a test is claimed -> pivot to a NEW consumer instead.

## 2. Collision check by CONCEPT, not just filename
```bash
# grep the concept across both STATUS and code
search_files STATUS_*.md        for  "gcode|analyze|report|layer|orient"
search_files backend/forge/*.py for  "gcode_report|analyze_gcode|..."
```
If a sibling owns the concept under a different filename, FLAG it in your
STATUS and build a DISTINCT value-add (or stop) -- never duplicate/edit.

## 3. Build the new module (consumer shape)
Pattern that works: import the stable read-path, add value, never re-implement.
```python
from .gcodeparser import parse_gcode, ParseResult   # read-path, untouched
# add: analysis + report + selfcheck() returning a dict of real values
```
Always add a `selfcheck()` that parses a tiny inline fixture and returns real
computed numbers -- it becomes your STATUS evidence.

## 4. Run YOUR tests with the project venv
```bash
cd /home/hunter/Desktop/demiurge-3d/backend
/home/hunter/Desktop/demiurge-3d/.venv/bin/python -m pytest tests/test_<mod>.py -v
```
TRAP: the venv is at the **repo root** `.venv`, NOT `backend/.venv`. `cd
backend` first, then call the absolute `.venv/bin/python` path.

## 5. Full-suite regression + honest "not mine" report
```bash
/home/hunter/Desktop/demiurge-3d/.venv/bin/python -m pytest tests/ -q --tb=no \
  | grep -E '^(FAILED|ERROR)' | sed -E 's/::.*//' | sort | uniq -c | sort -rn
```
Report the totals AND enumerate the failing FILES. Confirm NONE of them are
yours. Pre-existing failures here are async-harness/env
(`test_retry` async-defs, `test_fleet_*`, `test_asset_pipeline`,
`test_support_estimator`, `test_thermal_watch`) -- they are NOT regressions
from an additive change. State "0 new failures attributable to this module."

## 6. STATUS file (line 1 = [state: DONE])
Write `STATUS_D3D<nn>.md` at the repo root with: a real PASS/FAIL board
(actual test counts + `selfcheck()` dict), a "what adds R / what to drop"
list, and an UNVALIDATED section (live printer / scale / real-slicer items
blocked by the USB-DEMIURGE / subnet blockers).

## Gotcha bank (carried from this build)
- **`gcodeparser` empty-marker layers**: a bare `;LAYER:N` comment emits an
  empty `Layer` (0 moves) before the real `G1 Z..` layer. A 2-layer print is
  recorded as 4 `Layer` objects. Collapse with
  `[ly for ly in result.layers if ly.moves]` before counting layers.
- **Bounding-box perimeter**: a single `G1 X100 Y80 Z30` yields width=0
  (xmin==xmax). Trace a full perimeter to get real width/depth.
