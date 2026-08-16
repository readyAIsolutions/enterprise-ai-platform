# Read-only status bridge — verify Demiurge-3D WITHOUT editing it

Use this when LO (or an ENI mini) asks for a *status report / bridge* on the Demiurge-3D
app: "what's the build status, what does the GUI do, what's the next concrete step" — with
an explicit **DO NOT EDIT** constraint. The goal is a verified `ENI_3D_bridge.md` +
`STATUS_ENI11.md` pair (or similar), not a code change.

All commands below were re-verified live on 2026-07-09 and are read-only / transient-boot
only (the boot is killed afterward). Copy-paste safe.

====================================================================
## 0. THE #1 TRAP
====================================================================
The venv is at the **REPO ROOT**: `/home/hunter/Desktop/demiurge-3d/.venv`
NOT `backend/.venv`. Boot/run with `/home/hunter/Desktop/demiurge-3d/.venv/bin/python`.
(A prior bridge literally got this wrong once — the `backend/.venv` path does not exist.)

====================================================================
## 1. VERIFICATION COMMAND SET (read-only, re-verified)
====================================================================
# --- Git state ---
cd /home/hunter/Desktop/demiurge-3d
git status --short            # untracked/modified files = "the gap" candidates
git branch --show-current     # usually 'main'

# --- Orphaned / unwired module detection (how to find the next step) ---
#   Grep the feature keyword across backend. A module that is present + tested but has
#   0 references in server.py and no matching /api/* route is ORPHANED == the next step.
cd /home/hunter/Desktop/demiurge-3d
grep -rn "estimate" backend/server.py                 # only unrelated hits? (e.g. print_duration_estimate)
grep -n '"/api/estimate"' backend/server.py || echo "NO /api/estimate ROUTE"
grep -rn "from demiurge.estimator\|import estimator\|estimate_print" backend --include=*.py \
  | grep -v "estimator.py\|test_estimator.py"          # 0 hits (outside the module itself) = orphaned
#   WARNING: similar-looking names are DIFFERENT functions. On 2026-07-09 the only
#   "estimate" matches were `estimate_print_cost` (demiurge/hueforge/cost_estimator.py)
#   and `estimate_print_time` (demiurge/origami/generator.py) — NEITHER wires in the
#   standalone `demiurge.estimator.estimate_print`. Read each match; don't assume.

# --- Backend live boot + HTTP smoke (transient; KILL after) ---
cd /home/hunter/Desktop/demiurge-3d/backend
/home/hunter/Desktop/demiurge-3d/.venv/bin/python server.py > /tmp/d3_boot.log 2>&1 &
#   poll:  curl -s -o /dev/null http://localhost:8093/   until HTTP 200
#          grep "Application startup complete" /tmp/d3_boot.log
curl -s -o /dev/null -w 'HTTP %{http_code}\n' http://localhost:8093/
curl -s http://localhost:8093/api/status | head -c 200     # 15-agent roster JSON
#   KILL the pid when done. NOTE: this boot starts the "Hermes 24/7 / self-improvement"
#   loop (see SKILL.md runtime-self-edit pitfall). Keep the boot BRIEF and kill promptly.
#   For pure verification, prefer `scripts/verify_offline.py` (TestClient) — no live loop.

# --- Backend tests ---
cd /home/hunter/Desktop/demiurge-3d
.venv/bin/python -m pytest backend/tests -q      # 19 passed (2026-07-09; count grows as
                                                 # modules are added — re-check, don't hardcode)
#   4 non-blocking warnings: Pydantic V1 @validator deprecation + @app.on_event("startup")
#   deprecation. Both safe to ignore for a status report.

# --- Frontend type-check (read-only) ---
cd /home/hunter/Desktop/demiurge-3d/frontend
npx tsc --noEmit                                 # exit 0 == no type errors

# --- Frontend build freshness (does dist need a rebuild?) ---
#   Compare mtime of dist/index.html vs the newest touched source.
stat -c '%y %n' /home/hunter/Desktop/demiurge-3d/frontend/dist/index.html
stat -c '%y %n' /home/hunter/Desktop/demiurge-3d/frontend/src/App.tsx \
              /home/hunter/Desktop/demiurge-3d/frontend/src/components/forge/Forge3D.tsx
#   If dist/index.html is NEWER than every src file -> dist is CURRENT, no `npm run build`.
#   (2026-07-09: dist 10:33:40 > App.tsx 08:09 > Forge3D.tsx 07-08 23:13 -> current.)

# --- GUI tab inventory (read from src, no browser needed) ---
grep -n "type Tab = " frontend/src/App.tsx       # 9 tabs:
#   dashboard | forge | tuning | store | filaments | files | print | settings | about
#   Flagship = Forge 3D (components/forge/Forge3D.tsx): text/photo -> spec -> OpenSCAD->STL,
#   react-three-fiber live preview, optional Meshy AI-mesh at /api/forge/meshgen/*.
#   Routes the GUI actually calls (grep Forge3D.tsx): /api/forge/understand, /api/forge/photo,
#   /api/forge/build, /api/forge/meshgen/{text,photo,status,build}.

====================================================================
## 2. WORKED EXAMPLE — the current known gap (RE-VERIFY before acting)
====================================================================
On 2026-07-09 the orphaned module was `backend/demiurge/estimator.py` (191 lines):
  estimate_print(volume_cm3, infill_percent, price_per_kg, print_speed_mms,
                 *, density_g_per_cm3=1.24, layer_height_mm=0.20, line_width_mm=0.40,
                 shell_fraction=0.12, overhead_factor=1.5) -> dict
  returns effective_volume_cm3, mass_g, filament_cost_usd, print_time_h,
  total_cost_usd, assumptions. Has argparse CLI + ValueError validation.
  Tests: backend/tests/test_estimator.py (sample_input_is_sane, infill_boundaries,
  invalid_inputs_raise) -> all green (part of the 19 passed).

State then: COMPLETE + TESTED but ORPHANED — no `/api/estimate` route, not imported
anywhere, still untracked in git. Recommended next step (for LO to execute, NOT a bridge
edit): add POST /api/estimate to server.py, show a Cost/Time panel in Forge3D.tsx, then
`git add` + commit the two untracked files.

⚠ This is SESSION STATE — re-run §1 before treating it as current. If it's since been
wired/committed, the gap has moved; find the new orphan the same way.

====================================================================
## 3. SELF-HEAL (if the bridge process dies and restarts)
====================================================================
1. Re-read ENI_3D_bridge.md + STATUS_ENI11.md in ~/Commander/eni_swarm.
2. Re-run §1 (especially the orphaned-module grep + live smoke). State may have moved.
3. DO NOT `npm run build` or edit Demiurge-3D source unless LO explicitly directs it.
4. Continue from "expose the orphaned module" unless LO gave a newer directive.
5. Keep STATUS_ENI11.md current after every action; never let it go stale silent.
