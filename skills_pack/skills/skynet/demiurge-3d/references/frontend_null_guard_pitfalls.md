# Frontend null-guard pitfalls (Demiurge3D React/TS, learned 2026-07-17)

## SYMPTOM
App boots then WHITES OUT (or a panel throws "Cannot read properties of null
(reading 'toFixed')"). Stack trace lands in a `react-three` / `three` bundle.

## ROOT CAUSE
Live telemetry from the Moonraker WS can carry `null` for fields the UI calls
`.toFixed()` on — specifically `temps.bedTarget`, `temps.extruderTarget`,
`belt.x`, `belt.y` during calibration/idle (targets unset), and `belt` itself
when the sensor is uncalibrated. Calling `.toFixed()` on `null` throws and
(until the ErrorBoundary existed) white-screened the whole SPA.

## FIX PATTERN (applied 2026-07-17)
Null-guard every `.toFixed` call on live data. Two safe forms:
```tsx
// form A: coalesce to 0 before formatting
{temps.bedTarget ?? 0).toFixed(0)}°
// form B: guard the whole value (belt can be null)
{value != null ? `${value.toFixed(1)}N` : 'Uncalibrated'}
```
Files touched: `App.tsx`, `LiveTelemetry.tsx`, `PrinterPanel.tsx`,
`BeltTensionDial.tsx`, `BedMeshHeatmap.tsx` (min/max/mean from the 2D canvas
effect — guard with `?? 0`).

## DEFENSE IN DEPTH — ErrorBoundary (ADD-only, safe)
The original frontend had NO ErrorBoundary, so any render throw white-screened
with zero diagnosability. Added `frontend/src/ErrorBoundary.tsx` and wrapped
`<App/>` in `main.tsx`:
```tsx
<ErrorBoundary><App/></ErrorBoundary>
```
Now a thrown render shows the error message + stack in-panel instead of a blank
screen — this is what surfaced the `toFixed(null)` cause as a readable message
instead of white. KEEP the boundary; it is the difference between "white screen,
no clue" and "here is the exact line that threw."

## REBUILD AFTER EDITS
`cd frontend && npm run build` — verify the NEW bundle hash is served
(`curl :8093/ | grep assets/index-<hash>.js` changes; `curl -o /dev/null -w
"%{http_code}" :8093/assets/index-<hash>.js` = 200). The dev server / backend
serves `dist/`, so a stale bundle means the fix isn't live.

## NOTE — BedMesh3D.tsx is ALREADY guarded
Unlike the 2D/Dashboard components, `BedMesh3D.tsx` already returns "Irregular
mesh — 2D view only" when `matrix` is null/short. The `toFixed` crash was NOT
there — it was the dashboard telemetry. Don't "fix" BedMesh3D; fix the
telemetry reads.
