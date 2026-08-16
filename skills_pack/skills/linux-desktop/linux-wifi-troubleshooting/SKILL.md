---
name: linux-wifi-troubleshooting
description: Diagnose and fix WiFi connection drops, instability, and performance issues on Linux. Covers NetworkManager configuration, kernel driver parameters, power management, band steering/roaming problems, and hardware-specific fixes (Intel, MediaTek, Realtek, Broadcom). Use when the user reports "wifi keeps disconnecting", "wifi drops", "slow wifi", "wifi unstable", or similar connectivity issues.
---

# Linux WiFi Troubleshooting

## Quick Diagnosis Checklist

Run these first to understand the state:

```bash
# Interface status and connection
nmcli device status
nmcli device show wlan0  # or actual interface name

# Signal quality and available APs
nmcli -f in-use,ssid,bssid,chan,freq,signal,rate,bars dev wifi list

# Kernel driver and firmware
lspci -nnk | grep -A3 -i network
dmesg -T | grep -i -e wlan -e wifi -e <interface> | tail -30

# Power save status
iw dev <interface> get power_save
cat /sys/module/<driver>/parameters/*

# NetworkManager logs
journalctl -u NetworkManager -n 50 --no-pager | grep -i -e disconnect -e deauth -e "link"
```

## Common Root Causes & Fixes



### 1. Band Steering / Same SSID on 2.4/5 GHz
**Symptom:** Random disconnects, roaming between bands, "authenticate/associate" cycles in dmesg
**Fix:** Lock connection to specific BSSID and band

```bash
# Find the 5 GHz BSSID
nmcli -f ssid,bssid,chan,freq,signal,security dev wifi list | grep -i <SSID>

# Lock connection
nmcli connection modify "<SSID>" \
  802-11-wireless.bssid <5GHZ_BSSID> \
  802-11-wireless.band a \
  802-11-wireless.channel <5GHZ_CHANNEL>
nmcli connection up "<SSID>"
```

**Better fix:** Configure router with separate SSIDs (e.g. "Home-5G", "Home-2.4G")

### 2. WiFi Power Save Enabled
**Symptom:** Latency spikes, drops after idle, poor throughput
**Check:**
```bash
iw dev <interface> get power_save  # should be "off"
nmcli connection show "<SSID>" | grep powersave  # should be 2 (disable)
```

**Fix - NetworkManager (persistent):**
```bash
# Per-connection
nmcli connection modify "<SSID>" 802-11-wireless.powersave 2

# Global (create /etc/NetworkManager/conf.d/wifi-powersave.conf)
# Note: use sudo tee for heredoc to avoid permission issues
sudo tee /etc/NetworkManager/conf.d/wifi-powersave.conf > /dev/null <<'EOF'
[connection]
wifi.powersave = 2
EOF
```

### 3. PCIe ASPM (Active State Power Management)
**Symptom:** Drops under load, firmware crashes, "enabling device" cycles in dmesg
**Check:**
```bash
cat /sys/module/<driver>/parameters/disable_aspm  # should be Y
cat /sys/module/pcie_aspm/parameters/policy  # should be "performance" (not "default" or "powersave")
```

**Fix - Kernel parameter (persistent):**

**Per-driver (when only one interface affected):**
```bash
# Add to /etc/default/grub GRUB_CMDLINE_LINUX_DEFAULT:
# <driver>.disable_aspm=Y
# e.g. mt7921e.disable_aspm=Y iwlwifi.disable_aspm=Y
sudo update-grub
```

**Also create /etc/modprobe.d/<driver>.conf for persistence across kernel updates:**
```bash
echo "options mt7921e disable_aspm=1" | sudo tee /etc/modprobe.d/mt7921e.conf
```
(Values `Y`, `1`, or `true` are equivalent for boolean kernel parameters.)

**System-wide (when BOTH WiFi AND ethernet drop simultaneously):**
```bash
# Add to /etc/default/grub GRUB_CMDLINE_LINUX_DEFAULT:
pcie_aspm=off
sudo update-grub
```

**Runtime verification (doesn't persist reboot):**
```bash
echo performance | sudo tee /sys/module/pcie_aspm/parameters/policy
```

### 4. Driver/Firmware Issues
**MediaTek MT7921/MT7922 (mt7921e):**
- Ensure `linux-firmware` is current
- `disable_aspm=Y` often required
- Check `dmesg` for "WM Firmware Version" — newer is better

**Intel (iwlwifi):**
- `disable_aspm=Y`, `bt_coex_active=0` if Bluetooth coexistence issues
- `11n_disable=8` for 5 GHz stability (disables 802.11n aggregation)

**Realtek (rtw88/rtw89):**
- Often needs `fwlps=0 ips=0` module params

### 5. NetworkManager Config Errors
**Symptom:** "Failed to read configuration" in journalctl
**Check:**
```bash
ls -la /etc/NetworkManager/conf.d/
# Look for malformed .conf files (e.g. stray "EOF" lines)
```

**Fix:** Remove or fix bad config files

### 6. "Everything is already fixed but wifi still drops" — is wifi even carrying traffic?

When a desktop has BOTH a wired ethernet (primary) and wifi, all real traffic (swarm,
servers, tunnels, everything) rides the wire. A wifi "drop" on that box is usually an
idle-backup radio drop and is HARMLESS — do NOT chase it as a swarm/load problem.

Check which interface actually carries outbound traffic BEFORE attributing the drop:

```bash
# Which interface does real internet egress use?
ip route get 1.1.1.1                 # → "dev enp5s0" (wire) vs "dev wlp4s0" (wifi)

# Does wifi move ANY bytes? Compare counters over 3s.
cat /sys/class/net/wlp4s0/statistics/{rx_bytes,tx_bytes}; sleep 3; cat /sys/class/net/wlp4s0/statistics/{rx_bytes,tx_bytes}
cat /sys/class/net/enp5s0/statistics/{rx_bytes,tx_bytes}
```
If `ip route get` shows the wired NIC and the wifi counters are frozen while ethernet
streams → wifi is idle backup. Its intermittent drop doesn't affect the machine and is
not load-related (it's the known MT7921e/radio idle behavior, or the AP reaping an idle
client). All the client-side hardening (band lock, disable_aspm, IPv6 off, power save off)
may ALREADY be in place — verify `/proc/cmdline`, `/etc/modprobe.d/*.conf`, and `nmcli
connection show "<SSID>" | grep -Ei 'bssid|band|channel|ipv6.method'` rather than assuming
they're missing.

Action: keep the wired link primary (lower metric — it is by default), and set up a
lightweight drop monitor that logs the state change with its NetworkManager/kernel/wpa
context + auto-reconnects, so the NEXT real drop is captured with a reason code instead of
guessing. If the user specifically needs wifi as a standalone link, the remaining lever is
signal (2.4GHz is stronger/stabler than a -61 dBm 5GHz at long range) — speed doesn't
matter for a backup link.

## Verification Steps

After any fix, verify:

```bash
# 1. Connection stable
nmcli device show <interface> | grep STATE  # 100 (connected)

# 2. No RX/TX errors
ip -s link show <interface>

# 3. Internet reachable
ping -c 3 1.1.1.1
ping -c 3 8.8.8.8

# 4. No deauth/disconnect in kernel log (watch for 5+ min)
dmesg -T -w | grep -i -e <interface> -e deauth -e disconnect
```

## Hardware-Specific Reference

| Hardware | Driver | Common Params | Notes |
|----------|--------|---------------|-------|
| MediaTek MT7921/MT7922 | mt7921e | `disable_aspm=Y` | Filogic 330/830, common in laptops 2022+ |
| Intel AX200/AX210 | iwlwifi | `disable_aspm=Y bt_coex_active=0` | `11n_disable=8` for 5GHz |
| Realtek 8852A/8852B | rtw89 | `fwlps=0 ips=0` | Check `modinfo rtw89_core` |
| Broadcom BCM43xx | brcmfmac | N/A | Needs proprietary firmware |

## Pitfalls

- **Check which interface ACTUALLY carries outbound traffic before blaming wifi load.**
  On a desktop with a wired link, ethernet is usually the primary egress and wifi is an
  idle backup carrying ZERO traffic. Verify with `ip route get 1.1.1.1` (which `dev` does
  it pick? higher metric = backup) and compare live counters:
  `cat /sys/class/net/{enp5s0,wlp4s0}/statistics/{rx,tx}_bytes` twice ~3s apart. If wifi's
  counters are static while eth streams, the swarm-concurrency saturation cause does NOT
  apply — a drop there is just the MT7921e radio dropping an idle link (harmless because
  the wire handles everything), NOT load. Don't drop swarm concurrency in that case.
- **Capture the next drop with evidence, don't guess.** An idle-link drop is transient and
  self-recovers, leaving no trace. Install `scripts/wifi-drop-monitor.sh` as a 1-min
  systemd user timer: it logs the NM + kernel + wpa_supplicant deauth context (with reason
  code) into `~/.hermes/logs/wifi_drop_monitor.log` and auto-reconnects the backup link.
- **Don't assume power save is off** — check both `iw` and NetworkManager
- **Band steering is invisible** — same SSID on both bands looks like one network
- **`disable_aspm=Y` must be in kernel cmdline** — module param may not exist
- **NetworkManager `.conf` syntax errors are silent** — only visible in journalctl
- **Router-side issues masquerade as client issues** — check AP logs if possible
- **IPv6 can cause apparent drops** — test with `ping -4` and `ping -6` separately
- **A drop on a wired-primary box is usually harmless** — if `ip route get` shows ethernet and wifi counters are frozen, wifi is idle backup; its intermittent drop is the radio, NOT swarm/load. Don't rip out working config chasing the swarm theory. Confirm with `ip route get 1.1.1.1` + per-interface byte counters first.
- **MediaTek mt7921e: IPv6 breaks IPv4 connectivity** — interface shows connected, has IPv4 address/gateway/DNS, but `ping 1.1.1.1` fails. Fix: `nmcli connection modify "<SSID>" ipv6.method disabled ipv6.ignore-auto-routes yes ipv6.ignore-auto-dns yes`
- **Simultaneous WiFi + ethernet drops = system-wide PCIe ASPM** — not a per-driver issue. Fix with `pcie_aspm=off` kernel parameter, not just per-driver `disable_aspm=Y`
- **Invalid modprobe params are silently ignored** — check `dmesg | grep "unknown parameter"` (e.g. `r8169 eee_enable=0` doesn't exist; `r8169` has no `disable_aspm` or `aspm` params on kernel 7.x)
- **Creating NM config files needs sudo tee** — heredoc redirection (`cat > /etc/...`) fails with permission denied even with sudo; use `sudo tee /path/file <<'EOF'` instead
- **Ubuntu's linux-firmware package lags upstream** — kernel.org git often has newer MediaTek/Realtek firmware. When issues persist after driver params, fetch latest from `https://git.kernel.org/pub/scm/linux/kernel/git/firmware/linux-firmware.git`
- **Bluetooth firmware on same chip also matters** — MT7961 shares BT/WiFi firmware; update both `WIFI_*` and `BT_RAM_CODE_*` files from upstream
- **Ethernet drops alongside WiFi = check ethernet firmware too** — RTL8168h needs `rtl8168h-2.fw` from upstream; r8169 driver loads it automatically
- **AI swarm / high-concurrency workloads saturate MT7921e** — concurrent outbound API connections from multiple `hermes run` processes overwhelm MT7921e firmware, causing deauths and firmware resets. The bottleneck is NOT TCP connections or bandwidth (270 Mbps rx is plenty) — it's PACKET BURSTS hitting the firmware buffer. **Three tiers of fix, use the highest tier your system supports:**

  **TIER 1 (Quick):** `hermes config set delegation.max_concurrent_children 12` — works at decent signal without any proxy. Still prone to bursts.

  **TIER 2 (Better):** Swarm WiFi Optimizer — local proxy at :8921 with urllib3 connection pooling (50 keepalive), request coalescing, and adaptive semaphore based on signal. Enables 12–20 concurrent. `python3 ~/.hermes/scripts/swarm_wifi_optimizer.py`. See `references/swarm-wifi-optimizer.md`.

  **TIER 3 (Best — TURBOCHARGER):** Multi-layer optimization for 40+ concurrent agents. Adds kernel TCP buffer tuning (16MB, 5000 backlog), token-bucket pacing (sustained rate limit prevents burst overflow), aggressive connection pooling (80 keepalive, 40 pools), delta-based WiFi retry tracking (penalizes only when retries climb, not historical totals), and signal-adaptive auto-scaling. At -59 dBm: 40 concurrent safe. Start: `python3 ~/.hermes/scripts/swarm_turbocharger.py --port 8922`. Health: `curl localhost:8922/health`. Systemd: `~/.config/systemd/user/swarm-turbocharger.service`. Configure: `hermes config set delegation.max_concurrent_children 40`. See `references/swarm-turbocharger.md` for full 5-layer architecture.

## Files Created by This Skill

- `references/mt7921e-fixes.md` — MediaTek MT7921e specific fixes and dmesg patterns
- `references/band-steering-fix.md` — Step-by-step band steering lock procedure
- `scripts/wifi-diagnose.sh` — One-shot diagnostic script output for quick triage