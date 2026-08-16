# WiFi-Friendly Swarm Config for MT7921e / Filogic 330

## Problem

Running ENI swarm on hardware with MediaTek MT7921e (Filogic 330) WiFi causes complete WiFi dropout when the swarm launches 6+ concurrent `hermes run` processes. Each process makes outbound API calls to free-router (port 8920) → OpenRouter/Nvidia/SambaNova/Upstage/Zhipu endpoints, creating a burst of 6+ concurrent TCP connections that overwhelms the MT7921e firmware.

**Symptoms:**
- Periodic deauths (Reason 2/4/8) in dmesg
- Firmware resets (`enabling device` repeats)
- WiFi drops for 10-30s intervals
- Swarm appears "dead" — actually network stalled
- Builders time out or fail with connection errors

## Root Cause

MT7921e firmware cannot handle simultaneous:
1. Burst of 6+ concurrent TCP connections to external APIs
2. Bluetooth coexistence (BT/WiFi share antenna on MT7961 chip)
3. Band steering roaming (same SSID on 2.4/5 GHz)
4. IPv6 traffic (breaks IPv4 connectivity on this chip)
5. PCIe ASPM power management putting link to sleep

## Complete Fix Stack

### 1. System-Level WiFi Fixes (apply once, persist across reboots)

```bash
# Lock to 5 GHz BSSID (prevents band steering roaming)
nmcli connection modify "Wii Fii" \
  802-11-wireless.bssid 9C:1E:95:8B:3B:26 \
  802-11-wireless.band a \
  802-11-wireless.channel 149
nmcli connection up "Wii Fii"

# Disable IPv6 (MT7921e IPv6 breaks IPv4 connectivity)
nmcli connection modify "Wii Fii" \
  ipv6.method disabled \
  ipv6.ignore-auto-routes yes \
  ipv6.ignore-auto-dns yes

# Disable Bluetooth entirely (BT/WiFi share antenna on MT7961)
sudo systemctl disable --now bluetooth
rfkill block bluetooth

# System-wide PCIe ASPM off (kernel cmdline - survives reboot)
# /etc/default/grub: GRUB_CMDLINE_LINUX_DEFAULT="... pcie_aspm=off pcie_port_pm=off"
sudo update-grub

# Per-driver ASPM off (modprobe.d - survives kernel updates)
echo "options mt7921e disable_aspm=1" | sudo tee /etc/modprobe.d/mt7921e.conf
```

### 2. Swarm Config: `config/swarm_config.json`

```json
{
  "concurrency": {
    "max_concurrent_children": 4,
    "launch_delay_seconds": 15,
    "graceful_shutdown_timeout_seconds": 30,
    "max_idle_seconds": 30,
    "resource_gate": {
      "max_cpu_pct": 80,
      "min_free_ram_mb": 2048,
      "max_hermes_processes": 4,
      "check_interval_seconds": 5
    }
  },
  "fleet_optimization": {
    "stage_size": 4,
    "stage_delay_seconds": 15,
    "max_hermes_procs": 4,
    "nice_level": 15,
    "io_class": 3,
    "oom_score_adj": 500,
    "log_max_lines": 1000,
    "memory_limit_per_builder_gb": 2,
    "task_timeout_seconds": 600,
    "description": "Lag-free 50-builder fleet settings. Builders launch in stages, never exceed 4 concurrent hermes processes, run at lowest priority, and self-terminate before consuming system resources. Reduced from 6 to 4 to prevent WiFi saturation on MT7921e."
  },
  "rate_limiting": {
    "max_api_calls_per_minute": 60,
    "max_model_switches_per_hour": 10,
    "cooldown_after_rate_limit_seconds": 30,
    "description": "Global rate limits across all providers to avoid exhausting free tier quotas. Reduced from 120 to 60 to prevent WiFi saturation on MT7921e."
  }
}
```

**Key changes from defaults:**
| Parameter | Default | WiFi-Friendly | Reason |
|-----------|---------|---------------|--------|
| `max_concurrent_children` | 6 | 4 | Fewer concurrent `hermes run` = fewer simultaneous TCP connections |
| `launch_delay_seconds` | 12 | 15 | Stagger worker starts to avoid burst |
| `max_hermes_processes` | 6 | 4 | Hard limit on concurrent Hermes processes |
| `stage_size` | 5 | 4 | Launch 4 at a time, wait, then next 4 |
| `stage_delay_seconds` | 12 | 15 | Longer pause between stages |
| `max_hermes_procs` | 6 | 4 | Fleet optimization hard limit |
| `max_api_calls_per_minute` | 120 | 60 | Throttle outbound API calls |

### 3. Verification

After applying all fixes, run the swarm and verify:

```bash
# 1. WiFi stays on 5 GHz
nmcli -f in-use,ssid,bssid,chan,freq,signal,rate dev wifi list | grep -E '(IN-USE|Wii Fii)'
# Should show * on ch 149 (5745 MHz) @ 1170 Mbit/s

# 2. No deauths in kernel log during swarm run
dmesg -T -w | grep -i wlp4s0
# Should see ZERO authenticate/associate cycles after initial connect

# 3. Swarm completes tasks
eni-swarm start --project DEMIURGE --workers 4
# Watch: 33 tasks dispatched, all builders exit=0

# 4. Connectivity test during swarm
ping -c 3 1.1.1.1
# Should succeed throughout swarm run
```

## Test Results (July 2026)

| Metric | Before Fix | After Fix |
|--------|------------|-----------|
| WiFi drops during swarm | Every 1-5 min | Zero (60+ min test) |
| Concurrent workers | 6 | 4 |
| API calls/min | 120 | 60 |
| Swarm task completion | Timeouts/failures | All 33 tasks exit=0 |
| WiFi band | Roaming 2.4↔5 GHz | Locked 5 GHz ch 149 |
| Bluetooth | Active (interfering) | Disabled |

## Notes

- These settings reduce throughput slightly (fewer concurrent workers) but ensure **reliability** — the swarm actually completes instead of stalling on network drops
- On hardware with better WiFi (Intel AX200/AX210, wired ethernet), you can use higher concurrency
- The `free-router` proxy on port 8920 adds one local hop but doesn't count against the WiFi connection limit
- If you upgrade WiFi hardware, revert to defaults for maximum throughput