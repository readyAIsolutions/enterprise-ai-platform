#!/bin/bash
# verify_swarm_ready.sh — Post-reboot ENI Swarm readiness check
# Run after every reboot before starting the swarm
# Usage: ~/Desktop/Projects/ENI_Swarm_NEW/verify_swarm_ready.sh

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS=0
FAIL=0

check() {
    local desc="$1"
    local cmd="$2"
    if eval "$cmd" >/dev/null 2>&1; then
        echo -e "${GREEN}✅ PASS${NC}  $desc"
        PASS=$((PASS+1))
    else
        echo -e "${RED}❌ FAIL${NC}  $desc"
        FAIL=$((FAIL+1))
    fi
    return 0
}

check_output() {
    local desc="$1"
    local cmd="$2"
    local pattern="$3"
    if eval "$cmd" 2>/dev/null | grep -qE "$pattern"; then
        echo -e "${GREEN}✅ PASS${NC}  $desc"
        PASS=$((PASS+1))
    else
        echo -e "${RED}❌ FAIL${NC}  $desc"
        FAIL=$((FAIL+1))
    fi
    return 0
}

echo "═══════════════════════════════════════════════════════════"
echo "      ENI SWARM READINESS VERIFICATION — MT7921e"
echo "═══════════════════════════════════════════════════════════"
echo

echo "--- KERNEL BOOT PARAMETERS ---"
check_output "pcie_aspm=off in cmdline" "cat /proc/cmdline" "pcie_aspm=off"
check_output "pcie_port_pm=off in cmdline" "cat /proc/cmdline" "pcie_port_pm=off"

echo
echo "--- MT7921E MODULE PARAMETERS ---"
check "disable_aspm=Y active" "cat /sys/module/mt7921e/parameters/disable_aspm | grep -q Y"

echo
echo "--- BLUETOOTH COEXISTENCE ---"
check "Bluetooth service disabled" "systemctl is-enabled bluetooth 2>/dev/null | grep -q disabled || test \${PIPESTATUS[0]} -eq 1"
check "Bluetooth rfkill blocked" "rfkill list | grep -q 'Soft blocked: yes'"

echo
echo "--- WIFI CONNECTION ---"
check "WiFi interface connected (STATE=100)" "nmcli device show wlp4s0 2>/dev/null | grep -q 'STATE:.*100 (connected)'"
check_output "Locked to 5 GHz band (freq > 5000 MHz)" "nmcli -f in-use,ssid,bssid,chan,freq,signal,rate dev wifi list 2>/dev/null | grep -E '^\*|^IN-USE'" "5[0-9]{3} MHz"
check "IPv6 disabled on connection" "nmcli connection show 'Wii Fii' 2>/dev/null | grep -q 'ipv6.method:.*disabled'"

echo
echo "--- FREE MODEL ROUTER ---"
check "free-router service active" "systemctl --user is-active free-router 2>/dev/null | grep -q active"
check "free-router HTTP health endpoint" "curl -sf http://localhost:8920/health >/dev/null"
check "free-router has free models" "curl -sf http://localhost:8920/v1/models | jq -e '.data[] | select(.free==true)' >/dev/null"

echo
echo "--- SWARM CONFIGURATION ---"
CONFIG="/home/hunter/Desktop/Projects/ENI_Swarm_NEW/config/swarm_config.json"
check "Config file exists" "test -f '$CONFIG'"
if [ -f "$CONFIG" ]; then
    check_output "max_concurrent_children = 4" "python3 -c \"import json; d=json.load(open('$CONFIG')); print(d['concurrency']['max_concurrent_children'])\"" "^4$"
    check_output "launch_delay_seconds = 15" "python3 -c \"import json; d=json.load(open('$CONFIG')); print(d['concurrency']['launch_delay_seconds'])\"" "^15$"
    check_output "max_hermes_processes = 4" "python3 -c \"import json; d=json.load(open('$CONFIG')); print(d['concurrency']['resource_gate']['max_hermes_processes'])\"" "^4$"
    check_output "fleet stage_size = 4" "python3 -c \"import json; d=json.load(open('$CONFIG')); print(d['fleet_optimization']['stage_size'])\"" "^4$"
    check_output "fleet stage_delay_seconds = 15" "python3 -c \"import json; d=json.load(open('$CONFIG')); print(d['fleet_optimization']['stage_delay_seconds'])\"" "^15$"
    check_output "max_api_calls_per_minute = 60" "python3 -c \"import json; d=json.load(open('$CONFIG')); print(d['rate_limiting']['max_api_calls_per_minute'])\"" "^60$"
    check "Config JSON valid" "python3 -m json.tool '$CONFIG' >/dev/null"
fi

echo
echo "--- HERMES CLI ---"
check "hermes command available" "command -v hermes >/dev/null"
check "hermes config readable" "hermes config show >/dev/null 2>&1"

echo
echo "═══════════════════════════════════════════════════════════"
printf "   RESULTS: ${GREEN}%d PASS${NC} / ${RED}%d FAIL${NC}\n" "$PASS" "$FAIL"
echo "═══════════════════════════════════════════════════════════"

if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}✅ ALL CHECKS PASSED — SWARM READY TO START${NC}"
    exit 0
else
    echo -e "${RED}❌ $FAIL CHECK(S) FAILED — FIX BEFORE STARTING SWARM${NC}"
    exit 1
fi