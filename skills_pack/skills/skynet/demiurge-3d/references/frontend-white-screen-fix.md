# Demiurge3D Frontend White-Screen — root cause + fix (learned 2026-07-17)

## Symptom
Site "boots for a little bit then turns white."

## Diagnosis (rule out server first)
1. `curl localhost:8093/ | grep assets/index-` — if it references
   `/assets/index-*.js` and returns 200, the root HTML is served fine.
2. `curl -o /dev/null -w '%{http_code}' localhost:8093/assets/index-*.js` — 200 = bundle loads.
3. `curl -o /dev/null -w '%{http_code}' localhost:8093/api/printers` — 200 = backend APIs fine.
If ALL of the above are 200, the server + assets + APIs are healthy. The crash is
CLIENT-SIDE (a thrown React render), not the backend.

## Root cause
The React SPA had NO error boundary anywhere (`grep -rniE 'ErrorBoundary|
componentDidCatch|getDerivedStateFromError' frontend/src` = ZERO matches). A
live-telemetry component throwing during a WebSocket `printer_status` frame (e.g.
mid-calibration when the bed_mesh matrix is empty/partial, or BedMesh3D WebGL on a
bad matrix) unmounts the ENTIRE React tree -> blank page. "Boots then whites" =
mounts, WS connects and pushes a frame, a component throws, nothing catches it.

## Fix (safe, additive — does NOT touch working paths)
1. NEW `frontend/src/ErrorBoundary.tsx`:
   - class component, `getDerivedStateFromError(error)` -> `{error}`,
     `componentDidCatch` -> `console.error(...)` (so the failure is visible).
   - render(): if `this.state.error`, show a fixed dark panel with the error
     message + stack + a "Dismiss & keep running" button (app stays alive);
     else `this.props.children`.
2. `frontend/src/main.tsx`: wrap `<App/>`:
   `ReactDOM.createRoot(...).render(<React.StrictMode><ErrorBoundary><App/></ErrorBoundary></React.StrictMode>)`
3. `cd frontend && npm run build` (node22/npm9 present; ~6s, 2133 modules)
   regenerates `dist/`. Backend serves dist from disk per-request, so the new
   bundle is LIVE IMMEDIATELY — NO backend restart needed. Verify:
   `curl localhost:8093/ | grep assets/index-` shows the new hash (200).

## Why this matters
Post-fix, any panel crash renders a VISIBLE error message instead of a white void,
so future diagnosis is a paste-not-a-guess. BedMeshHeatmap 2D path already guards
empty matrices; the missing boundary + 3D/WebGL was the actual white-out.

## If it still whites post-fix
It won't go white — it'll show the error text. Paste LO the message; kill that
specific component (usually a null/NaN guard in BedMesh3D or LiveTelemetry during
an empty mesh matrix).
