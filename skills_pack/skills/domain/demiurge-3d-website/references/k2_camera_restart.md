# K2 Plus Camera Daemon Restart Recipes

Both K2 Plus printers run two separate webcam Python servers. They crash independently
after idle or reboot. The agent sandbox cannot reach 192.168.x.x directly — all
restarts must be done via SSH from the backend host.

## Quick Health Check (from backend host)
```bash
cd /home/hunter/Desktop/Demiurge3D/backend && python3 -c "
import httpx, asyncio
async def p():
    async with httpx.AsyncClient(timeout=4) as c:
        for host,n in [('192.168.1.65','P1'),('192.168.1.66','P2')]:
            for port,cam in [(8081,'nozzle'),(8080,'chamber')]:
                try:
                    r = await c.get(f'http://{host}:{port}/snapshot')
                    ct = r.headers.get('content-type','')
                    print(f'{n} {cam} -> HTTP {r.status_code} {ct[:25]} {len(r.content)}b')
                except Exception as e:
                    print(f'{n} {cam} -> {type(e).__name__}')
asyncio.run(p())
"
```

## Nozzle Camera (port 8081)
- Script: `/usr/bin/webcam_server_nozzle.py`
- Device: `/dev/video2`
- Output: `/tmp/webcam_nozzle.jpg`
- Kills `cam_sub_app` on startup to free the device

### Restart nozzle cam on P1:
```bash
cat > /tmp/ap.sh <<'EOF'
#!/bin/bash
echo 'creality_2024'
EOF
chmod +x /tmp/ap.sh
SSH_ASKPASS=/tmp/ap.sh SSH_ASKPASS_REQUIRE=force setsid ssh \
  -o StrictHostKeyChecking=no -o PubkeyAuthentication=no \
  -o PreferredAuthentications=password -o NumberOfPasswordPrompts=1 \
  root@192.168.1.65 \
  'python3 /usr/bin/webcam_server_nozzle.py > /tmp/nozzle_webcam.log 2>&1 &'
```

### Restart nozzle cam on P2 (same, different IP):
```bash
# Same as above, replace 192.168.1.65 with 192.168.1.66
```

## Chamber Camera (port 8080)
- Script: `/usr/bin/webcam_server.py`
- Device: `/dev/video0`
- Output: `/tmp/webcam_chamber.jpg`
- Uses ffmpeg to capture frames — can stall after idle

### Restart chamber cam on P1:
```bash
cat > /tmp/ap.sh <<'EOF'
#!/bin/bash
echo 'creality_2024'
EOF
chmod +x /tmp/ap.sh
SSH_ASKPASS=/tmp/ap.sh SSH_ASKPASS_REQUIRE=force setsid ssh \
  -o StrictHostKeyChecking=no -o PubkeyAuthentication=no \
  -o PreferredAuthentications=password -o NumberOfPasswordPrompts=1 \
  root@192.168.1.65 \
  'kill $(pgrep -f webcam_server.py 2>/dev/null) 2>/dev/null; sleep 1; python3 /usr/bin/webcam_server.py > /tmp/chamber_webcam.log 2>&1 &'
```

## Pitfalls

1. **`disown` and `nohup` don't exist on BusyBox.** Just `&` background is enough
   when wrapping in `setsid ssh`.

2. **SSH session kills children by default.** The `setsid` wrapper outside SSH
   prevents the agent's shell from waiting, but the SSH process may still tear down
   the backgrounded Python on exit. Use `> /tmp/log 2>&1 &` and verify with port
   check after 6-8 seconds.

3. **Both daemons must be restarted after printer reboot.** The K2 firmware does
   not auto-start them.

4. **FAN OUT to both printers in parallel.** Use `terminal(background=true)` for
   each printer to restart simultaneously. Wait 8-10 seconds then verify with the
   health check above.

5. **The nginx proxy on 4408 is DEAD.** Do not use `:4408/webcam/` URLs —
   always use the direct ports 8080 (chamber) and 8081 (nozzle). The backend
   manager.py was updated to use these direct URLs (2026-07-23).

## Camera URL Map (CONFIRMED)
| Camera  | Port  | Snapshot URL                        | Stream URL                      |
|---------|-------|-------------------------------------|---------------------------------|
| Nozzle  | 8081  | `http://{host}:8081/snapshot`       | N/A (snapshot only)             |
| Chamber | 8080  | `http://{host}:8080/snapshot`       | `http://{host}:8080/stream`     |
