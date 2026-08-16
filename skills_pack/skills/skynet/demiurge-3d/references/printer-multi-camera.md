# Per-printer multi-camera rendering (K2 Plus, 2 cams)

## Symptom LO reported
"2 cams per printer, that none show up." A printer with TWO cameras (nozzle +
chamber) rendered a BLANK camera panel instead of two feeds.

## Root cause (two stacked bugs)
1. FRONTEND `frontend/src/components/dashboard/PrinterPanel.tsx`: the camera
   grid keyed each tile with `key={cam.kind}`. React requires list keys to be
   UNIQUE among siblings. When 2 cams were present the keys collided and React
   silently dropped the whole list -> blank panel. CLASSIC "items vanish the
   moment there are 2+" React pitfall.
2. BACKEND `demiurge/printer/manager.py` `discover_cameras`: it `break`'d after
   the first nozzle cam and only probed a chamber `if len(found) < 2`, which
   could collapse/mishandle the second stream; a same-kind collision would feed
   the broken frontend key.

## The fix (committed, proven live)
- Backend: `discover_cameras` now probes BOTH nozzle + chamber UNCONDITIONALLY,
  dedupes true duplicate streams by `snapshot_url`, re-tags any same-kind
  collision with a unique suffix. Added `CameraInfo.id` (stable unique per
  `kind:stream_url`).
- Endpoint `/api/printer/{id}/cameras` returns `id` alongside name/kind/urls.
- Frontend: tiles key on `cam.id` (fallback `kind+stream_url`); added
  `id?: string` to the `Camera` interface.
- Tests: `tests/test_camera_2per_printer.py` (3 pass) + `tsc --noEmit` clean.

## LIVE VERIFY (against real hardware)
Printers registered in `~/.cali-agent/webapp.db` (`printers` table: id,
moonraker_url). K2 fleet = ids 5/6 at :7125. Boot backend on :8093, startup
auto-connects. Prove with:
  curl -s http://localhost:8093/api/printer/5/cameras
  curl -s http://localhost:8093/api/printer/6/cameras
Expect 2 entries each with distinct `id` (nozzle:...:8081/snapshot and
chamber:...:4408/webcam2/?action=stream).

## Caveat
Discovering the chamber relies on the printer exposing :4408/webcam2/ (or
:8088/webcam/). If a firmware fork serves it elsewhere, only the nozzle shows
(one cam, correctly, not blank). Add candidate URLs in `discover_cameras` if LO
reports a missing chamber.
