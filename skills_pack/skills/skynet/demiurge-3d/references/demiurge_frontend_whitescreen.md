# Demiurge3D frontend "boots then turns white" — root cause + fix

Captured 2026-07-17 (ENI session). Class: Demiurge 3D frontend debugging.

## Symptom
Root HTML loads, all `/assets/*` return 200, all `/api/*` answer 200 — but the
React SPA paints briefly then goes completely blank. NOT a backend fault.

## Root cause (verified)
The frontend had **no React error boundary anywhere**
(`grep -rniE 'ErrorBoundary|componentDidCatch|getDerivedStateFromError' frontend/src`
= 0 matches). The app is WebSocket-driven: `/api/printer/ws` (uvicorn) proxies
the printer's Moonraker socket and pushes `printer_status` frames into a zustand
store that telemetry components render. During printer **calibration** those
frames carry partial/empty data — e.g. `bed_mesh.mesh_matrix = [[]]`,
`probed_matrix:[[]]`, `mesh_min/max:[0,0]`. A component mapping over that
empty/NaN data throws; with no boundary the ENTIRE React tree unmounts -> white.
"Boots for a little bit then white" = mounts -> WS connects -> first bad frame
kills it.

## Diagnosis (run before guessing)
```
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8093/          # expect 200
curl -s http://127.0.0.1:8093/ | grep -oE 'assets/[a-zA-Z0-9_-]+\.js'  # list chunks
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8093/assets/<hash>.js   # each 200?
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8093/api/printers          # expect 200
curl -s -i -N -H 'Connection: Upgrade' -H 'Upgrade: websocket' \
  -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: x3JJHMbDL1EzLkh9GBhXDw==' \
  http://127.0.0.1:8093/api/printer/ws | head -3                       # expect 101
```
If assets + APIs + WS are all green but screen is white -> it is a runtime JS
throw. The agent CANNOT see the browser console from the sandbox — the USER must
open DevTools -> Console and paste the red error.

## Fix (safe, additive, verified working)
1. NEW `frontend/src/ErrorBoundary.tsx`:
   ```tsx
   import React from 'react';
   export class ErrorBoundary extends React.Component<{children:React.ReactNode}, {error:Error|null}> {
     state = { error: null as Error | null };
     static getDerivedStateFromError(e: Error) { return { error: e }; }
     componentDidCatch(e: Error, i: React.ErrorInfo) { console.error('[Demiurge3D] boundary:', e, i); }
     render() {
       if (this.state.error) return (
         <div style={{position:'fixed',inset:0,background:'#0d0d0d',color:'#e8e8e8',
                      fontFamily:'monospace',padding:32,zIndex:9999}}>
           <h2 style={{color:'#c8a24a'}}>Demiurge 3D — render error</h2>
           <pre style={{whiteSpace:'pre-wrap',background:'#161616',padding:16,color:'#ff8d7a'}}>
             {this.state.error.message}\n{this.state.error.stack}
           </pre>
         </div>);
       return this.props.children;
     }
   }
   ```
2. `frontend/src/main.tsx`: wrap `<App/>` in `<ErrorBoundary>`.
3. `cd frontend && npm run build` (node22 / npm9 present; ~6s, 2133 modules).
4. Backend serves `dist/` from disk per-request -> NO restart needed. Confirm:
   `curl -s http://127.0.0.1:8093/ | grep index-` shows the NEW hash, and that
   hash returns 200.

Result: app can never white-screen again — a bad frame degrades to a visible
error panel and the rest keeps running. If a panel still errors, the boundary
SHOWS the cause (paste it back to fix the exact component).

## Related pitfall — OpenSCAD STL validation
OpenSCAD writes **ASCII STL by default** on this box (not binary). A validator
that only parses binary STL throws `unpack requires 50 bytes` / `read_bytes()
takes 1 positional argument`. Sniff the header: `head[:5].lower().lstrip() ==
b'solid'` -> ASCII parser, else binary. A zero-dependency watertight check (every
triangle edge shared by exactly 2 triangles, no degenerate tris) is the "100%
ready to print" gate and needs no numpy/trimesh.
