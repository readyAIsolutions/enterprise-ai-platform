#!/usr/bin/env bash
# wifi-diagnose.sh — One-shot WiFi diagnostic for linux-wifi-troubleshooting skill
# Run with: bash wifi-diagnose.sh

set -euo pipefail

IFACE="${1:-}"
if [[ -z "$IFACE" ]]; then
    IFACE=$(nmcli -t -f DEVICE,TYPE device status | awk -F: '$2=="wifi"{print $1; exit}')
fi

echo "=== WiFi Diagnostic for interface: $IFACE ==="
echo "Timestamp: $(date)"
echo

echo "--- Interface Status ---"
nmcli device status | grep -E "^$IFACE|^DEVICE"
echo

echo "--- Connection Details ---"
nmcli device show "$IFACE" 2>/dev/null | grep -E "STATE|CONNECTION|IP4|IP6|DNS|GATEWAY"
echo

echo "--- Signal & AP Info ---"
CONN=$(nmcli -t -f GENERAL.CONNECTION device show "$IFACE" 2>/dev/null | cut -d: -f2)
if [[ -n "$CONN" && "$CONN" != "--" ]]; then
    echo "Active connection: $CONN"
    nmcli connection show "$CONN" | grep -E "802-11-wireless\.(ssid|bssid|band|channel|powersave)"
    echo
fi

echo "--- Available APs (top 10) ---"
nmcli -f in-use,ssid,bssid,chan,freq,signal,rate,bars,security dev wifi list | head -12
echo

echo "--- Power Save Status ---"
iw dev "$IFACE" get power_save 2>/dev/null || echo "iw not available or interface down"
echo

echo "--- Driver & Firmware ---"
DRIVER=$(lspci -nnk | grep -A3 -i network | grep -E "Kernel driver|Kernel modules" | head -2)
echo "$DRIVER"
if echo "$DRIVER" | grep -q "mt7921e"; then
    echo "mt7921e params:"
    cat /sys/module/mt7921e/parameters/* 2>/dev/null | sed 's/^/  /'
fi
echo

# Check for ignored modprobe params
echo "--- Ignored Modprobe Params (dmesg) ---"
dmesg -T | grep "unknown parameter" | tail -10
echo

# Check ethernet if both might be affected
echo "--- Ethernet Interface Check ---"
ETH_IFACE=$(nmcli -t -f DEVICE,TYPE device status | awk -F: '$2=="ethernet"{print $1; exit}')
if [[ -n "$ETH_IFACE" ]]; then
    echo "Ethernet interface: $ETH_IFACE"
    ETH_DRIVER=$(lspci -nnk | grep -A3 -i ethernet | grep -E "Kernel driver|Kernel modules" | head -2)
    echo "$ETH_DRIVER"
    if echo "$ETH_DRIVER" | grep -q "r8169"; then
        ethtool -i "$ETH_IFACE" 2>/dev/null | grep -E "driver|firmware-version"
    fi
fi
echo

echo "--- Kernel Log (last 20 wifi-related lines) ---"
dmesg -T | grep -i -e "$IFACE" -e wlan -e "deauth" -e "disconnect" -e "authenticate" | tail -20
echo

echo "--- NetworkManager Log (last 20 relevant lines) ---"
journalctl -u NetworkManager -n 50 --no-pager 2>/dev/null | grep -i -e "$IFACE" -e disconnect -e deauth -e "link" -e wifi | tail -20
echo

echo "--- Interface Statistics ---"
ip -s link show "$IFACE"
echo

echo "--- Connectivity Test ---"
ping -c 3 -W 2 1.1.1.1 2>&1 | tail -5
echo
ping -c 3 -W 2 8.8.8.8 2>&1 | tail -5
echo

echo "=== Diagnostic Complete ==="