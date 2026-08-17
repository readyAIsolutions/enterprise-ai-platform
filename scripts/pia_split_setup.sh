#!/usr/bin/env bash
# Split-tunnel for the puller: route ONLY the piafleet user's traffic through
# PIA's tunnel; everything else (incl. the rest of the machine) stays on the
# normal Ethernet default. This gives PIA rate-limit protection to the puller
# WITHOUT ever taking down the physical link.
#
# Usage: bash pia_split_setup.sh            # route piafleet via PIA tunnel
#        bash pia_split_setup.sh --off      # undo (back to normal routing)

PIA_TABLE=100
PIA_UID=997            # piafleet
RULE="uidrange $PIA_UID-$PIA_UID lookup $PIA_TABLE"

if [ "${1:-}" = "--off" ]; then
  ip rule del "$RULE" 2>/dev/null
  ip route flush table $PIA_TABLE 2>/dev/null
  ip route del default table $PIA_TABLE 2>/dev/null
  echo "split-tunnel OFF"
  exit 0
fi

# find PIA tunnel + its gateway
TUN=$(ip -o link show 2>/dev/null | awk -F': ' '{print $2}' | grep -E '^(tun|wg)' | head -1)
if [ -z "$TUN" ]; then
  echo "no PIA tunnel up yet (connect PIA first)"; exit 1
fi
GW=$(ip -o -4 addr show dev "$TUN" 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -1)
echo "PIA tunnel=$TUN gw=$GW"

# table: default via tunnel (and the tunnel subnet itself)
ip route flush table $PIA_TABLE 2>/dev/null
ip route add default dev "$TUN" table $PIA_TABLE 2>/dev/null || ip route add default via "$GW" dev "$TUN" table $PIA_TABLE 2>/dev/null
# route the piafleet uid through it
ip rule add "$RULE" 2>/dev/null || ip rule replace "$RULE" 2>/dev/null

echo "split-tunnel ON: uid $PIA_UID -> PIA ($TUN); rest -> main route"
ip rule show | grep -i "$PIA_TABLE"
