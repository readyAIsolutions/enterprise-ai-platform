# Cloudflare Tunnel ops — keep the site reachable (acpeso.shop + any CF-tunnel site)

## Symptom (2026-08-05): site down with a Cloudflare tunnel error
- `acpeso.shop` unreachable (522/tunnel error) but the local app was FINE.
- Root cause: the tunnel was launched ad-hoc with `cloudflared tunnel run acpeso` and had
  NO systemd service, so nothing restarted it after a reboot/crash. The app
  (`server.py` on :8533 via `acpeso.service`) was still up; only the tunnel had died.

## Diagnostic order (fast)
1. Is the local app up? `ss -ltnp | grep <port>` (here :8533) → the app is usually fine.
2. Is cloudflared running at all? `pgrep -a cloudflared` → if EMPTY, the tunnel is down;
   that's your outage, not the app.
3. Is it managed by systemd? `systemctl --user list-unit-files | grep -i tunnel|cloud`
   (and check `/etc/systemd/system` + `~/.config/autostart`). If nothing manages it, it
   WILL silently die again.

## Permanent fix — make the tunnel a managed systemd user service
`~/.config/systemd/user/<name>-tunnel.service`:
```
[Unit]
Description=<site> Cloudflare Tunnel (-> localhost:<port>)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/home/<user>/bin/cloudflared tunnel --config /home/<user>/.cloudflared/config.yml run <TUNNEL_ID>
Restart=on-failure
RestartSec=3
TimeoutStopSec=30

[Install]
WantedBy=default.target
```
Enable + start + ensure boot persistence:
```bash
systemctl --user daemon-reload
loginctl enable-linger <user>        # user services survive logout/reboot
systemctl --user enable <name>-tunnel.service
systemctl --user start  <name>-tunnel.service
```
Verify connect + serve:
- `systemctl --user status <name>-tunnel.service` → active; log shows
  `Registered tunnel connection ... location=seaXX protocol=quic` (one per edge conn).
- `curl -s -o /dev/null -w "%{http_code}" https://<hostname>/` → 200 (also test `www.`).

## Ops commands
- Restart: `systemctl --user restart <name>-tunnel.service`
- Logs: `journalctl --user -u <name>-tunnel`
- If DNS route lost later (zone/NS changed): `cloudflared tunnel route dns <tunnel> <hostname>`

## Key config facts (acpeso)
- cloudflared binary: `~/bin/cloudflared` (NOT on PATH).
- config: `~/.cloudflared/config.yml` — `tunnel: <TID>`, `credentials-file: ~/.cloudflared/<TID>.json`,
  ingress maps `acpeso.shop` + `www.acpeso.shop` → `http://localhost:8533`, else 404.
- Service created: `acpeso-tunnel.service` (enabled + linger). Setup script:
  `~/Desktop/ac pe$0/setup_acpeso.sh` (login → create tunnel → write config → route DNS).
