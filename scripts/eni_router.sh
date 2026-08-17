#!/usr/bin/env bash
# ENI rate-limit-safe puller router.
#
# Uses TOR as a LOCAL SOCKS proxy so only yt-dlp's traffic rotates its IP —
# the main system network is NEVER routed through it. This gives you IP
# rotation / rate-limit protection WITHOUT any chance of killing Ethernet or
# WiFi (the PIA system-wide approach that kept failing).
#
# TOR runs on 127.0.0.1:9050. We start it ourselves, detached, and yt-dlp is
# pointed at it via --proxy socks5://127.0.0.1:9050.
#
# Usage:
#   bash eni_router.sh start     # start TOR (detached) + verify 127.0.0.1:9050
#   bash eni_router.sh stop      # stop TOR
#   bash eni_router.sh test      # curl through TOR (exit IP will differ)

TORRC=/tmp/eni_torrc
TOR_DATA=/tmp/eni_tor_data
HAS_TOR=0

setup_torrc() {
  mkdir -p "$TOR_DATA"
  cat > "$TORRC" <<EOF
SocksPort 127.0.0.1:9050
DataDirectory $TOR_DATA
# stay up; don't try systemd/polipo
RunAsDaemon 0
Log notice file /tmp/eni_tor.log
EOF
}

find_tor() {
  if command -v tor >/dev/null 2>&1; then echo "tor"; return 0; fi
  for p in /usr/bin/tor /usr/sbin/tor /usr/local/bin/tor; do
    [ -x "$p" ] && { echo "$p"; return 0; }
  done
  echo ""; return 1
}

start() {
  setup_torrc
  TOR_BIN=$(find_tor)
  if [ -z "$TOR_BIN" ]; then echo "TOR not installed"; exit 1; fi
  # start detached with our torrc
  nohup "$TOR_BIN" -f "$TORRC" >/tmp/eni_tor_stdout.log 2>&1 &
  echo "TOR started (pid $!) on 127.0.0.1:9050"
  # wait for socks port
  for i in $(seq 1 20); do
    if (exec 3<>/dev/tcp/127.0.0.1/9050) 2>/dev/null; then exec 3>&- 3<&-; echo "  socks ready"; break; fi
    sleep 1
  done
}

stop() {
  # kill only tor processes we started (by torrc path)
  pkill -f "tor.*eni_torrc" 2>/dev/null
  echo "TOR stopped"
}

test_socks() {
  # show the exit IP you'd get THROUGH tor — proves rotation works per-process
  echo -n "direct ip : "; curl -s --max-time 8 https://ifconfig.me 2>&1 | head -1
  echo -n "via tor   : "; curl -s --max-time 15 --socks5-hostname 127.0.0.1:9050 https://ifconfig.me 2>&1 | head -1
}

case "${1:-}" in
  start) start ;;
  stop)  stop ;;
  test)  test_socks ;;
  *) echo "usage: $0 start|stop|test";;
esac
