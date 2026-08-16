# Demiurge3D Frontend — White Screen Fix + Delivery Notes

## White screen after boot (root cause + fix, 2026-07-17)
Symptom: site returns HTTP 200, all `/assets/*.js` + `*.css` return 200, all boot
APIs (`/api/printers`, `/api/sessions`) answer 200 — but the page "boots for a
little bit then turns white."

Root cause: the React SPA has NO top-level error boundary. Confirmed by:
`grep -rniE 'ErrorBoundary|componentDidCatch|getDerivedStateFromError' frontend/src`
-> ZERO matches. The WebSocket `/api/printer/ws` (upgrades fine, HTTP 101) pushes
`printer_status` frames into the zustand store. During printer calibration the
live data can be partial/empty (e.g. `bed_mesh.mesh_matrix:[[]]` mid-probe). Any
component that throws on that data unmounts the ENTIRE React tree -> blank.
"Boots then white" = mounts, WS connects, first bad frame crashes, no boundary.

Fix (additive, safe — does NOT touch working paths):
1. NEW `frontend/src/ErrorBoundary.tsx` — class component:
   - `getDerivedStateFromError` stores the error.
   - renders a dark fallback panel (amber title, red `<pre>` with
     `error.message` + `error.stack`, and a "Dismiss & keep running" button that
     clears state) INSTEAD of blanking.
   - `componentDidCatch` logs to console for diagnosis.
2. Wrap `<App/>` in `frontend/src/main.tsx`:
   `<ErrorBoundary><App/></ErrorBoundary>` inside `<React.StrictMode>`.
3. `cd frontend && npm run build` (node v22 / npm 9 present; ~6s, 2133 modules).
   Regenerates `dist/`.

CRITICAL: the backend serves `dist/` FROM DISK per request — NO backend restart
needed. Verify live: `curl -s localhost:8093/ | grep -oE 'assets/[a-zA-Z0-9_-]+\.js'`
-> shows the NEW hash (e.g. `index-Cmb5cDdv.js`), and
`curl -s -o /dev/null -w '%{http_code}' localhost:8093/assets/index-Cmb5cDdv.js` -> 200.

Bonus: after the boundary exists, future failures are VISIBLE (error text instead
of white). If a panel still errors, LO pastes the red console text -> exact
component identifiable. The 2D `BedMeshHeatmap` is already guarded against empty
matrices (early-returns on 0 rows/cols); the throw is elsewhere (or the 3D
`BedMesh3D` WebGL view) during calibration — the boundary is the universal fix.

## Delivery discipline — avoid the terminal output-length popup
LO's terminal warns on over-long output ("be wary of that output length popup").
During long ops (forge builds, calibration, multi-step runs): deliver SHORT,
scannable blocks (caveman-style summary is fine for him); if more detail is
needed he says "continue". Do NOT paste full tool output / long JSON / verbose
logs into the visible reply — summarize the evidence (e.g. "P1 nozzle 214->230,
live") and offer raw detail on request.
