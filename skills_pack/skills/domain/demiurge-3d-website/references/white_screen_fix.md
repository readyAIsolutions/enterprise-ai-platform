# White-Screen Fix — Demiurge3D Frontend (2026-07-17)

## Symptom
LO: "it boots for a little bit then website turns white." Site is http://localhost:8093.

## Diagnosis steps (what was checked, in order)
1. `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8093/` -> 200. Server up.
2. Root HTML (`curl /`) -> correct SPA shell referencing `/assets/index-*.js`. Backend serves
   the built frontend fine.
3. `curl /assets/index-*.js` / `.css` / `/favicon.svg` -> all 200, non-zero size. Assets load.
4. Boot APIs `/api/printers` `/api/sessions` -> 200 with real data. `/api/queue` -> 405.
   API layer works.
5. `curl -i` against `/api/printer/ws` -> `101 Switching Protocols` (WebSocket upgrades OK).
6. `grep -rniE 'ErrorBoundary|componentDidCatch|getDerivedStateFromError' frontend/src` ->
   ZERO matches. **No error boundary exists.**
7. Live printer status during calibration showed `bed_mesh.mesh_matrix:[[]]` and empty
   `mesh_min/max` -- a partial/empty mesh frame. A telemetry component mapping over that throws
   with no boundary -> entire React tree unmounts -> white.

## Root cause
React SPA with live WebSocket telemetry + NO top-level ErrorBoundary. Any render throw
(most visibly during calibration when mesh data is empty/transient) blanks the whole app.
"Boots then whites" = mounts, WS connects and pushes frames, a frame hits a component that
chokes, nothing catches it, blank.

## Fix applied (safe, additive)
- NEW `frontend/src/ErrorBoundary.tsx`: catches render errors, renders a fixed dark panel with
  the error message + stack (so failures are VISIBLE, not blank), keeps siblings alive, has a
  "Dismiss & keep running" button.
- `frontend/src/main.tsx`: wrap `<App/>` in `<ErrorBoundary>`.
- `cd /home/hunter/Desktop/Demiurge3D/frontend && npm run build` -> exit 0, 2133 modules,
  new bundle. Backend serves `dist/` from disk per request, so the new bundle is live immediately
  (no backend restart needed). Verified: root HTML now references the new hash and returns 200.

## Verification
Reload http://localhost:8093. Two outcomes:
- Stays up -> boundary caught whatever was throwing, app survives.
- Shows a dark error panel with red text -> that IS the root cause; paste it, fix the component.
Either way: no more silent white screen.

## Bonus signal during this fix
Live `/api/printer/5/status` showed bed 99.85C (target 95) mid-calibration -> the BEDPID step
had run live on hardware, proving calibration was progressing (not a dead printer).
