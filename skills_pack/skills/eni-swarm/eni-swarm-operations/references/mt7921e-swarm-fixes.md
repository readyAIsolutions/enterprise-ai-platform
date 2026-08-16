# MT7921e + ENI Swarm — Complete WiFi Stability Fixes

**Hardware:** MediaTek MT7921 802.11ax PCIe (Filogic 330) [14c3:7961]
**Driver:** mt7921e (kernel 7.0.0-28-generic)
**Firmware:** WM Version ____010000, Build 20260224110949
**Bluetooth:** MT7961 (shared antenna, btmtk module)

---

## Root Cause Analysis

The ENI Swarm launching 60 builders (max 6 concurrent `hermes run` processes) creates:
1. **Burst TLS connections** — 4-6 simultaneous outbound HTTPS to free API providers
2. **PCIe link power cycling** — ASPM puts link to sleep; burst wakes it → firmware crash
3. **Band steering roaming** — Same SSID on 2.4/5 GHz → client roams mid-transfer → deauth
4. **Bluetooth coexistence** — BT + WiFi share antenna; concurrent traffic = drops
5. **IPv6 stack bug** — MT7921e firmware: IPv6 enabled → IPv4 passes but `ping` fails

---

## Fix Stack (All Layers Required)

### Layer 1: NetworkManager Connection Profile (Runtime)

```bash
# Find 5 GHz BSSID
nmcli -f ssid,bssid,chan,freq,signal,security dev wifi list | grep "YOUR_SSID"

# Example output:
# YOUR_SSID  AA:BB:CC:DD:EE:FF  11    2462 MHz  80  WPA2   (2.4 GHz)
# YOUR_SSID  AA:BB:CC:DD:EE:11  149   5745 MHz  69  WPA2   (5 GHz)

# Lock to 5 GHz BSSID
nmcli connection modify "YOUR_SSID" \
  802-11-wireless.bssid AA:BB:CC:DD:EE:11 \
  802-11-wireless.band a \
  802-11-wireless.channel 149

# Disable WiFi power save
nmcli connection modify "YOUR_SSID" 802-11-wireless.powersave 2

# Disable IPv6 (critical for MT7921e)
nmcli connection modify "YOUR_SSID" \
  ipv6.method disabled \
  ipv6.ignore-auto-routes yes \
  ipv6.ignore-auto-dns yes

# Reconnect
nmcli connection up "YOUR_SSID"
```

**Verify:**
```bash
nmcli -f in-use,ssid,bssid,chan,freq,signal,rate dev wifi list | grep IN-USE
# Must show: 5 GHz channel (36-165), rate > 1000 Mbit/s
```

---

### Layer 2: Kernel Command Line (Boot Persistent)

**File:** `/etc/default/grub`

```bash
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash pcie_aspm=off pcie_port_pm=off"
```

Apply:
```bash
sudo update-grub
# Reboot required
```

**Verify after reboot:**
```bash
cat /proc/cmdline | grep -E 'pcie_aspm=off|pcie_port_pm=off'
```

---

### Layer 3: Module Parameters (Boot Persistent)

**File:** `/etc/modprobe.d/mt7921e.conf`

```bash
options mt7921e disable_aspm=1
```

**Note:** Value `1`, `Y`, or `true` all work for boolean kernel params.

**Verify after reboot:**
```bash
cat /sys/module/mt7921e/parameters/disable_aspm
# Output: Y
```

---

### Layer 4: Bluetooth Disable (Boot Persistent)

```bash
# Stop and disable service
sudo systemctl disable --now bluetooth

# Block at rfkill level (survives service restart)
rfkill block bluetooth

# Make rfkill persistent across reboot
echo 'rfkill block bluetooth' | sudo tee /etc/rc.local
sudo chmod +x /etc/rc.local
```

**Verify:**
```bash
rfkill list | grep -A1 Bluetooth
# Soft blocked: yes
```

---

### Layer 5: ENI Swarm Concurrency Tuning

**File:** `~/Desktop/Projects/ENI_Swarm_NEW/config/swarm_config.json`

```json
{
  "concurrency": {
    "max_concurrent_children": 4,
    "launch_delay_seconds": 15,
    "max_hermes_processes": 4
  },
  "fleet_optimization": {
    "stage_size": 4,
    "stage_delay_seconds": 15,
    "max_hermes_procs": 4
  },
  "rate_limiting": {
    "max_api_calls_per_minute": 60
  }
}
```

**Rationale:**
| Parameter | Before | After | Why |
|-----------|--------|-------|-----|
| max_concurrent_children | 6 | 4 | MT7921e saturates at ~4 concurrent TLS |
| launch_delay_seconds | 12 | 15 | Stagger connection storms |
| max_hermes_processes | 6 | 4 | Match concurrency limit |
| stage_size | 5 | 4 | Wave size = concurrency |
| stage_delay_seconds | 12 | 15 | Breathing room between waves |
| max_api_calls_per_minute | 120 | 60 | Global cap across all providers |

---

## Verification Protocol

### Pre-Swarm Checklist

```bash
#!/bin/bash
# Run before every swarm start

echo "1. Kernel params:"
cat /proc/cmdline | grep -E 'pcie_aspm=off|pcie_port_pm=off' && echo "   ✅" || echo "   ❌ MISSING"

echo "2. Module param:"
cat /sys/module/mt7921e/parameters/disable_aspm | grep -q Y && echo "   ✅" || echo "   ❌"

echo "3. Bluetooth:"
rfkill list | grep -q "Bluetooth.*Soft blocked: yes" && echo "   ✅" || echo "   ❌"

echo "4. WiFi band lock:"
nmcli -f in-use,ssid,bssid,chan,freq,signal,rate dev wifi list | grep IN-USE | grep -q "5[0-9][0-9][0-9] MHz" && echo "   ✅ 5 GHz" || echo "   ❌ 2.4 GHz!"

echo "5. IPv6 disabled:"
nmcli connection show "YOUR_SSID" | grep -q "ipv6.method:.*disabled" && echo "   ✅" || echo "   ❌"

echo "6. Free router:"
curl -sf http://localhost:8920/health >/dev/null && echo "   ✅" || echo "   ❌"

echo "7. Swarm config:"
python3 -c "
import json
d=json.load(open('/home/hunter/Desktop/Projects/ENI_Swarm_NEW/config/swarm_config.json'))
assert d['concurrency']['max_concurrent_children']==4
assert d['concurrency']['launch_delay_seconds']==15
assert d['fleet_optimization']['stage_size']==4
assert d['rate_limiting']['max_api_calls_per_minute']==60
print('   ✅ Config optimized')
"
```

### During Swarm Monitoring

```bash
# Watch WiFi state every 10s
watch -n 10 'nmcli device show wlp4s0 | grep STATE; nmcli -f in-use,ssid,bssid,chan,freq,signal,rate dev wifi list | grep IN-USE'

# Watch master log
tail -f ~/.cache/eni_swarm/master.log | grep -E 'completed|Dispatching|STALLED|CRITICAL'
```

---

## dmesg Patterns to Watch

### Good (Normal Operation)
```
mt7921e 0000:04:00.0: WM Firmware Version: ____010000, Build Time: 20260224110949
mt7921e 0000:04:00.0 wlp4s0: renamed from wlan0
```

### Bad (ASPM/Firmware Issues)
```
mt7921e 0000:04:00.0: Firmware init failed
mt7921e 0000:04:00.0: MCU restart
mt7921e 0000:04:00.0: Firmware assert
pcieport 0000:00:01.0: AER: Corrected error received
```

### Bad (Band Steering)
```
wlp4s0: authenticate with AA:BB:CC:DD:EE:FF
wlp4s0: associate with AA:BB:CC:DD:EE:FF
wlp4s0: deauthenticated from AA:BB:CC:DD:EE:FF (Reason: 3=DEAUTH_LEAVING)
```

---

## Firmware Upgrade (If Issues Persist)

Ubuntu's `linux-firmware` package lags upstream. Get latest MT7961 from kernel.org:

```bash
cd /tmp
git clone --depth=1 https://git.kernel.org/pub/scm/linux/kernel/git/firmware/linux-firmware.git
cd linux-firmware
sudo cp mediatek/WIFI_MT7961* /lib/firmware/mediatek/
sudo cp mediatek/BT_RAM_CODE_MT7961* /lib/firmware/mediatek/
sudo update-initramfs -u
# Reboot
```

**Verify new firmware:**
```bash
dmesg -T | grep "WM Firmware Version"
# Should show newer build date
```

---

## Emergency Recovery (WiFi Dead)

```bash
# 1. Reload driver
sudo modprobe -r mt7921e
sleep 2
sudo modprobe mt7921e

# 2. Re-apply NM lock (may have reverted)
nmcli connection up "YOUR_SSID"

# 3. If still dead, reboot (kernel params + modprobe.d apply)
sudo reboot
```

---

## Related Files

- `~/Desktop/Projects/ENI_Swarm_NEW/config/swarm_config.json` — Optimized concurrency
- `/etc/default/grub` — Kernel cmdline
- `/etc/modprobe.d/mt7921e.conf` — Module params
- `~/.config/systemd/user/free-router.service` — Local LLM proxy