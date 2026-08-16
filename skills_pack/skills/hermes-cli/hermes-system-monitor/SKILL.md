---
name: hermes-system-monitor
description: System health monitoring — GPU (nvidia-smi for RTX 3060 Ti), CPU, RAM, disk, temperatures, processes, and network stats. Includes watchdog patterns with alert thresholds. Uses nvidia-smi 595.71.05, psutil 7.2.2, lm-sensors, and standard Linux tools.
---

# Hermes System Monitor

Comprehensive system health monitoring for this box. Covers GPU (NVIDIA RTX 3060 Ti
8GB + AMD RX 5700 XT), CPU (AMD Ryzen), RAM, disk, temperatures, processes, and
network. Uses nvidia-smi, psutil, lm-sensors, and standard Linux tools — all
pre-installed.

## Trigger Conditions

Use this skill when the user asks to:
- Check system health or resource usage
- Monitor GPU status / VRAM for ML workloads
- Diagnose performance problems (high CPU, low memory, disk full)
- Set up automated monitoring or alert thresholds
- Find what's consuming resources
- Check temperatures or thermal throttling

---

## Step 1: Full System Snapshot (One-Liner)

Run this to get a complete health overview in one shot:

```bash
echo "=== GPU (NVIDIA) ===" && nvidia-smi --query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total,fan.speed --format=csv,noheader && echo "" && echo "=== CPU ===" && lscpu | grep -E "Model name|CPU\(s\)|MHz" && uptime && echo "" && echo "=== RAM ===" && free -h && echo "" && echo "=== DISK ===" && df -h / /home && echo "" && echo "=== TEMPS ===" && sensors | grep -E "Core|temp|Tctl|Composite" && echo "" && echo "=== TOP PROCESSES ===" && ps aux --sort=-%mem | head -6 && echo "" && echo "=== NETWORK ===" && ss -tlnp | head -20 && echo "" && echo "=== GPU PROCESSES ===" && nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader
```

## Step 2: GPU Monitoring (NVIDIA RTX 3060 Ti)

### GPU Quick Check

```bash
nvidia-smi
```

This shows: GPU utilization, VRAM usage, temperature, fan speed, power draw,
and running compute processes.

### GPU Targeted Queries

```bash
# Just VRAM
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader

# Temperature + utilization
nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,utilization.memory --format=csv,noheader

# Power draw
nvidia-smi --query-gpu=power.draw,power.limit --format=csv,noheader

# Fan speed
nvidia-smi --query-gpu=fan.speed --format=csv,noheader

# Running GPU processes with VRAM per process
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
```

### GPU Watchdog with Python (psutil + nvidia-smi)

```python
import subprocess, time, json

THRESHOLDS = {
    "gpu_temp_c": 85,       # Alert if GPU > 85°C
    "gpu_util_pct": 95,     # Alert if sustained > 95% (possible hang)
    "vram_used_pct": 90,    # Alert if > 90% VRAM used
}

def get_gpu_stats():
    """Parse nvidia-smi output into a dict."""
    result = subprocess.run([
        "nvidia-smi",
        "--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total",
        "--format=csv,noheader,nounits"
    ], capture_output=True, text=True)
    parts = result.stdout.strip().split(",")
    return {
        "temp": float(parts[0].strip()),
        "util": float(parts[1].strip()),
        "vram_used_mb": float(parts[2].strip()),
        "vram_total_mb": float(parts[3].strip()),
    }

def watchdog():
    stats = get_gpu_stats()
    vram_pct = (stats["vram_used_mb"] / stats["vram_total_mb"]) * 100
    alerts = []
    if stats["temp"] > THRESHOLDS["gpu_temp_c"]:
        alerts.append(f"GPU TEMP: {stats['temp']}°C > {THRESHOLDS['gpu_temp_c']}°C")
    if stats["util"] > THRESHOLDS["gpu_util_pct"]:
        alerts.append(f"GPU UTIL: {stats['util']}% > {THRESHOLDS['gpu_util_pct']}%")
    if vram_pct > THRESHOLDS["vram_used_pct"]:
        alerts.append(f"VRAM: {vram_pct:.1f}% used")
    return stats, alerts

stats, alerts = watchdog()
print(f"GPU: {stats['temp']}°C | {stats['util']}% util | {stats['vram_used_mb']:.0f}/{stats['vram_total_mb']:.0f} MB VRAM")
if alerts:
    for a in alerts:
        print(f"ALERT: {a}")
else:
    print("GPU: OK")
```

### GPU for AMD RX 5700 XT (secondary card)

The AMD card may be present as a secondary GPU. Check with:

```bash
# See if AMD GPU is visible
lspci | grep -i amd
lspci | grep -i vga

# If rocm-smi is installed:
rocm-smi 2>/dev/null || echo "rocm-smi not installed"

# Generic GPU info via /sys
cat /sys/class/drm/card*/device/vendor 2>/dev/null
```

Note: nvidia-smi only covers the NVIDIA card. The AMD card requires `rocm-smi`
(not installed by default). Most monitoring focuses on the RTX 3060 Ti.

---

## Step 3: CPU Monitoring

### Quick CPU Overview

```bash
lscpu | grep -E "Model name|CPU\(s\)|Thread|Core|MHz"
```

### Real-time CPU Usage with psutil

```python
import psutil

# Overall CPU usage (1-second sample)
cpu_pct = psutil.cpu_percent(interval=1)
print(f"CPU Usage: {cpu_pct}%")

# Per-core
per_core = psutil.cpu_percent(interval=1, percpu=True)
for i, pct in enumerate(per_core):
    bar = "█" * int(pct / 5)
    print(f"  Core {i:2d}: {pct:5.1f}% {bar}")

# Load averages
load1, load5, load15 = psutil.getloadavg()
cpu_count = psutil.cpu_count()
print(f"Load: {load1:.2f} / {load5:.2f} / {load15:.2f}  (cores: {cpu_count})")
```

### CPU Alert Thresholds

```python
import psutil

cpu_pct = psutil.cpu_percent(interval=1)
load1, load5, load15 = psutil.getloadavg()
cpu_count = psutil.cpu_count()

alerts = []
if cpu_pct > 90:
    alerts.append(f"CPU {cpu_pct}% > 90% threshold")
if load1 > cpu_count * 1.5:
    alerts.append(f"Load avg {load1:.1f} > {cpu_count * 1.5:.1f} (1.5x cores)")
if load15 > cpu_count:
    alerts.append(f"Sustained load: {load15:.1f} > {cpu_count} (cores)")

for a in alerts:
    print(f"ALERT: {a}")
```

---

## Step 4: RAM Monitoring

### Quick Check

```bash
free -h
```

### Detailed RAM with psutil

```python
import psutil

mem = psutil.virtual_memory()
swap = psutil.swap_memory()

print(f"RAM:  {mem.used / 1024**3:.1f} GB / {mem.total / 1024**3:.1f} GB ({mem.percent}%)")
print(f"  Available: {mem.available / 1024**3:.1f} GB")
print(f"Swap: {swap.used / 1024**3:.1f} GB / {swap.total / 1024**3:.1f} GB ({swap.percent}%)")

if mem.percent > 90:
    print("ALERT: RAM usage > 90%")
if swap.percent > 50:
    print("ALERT: Heavy swap usage — system may be thrashing")
```

### Top Memory Consumers

```python
import psutil

procs = []
for p in psutil.process_iter(['pid', 'name', 'memory_percent', 'memory_info']):
    try:
        procs.append(p.info)
    except psutil.NoSuchProcess:
        pass

procs.sort(key=lambda x: x.get('memory_percent', 0), reverse=True)
print("Top memory consumers:")
for p in procs[:5]:
    name = p['name'][:30]
    rss_mb = p.get('memory_info', None)
    rss = rss_mb.rss / 1024**2 if rss_mb else 0
    print(f"  PID {p['pid']:6d}  {name:30s}  {rss:8.1f} MB  ({p['memory_percent']:.1f}%)")
```

---

## Step 5: Disk Monitoring

### Quick Check

```bash
df -h / /home
```

### Detailed Disk with psutil

```python
import psutil

for part in psutil.disk_partitions():
    try:
        usage = psutil.disk_usage(part.mountpoint)
        if usage.total > 1_000_000_000:  # Skip small partitions (>1GB)
            alert = " ALERT" if usage.percent > 90 else ""
            print(f"{part.mountpoint:20s} {usage.used/1024**3:6.1f}/{usage.total/1024**3:6.1f} GB ({usage.percent}%){alert}")
    except PermissionError:
        pass
```

### Disk I/O Stats

```bash
# I/O stats (requires sysstat, usually pre-installed)
iostat -x 1 1 2>/dev/null || echo "iostat not available, use /proc/diskstats"

# Alternative: read raw stats
cat /proc/diskstats | head -5
```

---

## Step 6: Temperature Monitoring

### All Sensors

```bash
sensors
```

### Targeted Temperature Check

```bash
# NVMe SSD
sensors | grep -A2 "nvme"

# CPU (k10temp for AMD Ryzen)
sensors | grep -A5 "k10temp"

# GPU is covered by nvidia-smi (see Step 2)
```

### Temperature Alert Script

```python
import subprocess, re

def get_cpu_temp():
    """Parse k10temp from sensors output."""
    result = subprocess.run(["sensors"], capture_output=True, text=True)
    for line in result.stdout.split("\n"):
        if "Tctl:" in line:
            match = re.search(r'\+?([\d.]+)°C', line)
            if match:
                return float(match.group(1))
    return None

cpu_temp = get_cpu_temp()
if cpu_temp:
    status = "OK" if cpu_temp < 85 else "ALERT"
    print(f"CPU temp: {cpu_temp}°C [{status}]")

# GPU temp via nvidia-smi
result = subprocess.run(
    ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader"],
    capture_output=True, text=True
)
gpu_temp = float(result.stdout.strip())
status = "OK" if gpu_temp < 85 else "ALERT"
print(f"GPU temp: {gpu_temp}°C [{status}]")
```

### Temperature Thresholds

| Component | Warning | Critical | Action if exceeded |
|-----------|---------|----------|--------------------|
| CPU (Tctl) | 80°C | 90°C | Check cooler, reduce load |
| GPU | 83°C | 90°C | Increase fan curve, check airflow |
| NVMe SSD | 60°C | 70°C | Improve case airflow |
| VRM/Motherboard | 80°C | 95°C | Reduce overclock, check cooling |

---

## Step 7: Process Monitoring

### Top CPU Consumers

```bash
ps aux --sort=-%cpu | head -11
```

### Top Memory Consumers

```bash
ps aux --sort=-%mem | head -11
```

### Find Process by Name

```bash
pgrep -a python
pgrep -a node
```

### Kill Stuck Processes

```bash
# Find zombie processes
ps aux | awk '$8 ~ /Z/ {print $2, $11}'

# Kill a process by PID
kill -9 <PID>

# Kill all processes matching a name (careful!)
pkill -f "process_name_pattern"
```

---

## Step 8: Network Monitoring

### Active Connections

```bash
# Listening servers
ss -tlnp

# All TCP connections
ss -tanp

# Connection count by state
ss -tan | awk '{print $1}' | sort | uniq -c | sort -rn
```

### Network Interface Stats

```bash
ip -s link show
```

### Python Network Stats with psutil

```python
import psutil

# Per-interface stats
counters = psutil.net_io_counters(pernic=True)
for iface, stats in counters.items():
    if stats.bytes_sent > 0 or stats.bytes_recv > 0:
        print(f"{iface:10s}  RX: {stats.bytes_recv / 1024**2:8.1f} MB  TX: {stats.bytes_sent / 1024**2:8.1f} MB")

# Active connections count
conns = psutil.net_connections()
print(f"\nActive connections: {len(conns)}")
by_state = {}
for c in conns:
    by_state[c.status] = by_state.get(c.status, 0) + 1
for state, count in by_state.items():
    print(f"  {state}: {count}")
```

---

## Step 9: Continuous Watchdog (Monitoring Loop)

Full watchdog script that checks everything and alerts on thresholds:

```python
import psutil, subprocess, time, json
from datetime import datetime

THRESHOLDS = {
    "cpu_pct": 90,
    "ram_pct": 90,
    "disk_pct": 90,
    "gpu_temp": 85,
    "cpu_temp": 85,
    "gpu_util_sustained": 95,  # sustained over 3 checks
}

def check_all():
    alerts = []
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # CPU
    cpu = psutil.cpu_percent(interval=0.5)
    if cpu > THRESHOLDS["cpu_pct"]:
        alerts.append(f"CPU {cpu}%")

    # RAM
    mem = psutil.virtual_memory()
    if mem.percent > THRESHOLDS["ram_pct"]:
        alerts.append(f"RAM {mem.percent}%")

    # Disk
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
            if usage.total > 1_000_000_000 and usage.percent > THRESHOLDS["disk_pct"]:
                alerts.append(f"Disk {part.mountpoint} {usage.percent}%")
        except:
            pass

    # GPU
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        gpu_temp, gpu_util, vram_used, vram_total = map(float, result.stdout.strip().split(","))
        if gpu_temp > THRESHOLDS["gpu_temp"]:
            alerts.append(f"GPU temp {gpu_temp}°C")
        if (vram_used / vram_total) * 100 > 90:
            alerts.append(f"GPU VRAM {(vram_used/vram_total)*100:.0f}%")
    except:
        pass

    # Status line
    status = "ALERT" if alerts else "OK"
    print(f"[{ts}] {status} | CPU:{cpu:.0f}% RAM:{mem.percent:.0f}%")
    if alerts:
        for a in alerts:
            print(f"  -> {a}")
    return len(alerts) == 0

# Example: check once
check_all()

# Example: loop every 30 seconds (Ctrl+C to stop)
# while True:
#     check_all()
#     time.sleep(30)
```

---

## Step 10: Quick Status Dashboard (One-Call)

For a speedy at-a-glance status, save this as a Hermes one-liner:

```bash
echo "=== SYSTEM STATUS $(date) ===" && echo "--- GPU ---" && nvidia-smi --query-gpu=utilization.gpu,memory.used,temperature.gpu --format=csv,noheader && echo "--- CPU ---" && top -bn1 | head -5 && echo "--- RAM ---" && free -h | grep -E "Mem|Swap" && echo "--- DISK ---" && df -h / /home | tail -2 && echo "--- CONNS ---" && ss -tan | wc -l && echo "==============================="
```

---

## Pitfalls

1. **nvidia-smi requires Xorg or persistence mode**: If the GPU isn't initialized
   (no X server, no persistence daemon), `nvidia-smi` may show N/A for some
   values or return errors. Start the persistence daemon:
   ```bash
   sudo nvidia-persistenced --user nvidia-persistenced
   ```

2. **sensors needs lm-sensors configured**: Run `sudo sensors-detect` once if
   sensors output is sparse. On this box, it's already configured.

3. **psutil disk counters reset on reboot**: Network and disk I/O counters are
   since-boot totals. Compute deltas between samples for rates.

4. **Monitoring loops in foreground will timeout**: For continuous monitoring,
   use `terminal(background=true, notify_on_complete=true)` but note the process
   never exits. Better: run a single snapshot and exit.

5. **psutil.cpu_percent() blocks for 1 second**: The `interval` parameter causes
   a sleep. Use `interval=0.1` for faster (but less accurate) readings.

6. **nvidia-smi CSV parsing is sensitive to whitespace**: Strip all values before
   converting to float. The `nouns` flag removes unit suffixes.

7. **GPU temp of 0 or N/A**: GPU may be in a low-power state. Run a quick CUDA
   workload to wake it up, or check that persistence mode is on.

## Verification

```bash
# Run the full snapshot
echo "=== SYSTEM STATUS $(date) ===" && echo "--- GPU ---" && nvidia-smi --query-gpu=utilization.gpu,memory.used,temperature.gpu --format=csv,noheader && echo "--- CPU ---" && top -bn1 | head -5 && echo "--- RAM ---" && free -h | grep -E "Mem|Swap" && echo "--- DISK ---" && df -h / /home | tail -2 && echo "--- CONNS ---" && ss -tan | wc -l && echo "=== DONE ==="
```