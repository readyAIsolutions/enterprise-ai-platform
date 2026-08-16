# MediaTek MT7921e (Filogic 330) Specific Fixes

## Hardware ID
- **PCI ID:** 14c3:7961
- **Subsystem:** Often AzureWave 1a3b:4680
- **Kernel driver:** mt7921e
- **Firmware:** mt7921_firmware.bin (in linux-firmware)

## Required Kernel Parameters

Add to `/etc/default/grub` GRUB_CMDLINE_LINUX_DEFAULT:

**Per-driver (WiFi-only issues):**
```
mt7921e.disable_aspm=Y
```

**System-wide (when BOTH WiFi AND ethernet drop simultaneously):**
```
pcie_aspm=off
```

Then `sudo update-grub` and reboot.

**Also add to `/etc/modprobe.d/mt7921e.conf` (persists across kernel updates):**
```
options mt7921e disable_aspm=1
```
(Values `Y`, `1`, or `true` are equivalent for boolean kernel parameters.)

**Verify:**
```bash
cat /proc/cmdline | grep -E 'pcie_aspm|mt7921e'
cat /sys/module/mt7921e/parameters/disable_aspm  # should output Y
cat /sys/module/pcie_aspm/parameters/policy  # should show "performance" or "off"
```

## Common dmesg Patterns

### Normal Boot (Good)
```
mt7921e 0000:04:00.0: enabling device (0000 -> 0002)
mt7921e 0000:04:00.0: ASIC revision: 79610010
mt7921e 0000:04:00.0: HW/SW Version: 0x8a108a10, Build Time: 20260224110909a
mt7921e 0000:04:00.0: WM Firmware Version: ____010000, Build Time: 20260224110949
mt7921e 0000:04:00.0 wlp4s0: renamed from wlan0
wlp4s0: authenticate with <BSSID>
wlp4s0: authenticated
wlp4s0: associate with <BSSID>
wlp4s0: associated
wlp4s0: Limiting TX power to 30 (30 - 0) dBm as advertised by <BSSID>
```

### Problem Patterns

| Pattern | Meaning | Fix |
|---------|---------|-----|
| `enabling device` repeats | ASPM waking device repeatedly | `disable_aspm=Y` |
| `deauthenticated from <BSSID> (Reason: 2)` | AP kicked client (inactivity) | Disable power save, check AP logs |
| `deauthenticated from <BSSID> (Reason: 4)` | Disassociated (inactivity) | Disable power save |
| `deauthenticated from <BSSID> (Reason: 8)` | Disassociated (leaving BSS) | Band steering / roaming issue |
| `Firmware crash` / `Firmware assert` | FW bug | Update linux-firmware, report upstream |
| `HW/SW Version` mismatch | FW/driver version skew | Update kernel + linux-firmware together |

## Power Save Control

```bash
# Runtime (persists until reboot)
iw dev wlp4s0 set power_save off

# Persistent via NetworkManager
nmcli connection modify "<SSID>" 802-11-wireless.powersave 2

# Global NetworkManager config
# /etc/NetworkManager/conf.d/wifi-powersave.conf:
# [connection]
# wifi.powersave = 2
```

## Firmware Updates

```bash
# Check current firmware version in dmesg
dmesg -T | grep "WM Firmware Version"

# Update via package manager (Ubuntu/Debian)
sudo apt update && sudo apt install linux-firmware

# Check available version
apt show linux-firmware | grep Version
```

### **Upstream Firmware (when package is stale)**

Ubuntu's `linux-firmware` often lags kernel.org git by months. For persistent issues, fetch latest:

```bash
# Clone upstream firmware repo
cd /tmp && git clone --depth 1 https://git.kernel.org/pub/scm/linux/kernel/git/firmware/linux-firmware.git

# Check dates in git log for MT7961 files
cd linux-firmware
git log -1 --format="%ci %s" -- mediatek/WIFI_MT7961_patch_mcu_1_2_hdr.bin
git log -1 --format="%ci %s" -- mediatek/WIFI_RAM_CODE_MT7961_1.bin

# Copy newer firmware (MediaTek MT7961 = MT7921E Filogic 330)
sudo cp mediatek/WIFI_MT7961_patch_mcu_1_2_hdr.bin /lib/firmware/mediatek/
sudo cp mediatek/WIFI_RAM_CODE_MT7961_1.bin /lib/firmware/mediatek/
sudo cp mediatek/WIFI_MT7961_patch_mcu_1a_2_hdr.bin /lib/firmware/mediatek/
sudo cp mediatek/WIFI_RAM_CODE_MT7961_1a.bin /lib/firmware/mediatek/

# Also update Bluetooth firmware on same chip
sudo cp mediatek/BT_RAM_CODE_MT7961_1_2_hdr.bin /lib/firmware/mediatek/
sudo cp mediatek/BT_RAM_CODE_MT7961_1a_2_hdr.bin /lib/firmware/mediatek/

# Regenerate initramfs and reload driver
sudo update-initramfs -u
sudo modprobe -r mt7921e && sleep 2 && sudo modprobe mt7921e

# Verify new firmware loaded
dmesg -T | grep "WM Firmware Version"
```

**Ethernet firmware (when both WiFi + ethernet drop):**
```bash
# RTL8168h (Realtek Gigabit Ethernet) firmware
sudo cp mediatek/rtl_nic/rtl8168h-2.fw /lib/firmware/rtl_nic/
sudo update-initramfs -u
sudo modprobe -r r8169 && sleep 2 && sudo modprobe r8169
```

## Known Issues (as of Linux 7.x)

1. **ASPM must be disabled** — causes spontaneous disconnects under load
2. **Band steering triggers roaming loops** — lock to 5 GHz BSSID
3. **Bluetooth coexistence** — if BT + WiFi on same chip, may need `bt_coex_active=0` (not exposed in mt7921e yet)
4. **5 GHz DFS channels** — may cause disconnects during radar detection; avoid DFS channels on router if unstable
5. **Simultaneous ethernet drops** — if ethernet (e.g. Realtek r8169) drops at same time as WiFi, it's system-wide PCIe ASPM. Fix with `pcie_aspm=off` kernel parameter, not just `mt7921e.disable_aspm=Y`
6. **Invalid modprobe params are silently ignored** — check `dmesg | grep "unknown parameter"` (e.g. `r8169 eee_enable=0` doesn't exist; `r8169` has no `disable_aspm` or `aspm` params on kernel 7.x; `mt7921e debug=` param also doesn't exist)
7. **IPv6 breaks IPv4 connectivity** — interface shows connected, has IPv4 address/gateway/DNS, but `ping 1.1.1.1` fails. Fix: `nmcli connection modify "<SSID>" ipv6.method disabled ipv6.ignore-auto-routes yes ipv6.ignore-auto-dns yes`
8. **AI swarm / high-concurrency workloads saturate WiFi** — concurrent outbound API connections from multiple `hermes run` processes (6+ concurrent) overwhelm MT7921e firmware, causing deauths and firmware resets. **SOLUTION (2026-08-01): Swarm WiFi Optimizer** — a local connection-pooling proxy at :8921 that enables 12-20+ concurrent subagents via connection pooling, adaptive throttling based on WiFi signal strength, request coalescing, and circuit breaker. See `references/swarm-wifi-optimizer.md`. Legacy fix: reduce swarm concurrency (`max_concurrent_children: 4`, `stage_size: 4`, `launch_delay_seconds: 15`), limit API rate (`max_api_calls_per_minute: 60`), lock to 5 GHz BSSID, and soft-block Bluetooth (`rfkill block bluetooth`).

### Verified Configuration (2026-08-01)

**The single most impactful change:** `hermes config set delegation.max_concurrent_children 4`

Before: `max_concurrent_children: 10` → WiFi drops every 30-60 minutes under load.
After: `max_concurrent_children: 4` → zero drops over hours of continuous swarm operation.

This controls Hermes subagent spawning globally. 4 concurrent subagents = 4 concurrent outbound API connections, well within MT7921e firmware limits. No other config changes needed when only Hermes delegate_task is in use (swarm-specific config files at `~/Desktop/Projects/ENI_Swarm_NEW/config/` apply only to the standalone ENI Swarm driver, not to Hermes-native delegate_task).

## AI Swarm / High-Concurrency Workload Fix (July 2026)

**Problem:** ENI swarm launching 6+ concurrent `hermes run` processes, each making outbound API calls to free-router (port 8920) → OpenRouter/Nvidia/SambaNova endpoints, saturated the MT7921e firmware causing:
- Periodic deauths (Reason 2/4/8)
- Firmware resets (`enabling device` repeats in dmesg)
- Complete WiFi dropout for 10-30s intervals
- Swarm appearing "dead" (actually network stalled)

**Root cause:** MT7921e firmware cannot handle burst of 6+ concurrent TCP connections + Bluetooth coexistence + band steering roaming simultaneously.

**Complete fix stack:**

```bash
# 1. Lock to 5 GHz BSSID (prevents band steering roaming)
nmcli connection modify "Wii Fii" \
  802-11-wireless.bssid 9C:1E:95:8B:3B:26 \
  802-11-wireless.band a \
  802-11-wireless.channel 149
nmcli connection up "Wii Fii"

# 2. Disable IPv6 (MT7921e IPv6 breaks IPv4 connectivity)
nmcli connection modify "Wii Fii" \
  ipv6.method disabled \
  ipv6.ignore-auto-routes yes \
  ipv6.ignore-auto-dns yes

# 3. Disable Bluetooth entirely (BT/WiFi share antenna on MT7961)
sudo systemctl disable --now bluetooth
rfkill block bluetooth

# 4. System-wide PCIe ASPM off (kernel cmdline - survives reboot)
# /etc/default/grub: GRUB_CMDLINE_LINUX_DEFAULT="... pcie_aspm=off pcie_port_pm=off"
sudo update-grub

# 5. Per-driver ASPM off (modprobe.d - survives kernel updates)
echo "options mt7921e disable_aspm=1" | sudo tee /etc/modprobe.d/mt7921e.conf

# 6a. Reduce swarm concurrency — PRIMARY FIX (controls Hermes subagent spawning globally)
hermes config set delegation.max_concurrent_children 4

# 6b. Also in swarm-specific config if using ENI Swarm directly:
# ~/Desktop/Projects/ENI_Swarm_NEW/config/swarm_config.json:
# "concurrency": { "max_concurrent_children": 4, "launch_delay_seconds": 15, "max_hermes_processes": 4 }
# "fleet_optimization": { "stage_size": 4, "stage_delay_seconds": 15, "max_hermes_procs": 4 }
# "rate_limiting": { "max_api_calls_per_minute": 60 }
```

**Verification after full fix:**
- Swarm runs 33 tasks across 60 minis with 4 concurrent workers
- WiFi stays locked to 5 GHz ch 149 @ 1170 Mbit/s
- Zero deauths, zero roams, zero drops for 60+ min test
- All builders complete with exit=0

## Firmware Version Format Note

MT7921e / MT7961 WM Firmware Version in dmesg shows as `____010000` (underscores = build metadata). This is NORMAL for MediaTek firmware — not a version parsing error. The actual version is in the Build Time field (e.g., `20260224110949` = 2026-02-24 11:09:49).

## Debug Commands

```bash
# Full driver state
cat /sys/kernel/debug/ieee80211/phy*/mt76/debugfs/* 2>/dev/null | head -100

# TX/RX stats
cat /sys/class/net/wlp4s0/statistics/*

# Regulatory domain
iw reg get

# Verify all fixes active
cat /proc/cmdline | grep -E 'pcie_aspm|mt7921e'
cat /sys/module/mt7921e/parameters/disable_aspm
rfkill list
nmcli connection show "Wii Fii" | grep -E 'bssid|band|channel|ipv6.method'
systemctl is-enabled bluetooth
```