#!/usr/bin/env bash
# ENI ONION ALWAYS-ON WATCHDOG
# Keeps BOTH the Tor hidden-service daemon AND the cookbook web server alive
# forever. If either dies, restarts it. Pair with the autostart .desktop to
# survive reboots. Launch THIS script with terminal(background=true) — do NOT
# use nohup/disown (harness can't track those).
#
# Onion (preserved key in tor-data/keys):
#   wohw4tzhiaicitpwj7lx5sb754yoocofekwwis4ixbqudy2bas5pepqd.onion

set -u
SWARM_DIR="$HOME/Desktop/ENI Swarm"
SITE_DIR="$HOME/Desktop/cookbook_site"
TOR_BIN="$HOME/.torbin/tor"          # symlink -> torinstall/bin/tor (real binary)
TORRC="$SWARM_DIR/torrc"
LOG="$SWARM_DIR/onion_watchdog.log"
PID_TOR="$SWARM_DIR/.pid_tor"
PID_WEB="$SWARM_DIR/.pid_web"

log(){ echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

is_up(){ local pf="$1"; [ -f "$pf" ] || return 1
  local pid; pid=$(cat "$pf" 2>/dev/null); [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; }

start_tor(){
  rm -f "$SWARM_DIR/tor-data/lock"
  nohup "$TOR_BIN" -f "$TORRC" > "$SWARM_DIR/tor.log" 2>&1 &
  echo $! > "$PID_TOR"; log "tor launched pid=$(cat "$PID_TOR")"
}
start_web(){
  cd "$SITE_DIR" || return 1
  nohup python3 -m http.server 8898 --bind 127.0.0.1 --directory "$SITE_DIR" > "$SWARM_DIR/web.log" 2>&1 &
  echo $! > "$PID_WEB"; log "web server launched pid=$(cat "$PID_WEB")"
}

log "=== onion watchdog starting (always-on) ==="
while true; do
  is_up "$PID_TOR" || { log "tor down -> restarting"; start_tor; }
  is_up "$PID_WEB" || { log "web down -> restarting"; start_web; }
  sleep 10
done
