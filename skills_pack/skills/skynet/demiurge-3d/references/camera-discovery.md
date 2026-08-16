# Creality K2 Plus camera discovery

The K2 Plus has ONE camera (the AI nozzle cam). Moonraker/Creality proxy the
SAME image at several endpoints, so a naive probe shows it 2-3x (e.g. a
mislabeled "Chamber Cam"). Real endpoints observed on LO's fleet:

- `http://<ip>:8081/snapshot`  (actual nozzle-cam server; may be powered OFF
  by default — `start_nozzle_camera` refuses during a print)
- `http://<ip>:4408/webcam/?action=stream`  (MJPEG proxy of the same nozzle cam)
- `http://<ip>:4408/webcam2/?action=stream` (only on multi-cam rigs; on a
  single-cam K2 this resolves to the SAME image as webcam/)

RULE: `discover_cameras()` MUST dedupe by RESOLVED snapshot URL, not by
(name, kind). A plain HTTP GET on the snapshot URL is enough to confirm liveness
— you do NOT need an MJPEG stream for the camera to be "found".

```python
seen_urls = set()
for name, kind, stream, snap in candidates:
    key = snap.rstrip("/").lower()
    if key in seen_urls: continue          # same image already added
    try: r = await client.get(snap, timeout=4.0)
    except Exception: continue
    if r.status_code == 200 and r.content_type.startswith("image"):
        seen_urls.add(key)
        cams.append(CameraInfo(name=name, kind=kind, stream_url=stream, snapshot_url=snap))
```

Result: K2 shows exactly ONE "Nozzle Cam". The `:4408/webcam2/` "Chamber" is
only added if its resolved URL differs from the nozzle's (i.e. a real second cam).

Frontend note: `CameraStream.tsx` renders an `<img src=snapshot_url>` and polls
with a `?t=` cache-buster so a single-image snapshot endpoint shows a live feed
without needing MJPEG.
