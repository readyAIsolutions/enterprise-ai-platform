#!/usr/bin/env bash
# WiFi drop monitor + auto-reconnect (run every minute via a systemd user timer).
# Captures the next drop with hard evidence (NetworkManager + kernel deauth context)
# instead of guessing, and brings the link back up if it's a redundant backup.
#
# Install:
#   chmod +x ~/.hermes/scripts/wifi_drop_monitor.sh
#   systemd user unit: ~/.config/systemd/user/wifi-monitor.service (Type=oneshot,
#     ExecStart=.../wifi_drop_monitor.sh) + wifi-monitor.timer (OnBootSec=1min,
#     OnUnitActiveSec=1min), then:
#   systemctl --user daemon-reload && systemctl --user enable --now wifi-monitor.timer
#
# Log: ~/.hermes/logs/wifi_drop_monitor.log ; last-state sentinel:
# ~/.hermes/logs/wifi_last_state
LOG="$HOME/.hermes/logs/wifi_drop_monitor.log"
mkdir -p "$(dirname "$LOG")"

IFACE="${WIFI_IFACE:-wlp4s0}"
SSID="${WIFI_SSID:-Wii Fii}"

state() { nmcli -t -f DEVICE,STATE dev | grep "^${IFACE}:" | cut -d: -f2; }
now() { date '+%F %T'; }

wifi_state="$(state)"
last_file="$HOME/.hermes/logs/wifi_last_state"
last=""
[ -f "$last_file" ] && last="$(cat "$last_file")"

if [ "$wifi_state" != "$last" ]; then
  if [ -n "$last" ]; then
    {
      echo ""
      echo "=== [$(now)] WiFi state change: '$last' -> '$wifi_state' ==="
      echo "--- nmcli device status ---"; nmcli device status 2>/dev/null
      echo "--- recent NetworkManager wifi lines ---"
      journalctl -u NetworkManager --since "-3 min" --no-pager 2>/dev/null \
        | grep -iE "$IFACE|deauth|disassoc|state change" | tail -15
      echo "--- recent kernel wifi lines ---"
      journalctl -k --since "-3 min" --no-pager 2>/dev/null \
        | grep -iE "$IFACE|mt7921|deauth|disassoc|firmware|enabling device" \
        | grep -viE "apparmor|audit" | tail -15
      echo "--- wpa_supplicant recent ---"
      journalctl -u wpa_supplicant --since "-3 min" --no-pager 2>/dev/null \
        | grep -iE "DISCONNECT|DEAUTH|disassoc|CTRL-EVENT" \
        | grep -viE "REGDOM|BEACON" | tail -15
    } >> "$LOG"
  fi
  echo "$wifi_state" > "$last_file"
  if [ "$wifi_state" = "disconnected" ] || [ "$wifi_state" = "unavailable" ] \
     || [ "$wifi_state" = "deactivating" ]; then
    echo "WIFI DROP detected: [$(now)] wifi state='$wifi_state' -> see $LOG"
  fi
fi

# If wifi is down, bring the redundant backup link back up (harmless if wired is primary).
if [ "$wifi_state" != "connected" ]; then
  echo "WIFI: currently '$wifi_state' — attempting reconnect."
  nmcli radio wifi on 2>/dev/null
  sleep 1
  nmcli connection up "$SSID" 2>/dev/null || true
fi

exit 0
