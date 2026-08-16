# Camera Proxy Implementation (2026-07-22)

## Problem
Frontend CameraStream `<img>` tags cannot reach 192.168.x.x printer IPs directly
when the backend runs in a sandbox environment that blocks that traffic.

## Solution
Add a proxy endpoint that fetches camera snapshots on behalf of the frontend.

## Backend Endpoint (`server.py`)
```python
@app.get("/api/printer/{printer_id}/camera/{cam_kind}")
async def api_printer_camera_proxy(printer_id: int, cam_kind: str):
    """Proxy camera snapshots through the backend."""
    m = get_hub().get(printer_id)
    if m is None:
        raise HTTPException(404, "Printer not found")
    if not m.cameras:
        await asyncio.wait_for(m.discover_cameras(), timeout=8.0)

    cam = next((c for c in m.cameras if c.kind == cam_kind), None)
    if cam is None:
        raise HTTPException(404, f"Camera {cam_kind} not found")

    url = cam.snapshot_url or f"http://{m.host}:8081/snapshot"
    async with httpx.AsyncClient(timeout=6.0) as client:
        r = await client.get(url)
        return Response(
            content=r.content,
            media_type=r.headers.get("content-type", "image/jpeg"),
            headers={"Cache-Control": "no-cache", "Access-Control-Allow-Origin": "*"},
        )
```

## Frontend Changes

### CameraStream.tsx
- Add `kind?: string` and `printerId?: number` props
- Build proxy URL: `/api/printer/${printerId}/camera/${kind}?t=${Date.now()}`

### PrinterPanel.tsx  
- Change: `<CameraStream printerId={printer.id} kind={cam.kind} label={camLabel(cam)} />`

## Camera URLs (K2 Plus)
- Nozzle: `http://{host}:8081/snapshot`
- Chamber: `http://{host}:4408/webcam/?action=snapshot` (usually dead on LO's fleet)

## Verification
Check printers: `curl http://localhost:8093/api/printers`
Check cameras: `curl http://localhost:8093/api/printer/5/cameras`
Check proxy: `curl http://localhost:8093/api/printer/5/camera/nozzle`