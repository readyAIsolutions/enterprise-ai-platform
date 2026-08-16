#!/bin/bash
# find_workstations.sh — discover LO's Linux mini-ENI workstations on a /24.
# Portable: NO nmap dependency (nmap is usually absent on LO's box).
# Pings every host (ICMP) AND probes TCP/22 (so printers that block ping still
# show up as ssh22=1 — verify OS by banner, they are NOT workstations).
# Usage: bash find_workstations.sh [SUBNET=192.168.1]
set -u
SUB="${1:-192.168.1}"
OUT="/tmp/ws_alive.txt"
: > "$OUT"
echo "Sweeping $SUB.0/24 (ping + TCP/22) ..."
for i in $(seq 1 254); do
  ip="$SUB.$i"
  if ping -c1 -W1 "$ip" >/dev/null 2>&1; then ping_ok=1; else ping_ok=0; fi
  if timeout 1 bash -c "exec 3<>/dev/tcp/$ip/22" 2>/dev/null; then ssh_ok=1; else ssh_ok=0; fi
  if [ "$ping_ok" = 1 ] || [ "$ssh_ok" = 1 ]; then
    printf '%-16s ping=%s ssh22=%s\n' "$ip" "$ping_ok" "$ssh_ok" | tee -a "$OUT"
  fi
done
echo "--- ALIVE ---"; cat "$OUT"
echo "NOTE: SSH-open hosts (ssh22=1) are Linux boxes. The Creality printers also show"
echo "ssh22=1 but run OpenWrt/Creality OS (dropbear, no X) — confirm by SSH banner before"
echo "treating a host as a mini-ENI workstation. WS1 is this PC (192.168.1.64)."
