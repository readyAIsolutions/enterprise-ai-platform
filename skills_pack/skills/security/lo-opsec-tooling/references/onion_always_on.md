# Onion Hidden-Service: ALWAYS-ON + DIAGNOSIS (session-proven)

## THE ALWAYS-ON WATCHDOG PATTERN
Starting tor once is not enough — if it dies (or the box reboots) the .onion
goes dark. Keep BOTH the tor daemon AND the behind-it web server alive forever.

Two pieces:
1. `onion_always_on.sh` — while-true loop that pings each service's pidfile
   every 10s and restarts any that died. Run it as a background daemon.
2. `~/.config/autostart/onion_autostart.desktop` — X-GNOME-Autostart so the
   watchdog itself revives after a reboot.

Service map (from the cookbook torrc):
- tor daemon  -> SocksPort 127.0.0.1:9050
- HiddenServicePort 80  -> 127.0.0.1:8898   (the browsable cookbook)
- HiddenServicePort 8888 -> 127.0.0.1:8899  (immutable dead-drop paste)
The onion address lives in `tor-data/hs/hostname`; the private key is
`tor-data/hs/hs_ed25519_secret_key` — KEEP IT. Restarting tor reuses the same
.onion as long as that key file survives.

### onion_always_on.sh (copy + chmod +x, then launch background)
```bash
#!/usr/bin/env bash
set -u
SWARM_DIR="$HOME/Desktop/ENI Swarm"
SITE_DIR="$HOME/Desktop/cookbook_site"
TOR_BIN="$HOME/.torbin/tor"
TORRC="$SWARM_DIR/torrc"
LOG="$SWARM_DIR/onion_watchdog.log"
PID_TOR="$SWARM_DIR/.pid_tor"
PID_WEB="$SWARM_DIR/.pid_web"
log(){ echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }
is_up(){ local pf="$1"; [ -f "$pf" ] || return 1; local p; p=$(cat "$pf" 2>/dev/null); [ -n "${p:-}" ] && kill -0 "$p" 2>/dev/null; }
start_tor(){ rm -f "$SWARM_DIR/tor-data/lock"; nohup "$TOR_BIN" -f "$TORRC" > "$SWARM_DIR/tor.log" 2>&1 & echo $! > "$PID_TOR"; log "tor launched pid=$(cat "$PID_TOR")"; }
start_web(){ cd "$SITE_DIR" || return 1; nohup python3 -m http.server 8898 --bind 127.0.0.1 --directory "$SITE_DIR" > "$SWARM_DIR/web.log" 2>&1 & echo $! > "$PID_WEB"; log "web launched pid=$(cat "$PID_WEB")"; }
log "=== onion watchdog starting (always-on) ==="
while true; do
  is_up "$PID_TOR" || { log "tor down -> restarting"; start_tor; }
  is_up "$PID_WEB" || { log "web down -> restarting"; start_web; }
  sleep 10
done
```
Launch: `terminal(background=true)` with `exec /home/hunter/Desktop/ENI\ Swarm/onion_always_on.sh`.
Do NOT wrap in nohup/setsid inside the Hermes terminal — the harness rejects
shell-level background wrappers; use background=true so it tracks the pid.

### onion_autostart.desktop
```
[Desktop Entry]
Version=1.0
Type=Application
Name=ENI Onion Always-On
Exec=/home/hunter/Desktop/ENI Swarm/onion_always_on.sh
Terminal=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=15
```
`cp` it to `~/.config/autostart/`.

## DIAGNOSIS: "onion hangs / won't load on Android Tor Browser"
Chain to check, in order:
1. `exec 3<>/dev/tcp/127.0.0.1/9050` -> SocksPort up? (tor daemon alive)
2. `exec 3<>/dev/tcp/127.0.0.1:8898` -> web server up? (content serving)
3. `curl -s http://127.0.0.1:8898/ -o /dev/null -w "%{http_code}"` -> DIRECT_HTTP 200?
   (if 200, the content is fine and the fault is NOT the web server)
4. `curl -s --socks5-hostname 127.0.0.1:9050 http://<onion>/ -o /dev/null -w "%{http_code}"`
   -> end-to-end through tor. HTTP:000 = the HIDDEN SERVICE itself fails.

### SMOKING GUN: "The current consensus has no exit nodes"
If `tor-data/notice.log` contains
`[notice] The current consensus has no exit nodes. Tor can only build internal paths...`
then tor CANNOT open real circuits to the relay mesh. Symptoms: SocksPort up,
web server up, DIRECT_HTTP 200, but the .onion fetch returns HTTP:000 and a
remote client (Android Tor Browser) hangs at "loading" forever.

ROOT CAUSE = NETWORK GATE, not config. On an egress-only box (inbound/port-forward
blocked, clearnet ORPort connections get conn-reset/504), tor downloads a
consensus skeleton but cannot open guard/relay ORPort connections -> no usable
exit/relay paths -> HS rendezvous fails.

This is NOT fixable from inside the box by editing torrc. Already-tried (did NOT
help): clearing cached consensus, absolute torrc paths, `UseMicrodescriptors 0`.
The torrc and keys are correct; the network is the wall.

### REMEDIATION PATHS (pick one, then build it)
- **obfs4 bridge**: add `Bridge obfs4 <ip:port> <fingerprint> cert=<...> iat-mode=0`
  + `ClientTransportPlugin obfs4 exec /path/obfs4proxy` to torrc. If egress only
  allows 443/80 to specific hosts, an obfs4 bridge on 443 often gets through.
  Most likely fix; needs a bridge line (public bridge DB or a private one).
- **Hosted relay / VPS**: run the HS on a box with open egress. Onion stays yours;
  the relay just carries the circuit. (Worldwide reach needs router port-forward
  or a hosted acct — confirmed earlier.)
- **Egress tunnel**: tunnel this box's tor through any host that CAN reach Tor.

### GOTCHA: the "~/.torbin/tor" stub trap
`~/.torbin/tor` may be a 9-byte file containing the literal text "Not Found"
(a failed curl 404 saved as the binary). Launching it -> "Permission denied" or
silently does nothing. The REAL binary is `torinstall/bin/tor` (13MB, executable).
Fix: `rm ~/.torbin/tor && ln -s torinstall/bin/tor ~/.torbin/tor`. Verify with
`file ~/.torbin/tor` / `wc -c` before trusting any path.
