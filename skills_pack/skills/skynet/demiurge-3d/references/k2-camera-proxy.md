# K2 Plus Camera Proxy Pattern

When the frontend cannot reach printer IPs directly (sandbox), add a backend proxy endpoint:

## Backend Route (server.py)
```python
@app.get("/api/printer/{printer_id}/camera/{cam_kind}")
async def api_printer_camera_proxy(printer_id: int, cam_kind: str):
    m = get_hub().get(printer_id)
    if m is None:
        raise HTTPException(404, "Printer not found")
    if not m.cameras:
        try:
            await asyncio.wait_for(m.discover_cameras(), timeout=8.0)
        except Exception:
            pass
    cam = next((c for c in m.cameras if c.kind == cam_kind), None)
    if cam is None:
        raise HTTPException(404, f"Camera {cam_kind} not found")
    url = cam.snapshot_url  # Prefer discovered URL
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            return Response(
                content=r.content,
                media_type=r.headers.get("content-type", "image/jpeg"),
                headers={"Cache-Control": "no-cache", "Access-Control-Allow-Origin": "*"},
            )
    except Exception as e:
        raise HTTPException(502, f"Camera fetch failed: {str(e)[:100]}")
```

## Frontend CameraStream Props
Add these props to support the proxy pattern:

```tsx
interface CameraStreamProps {
  kind?: string;        // 'nozzle' | 'chamber'
  printerId?: number;   // Required if using proxy
  src?: string;         // Legacy direct URL (fallback)
  ...
}

// Build proxy URL
const proxyUrl = kind && printerId
  ? `/api/printer/${printerId}/camera/${kind}?t=${Date.now()}`
  : null;
const resolved = proxyUrl ?? src ?? ...;
```

## K2 Camera Ports (CONFIRMED)
- NOZZLE → port 8081 `/snapshot` (single JPEG, always registered)
- CHAMBER → port 4408 `/webcam/?action=snapshot` (probed, may be dead)

## Troubleshooting
- 502 from proxy in sandbox is EXPECTED — sandbox has no 192.168.x.x egress
- On host, proxy returns actual image bytes
- Chamber cam may not respond — the `_cam_alive` probe will skip it silently
- Cache-busting required for K2 snapshots (they don't push MJPEG)