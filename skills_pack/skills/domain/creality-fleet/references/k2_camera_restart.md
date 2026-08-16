# K2 Plus Camera Daemon Restart Recipes

## Nozzle Camera (port 8081)
Script: `/usr/bin/webcam_server_nozzle.py`
Device: `/dev/video2`

Restart P1:
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

Restart P2: replace 192.168.1.65 with 192.168.1.66

## Chamber Camera (port 8080)
Script: `/usr/bin/webcam_server.py`
Device: `/dev/video0`

Restart P1:
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

Restart P2: replace IP.

## Quick Health Check
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

## Pitfalls
- `disown` and `nohup` don't exist on BusyBox ash. Use `&` directly.
- Both daemons must be restarted after printer reboot — firmware doesn't auto-start them.
- Fan out to both printers in parallel with `terminal(background=true)`.
- The nginx proxy on :4408 is DEAD for camera — always use direct ports.
- URL map updated 2026-07-23: chamber 8080, nozzle 8081.
