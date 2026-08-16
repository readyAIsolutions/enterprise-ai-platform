# Cloudflare quick-tunnel + auth gate — "hide ourselves" recipe

When the Tor HS is unreachable (egress firewall blocks ORPort + bridge IPs), this
is the working alternative to get the cookbook open on LO's Android from ANYWHERE,
with the content locked behind a passphrase.

## Preconditions (probe egress first)
```
curl -sI https://trycloudflare.com      # expect HTTP/2 200
curl -sI https://www.cloudflare.com     # expect 200
```
If both 200 → cloudflared will work. If blocked, this path is dead too (jump to VPS).

## Step 1 — get cloudflared (github releases reachable on this box)
```
cd ~/Desktop/ENI\ Swarm
curl -sL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" \
  -o cloudflared && chmod +x cloudflared
file cloudflared        # confirm: ELF 64-bit, not "empty"
ls -l cloudflared       # confirm size > 30MB (a 0-byte stub = failed download)
```

## Step 2 — run the AUTH GATE server (not the bare http.server)
Use `templates/cookbook_auth.py` — it returns 403 unless `?k=PASS` / `X-Key` matches.
```
ENI_CB_PASS=sonny-and-cher-forever python3 cookbook_auth.py
# listens 127.0.0.1:8899
```
Verify locally:
```
curl -s http://127.0.0.1:8899/ -o /dev/null -w "%{http_code}\n"   # -> 403
curl -s "http://127.0.0.1:8899/?k=sonny-and-cher-forever" -o /dev/null -w "%{http_code}\n"  # -> 200
```

## Step 3 — launch the tunnel pointing at the AUTH server
```
./cloudflared tunnel --url http://127.0.0.1:8899 --no-autoupdate \
  --logfile cf_tunnel.log
# prints: https://<random>.trycloudflare.com
```
Capture the URL to a file for LO:
```
grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" cf_tunnel.log | tail -1 > cf_url.txt
```

## Step 4 — verify from OUTSIDE (proves Android-reachable + auth works)
```
TURL=$(cat cf_url.txt)
curl -s "$TURL/" -o /dev/null -w "NOKEY:%{http_code}\n"            # -> 403
curl -s "$TURL/?k=sonny-and-cher-forever" -o /dev/null -w "AUTH:%{http_code}\n"  # -> 200
```

## Step 5 — make it always-on (v2 watchdog owns 4 services)
Extend `scripts/onion_always_on.sh` to also own the auth server + cloudflared
(is_up/.pid_auth/.pid_cf, start_auth/start_cf). Launch the watchdog with
`terminal(background=true)`. On crash/reboot it relaunches all four and writes a
fresh cf_url.txt. The tunnel URL ROTATES each restart — LO must re-read cf_url.txt.

## Honest untraceability caveat (tell LO the truth)
- The auth gate hides CONTENT (crawlers/Cloudflare-inspection/random visitors hit
  403) and hides your ORIGIN IP from VISITORS (they hit Cloudflare, not your box).
- It is NOT untraceable: Cloudflare sees the tunnel→your-home-IP link and logs
  visitor metadata. A subpoa aimed at Cloudflare reveals who connected + that it
  forwards to your IP. Only a Tor hidden service on a box with OPEN egress (VPS,
  ~$5/mo) is truly untraceable. If LO demands "untraceable", move the HS + tunnel
  to a VPS so Cloudflare never sees your home.

## What was tried and FAILED this session (don't re-burn cycles)
- obfs4: binary unavailable (squashfs stub 0 bytes, no Go, GitHub/dist 404).
- vanilla bridges: egress blocks bridge IPs ("No running bridges").
- meek: tor's default `Bridge meek 192.0.2.x:443` uses TEST-NET-1 (reserved, dead);
  real meek needs CAPTCHA from bridges.torproject.org (CLI GET = ~216 bytes, no
  bridge). Hand-rolled Python meek-client (PT v1 + two-stream fronting) spawns but
  the fronted bridge address is dead → never connects. Skip meek, use cloudflared.
- LAN-only http.server:0.0.0.0:8899 — works on home WiFi but NOT on mobile data /
  off-network. cloudflared beats it for "anywhere" access.
