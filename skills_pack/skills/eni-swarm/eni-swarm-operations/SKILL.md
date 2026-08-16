---
name: eni-swarm-operations
description: "Complete operational skill for ENI Swarm — start/stop, configure, monitor, debug, and manage the 50-builder fleet with WiFi-stable settings for MT7921e hardware. Fleet-monitor cron interpretation: refs/fleet-monitor-ledger.md; dormant-vs-live mtime + alert-noise analysis: refs/fleet-staleness-interpretation.md; ledger-read pits (regex + stale-re-read + zero-padded filenames 05→5 + empty-file crash-guard skip): refs/fleet-monitor-ledger-read-pitfalls.md; no-dump one-liner diagnostics (ledger counts, mtimes, empty-file crash-guard probe, dormancy checks + the ENI-COMPRESSED SNAFU): references/fleet-monitor-concise-summary.md + references/fleet-monitor-diagnostic-one-liners.md; builder FIFO watcher-cron mechanics + stale-job diagnostics + on-disk builder state file-layout map + config-workdir-vs-live-tree path caveat: references/builder-fifo-cron-diagnostics.md; one-shot re-runnable fleet-monitor pass (compute-don't-dump; handles zero-padded names + crash-guard empty files): scripts/fleet_monitor_pass.py"
category: eni-swarm
version: 1.0.0
tags: [eni, swarm, operations, mt7921e, wifi-stability, hermes, free-router]
---

# ENI Swarm Operations Skill

> **Idle-slot protocol**: A cron/runner firing for a BUILDER slot is usually a routine
> idle check-in, NOT dispatched work. Before acting, follow
> `references/builder-idle-slot-check.md` — verify STATUS/roster/FIFO/queue. If the
> slot is `[IDLE]` with no task, the correct outcome is a no-op, not inventing work.

Provides battle-tested procedures for running the ENI Swarm (50 BUILDERS + HEARTBEAT + PRODUCT_LEAD + 8 ENI_SELF) on hardware with MediaTek MT7921e WiFi. Includes all WiFi stability fixes and optimal concurrency settings.

## Quick Reference

| Command | Purpose |
|---------|---------|
| `eni-swarm start --project DEMIURGE --workers 4` | Launch swarm with 4 concurrent workers |
| `eni-swarm stop` | Stop all swarm processes |
| `eni-swarm status` | Full status dashboard |
| `eni-swarm logs --follow` | Tail master log |
| `eni-swarm config show` | View current config |
| `eni-swarm config edit` | Edit swarm_config.json |
| `eni-swarm task list` | List all 60 mini tasks |
| `eni-swarm heartbeat` | Real-time pulse monitor |

---

## Prerequisites (Run Once)

### 1. WiFi Stability Fixes for MT7921e (Filogic 330)

**These are mandatory — without them the swarm kills WiFi under load.**

```bash
# Lock to 5 GHz BSSID (prevents band steering roaming)
nmcli connection modify "YOUR_SSID" \
  802-11-wireless.bssid <5GHZ_BSSID> \
  802-11-wireless.band a \
  802-11-wireless.channel <5GHZ_CHANNEL>
nmcli connection up "YOUR_SSID"

# Disable WiFi power save (persistent)
nmcli connection modify "YOUR_SSID" 802-11-wireless.powersave 2

# Disable IPv6 on WiFi connection (MT7921e IPv6 breaks IPv4)
nmcli connection modify "YOUR_SSID" \
  ipv6.method disabled \
  ipv6.ignore-auto-routes yes \
  ipv6.ignore-auto-dns yes

# System-wide PCIe ASPM off (kernel cmdline)
# Edit /etc/default/grub GRUB_CMDLINE_LINUX_DEFAULT:
# quiet splash pcie_aspm=off pcie_port_pm=off
sudo update-grub

# Per-driver ASPM off (persistent across kernel updates)
echo "options mt7921e disable_aspm=1" | sudo tee /etc/modprobe.d/mt7921e.conf

# Disable Bluetooth (shares antenna with MT7921e)
sudo systemctl disable --now bluetooth
rfkill block bluetooth
```

### 2. Verify Fixes Applied

```bash
# Check WiFi locked to 5 GHz
nmcli -f in-use,ssid,bssid,chan,freq,signal,rate dev wifi list | grep IN-USE

# Check kernel params
cat /proc/cmdline | grep -E 'pcie_aspm|pcie_port_pm'

# Check module param
cat /sys/module/mt7921e/parameters/disable_aspm  # Should be Y

# Check Bluetooth blocked
rfkill list | grep -E 'Bluetooth.*Soft blocked: yes'
```

---

## Swarm Configuration (Optimized for MT7921e)

**File:** `~/Desktop/Projects/ENI_Swarm_NEW/config/swarm_config.json`

```json
{
  "concurrency": {
    "max_concurrent_children": 4,
    "launch_delay_seconds": 15,
    "max_hermes_processes": 4,
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
    "memory_limit_per_builder_gb": 2,
    "task_timeout_seconds": 600
  },
  "rate_limiting": {
    "max_api_calls_per_minute": 60,
    "max_model_switches_per_hour": 10,
    "cooldown_after_rate_limit_seconds": 30
  }
}
```

**Key settings rationale:**
- `max_concurrent_children: 4` — Not 6. MT7921e saturates at ~4 concurrent outbound TLS connections.
- `launch_delay_seconds: 15` — Staggered startup prevents connection storm.
- `max_api_calls_per_minute: 60` — Global cap across all free providers.
- `stage_size: 4` + `stage_delay_seconds: 15` — Fleet launches in waves.

---

## Operational Procedures

### Start Swarm (Standard)

```bash
cd ~/Desktop/Projects/ENI_Swarm_NEW
eni-swarm start --project DEMIURGE --workers 4
```

**Expected output:**
```
[MASTER] ENI Master Driver v5.0 starting (on-demand, max_workers=4)
[MASTER] Model: free-router @ free-router
[MASTER] Loaded 60 logical minis...
[CYCLE N] Dispatching XX tasks (max 4 concurrent)...
```

### Start Swarm (Background, Long-Running)

```bash
cd ~/Desktop/Projects/ENI_Swarm_NEW
nohup eni-swarm start --project DEMIURGE --workers 4 > ~/eni_swarm.log 2>&1 &
# Or use systemd user service (see below)
```

### Monitor Live

```bash
# Real-time heartbeat (TUI)
eni-swarm heartbeat

# Tail master log
eni-swarm logs --follow

# Full status snapshot
eni-swarm status
```

### Stop Swarm

```bash
eni-swarm stop
# Verifies: no master driver, no hermes children, no compression workers
```

### Check WiFi Health During Operation

```bash
# Quick one-liner
nmcli device show wlp4s0 | grep STATE && nmcli -f in-use,ssid,bssid,chan,freq,signal,rate dev wifi list | grep IN-USE

# Should show: STATE=100 (connected), 5 GHz channel, rate > 1000 Mbit/s
```

---

## Systemd Service (Persistent Background)

Create `~/.config/systemd/user/eni-swarm.service`:

```ini
[Unit]
Description=ENI Swarm Master Driver
After=network-online.target free-router.service
Wants=network-online.target free-router.service

[Service]
Type=simple
WorkingDirectory=/home/hunter/Desktop/Projects/ENI_Swarm_NEW
ExecStart=/home/hunter/.local/bin/eni-swarm start --project DEMIURGE --workers 4
Restart=on-failure
RestartSec=30
Environment=HOME=/home/hunter

[Install]
WantedBy=default.target
```

Enable:
```bash
systemctl --user daemon-reload
systemctl --user enable --now eni-swarm.service
systemctl --user status eni-swarm.service
journalctl --user -u eni-swarm -f
```

---

## Task Management

### List All Tasks

```bash
eni-swarm task list
# Shows: BUILDER_01 through BUILDER_50, HEARTBEAT, PRODUCT_LEAD, ENI_SELF_1-8
```

### Add Custom Task

```bash
eni-swarm task add \
  --name CUSTOM_TASK \
  --title "Custom Build" \
  --workdir ~/Desktop/Projects/ENI_Swarm_NEW \
  --model free-router \
  --provider free-router \
  --task "Your prompt here..."
```

### View Builder Logs

```bash
# Specific builder
eni-swarm logs --mini BUILDER_01

# All builders (follow)
eni-swarm logs --follow
```

---

## Model/Provider Management

### Current Model (Hot-Reloaded from ~/.hermes/config.yaml)

```bash
eni-swarm config show
# Shows: CURRENT_MODEL, CURRENT_PROVIDER, max_workers, interval
```

### Force Model Change

```bash
# Edit Hermes config
hermes config set model.default "free-router"
hermes config set model.provider "free-router"

# Master driver auto-detects within 5s (config watcher thread)
```

### Free Router Health

```bash
curl -s http://localhost:8920/health
curl -s http://localhost:8920/v1/models | jq '.data[] | select(.free==true) | .id'
```

---

## Dashboard

```bash
# Web dashboard on :8420
eni-swarm dashboard
# Opens browser to http://localhost:8420
```

---

## Troubleshooting

### WiFi Drops During Swarm

| Symptom | Check | Fix |
|---------|-------|-----|
| Disconnects under load | `nmcli device show wlp4s0 \| grep STATE` | Verify 5 GHz lock, ASPM off, BT disabled |
| Roaming to 2.4 GHz | `nmcli -f ssid,bssid,chan dev wifi list` | Re-apply BSSID lock |
| IPv4 works, ping fails | `ping 1.1.1.1` vs `ping -6 1.1.1.1` | Disable IPv6 on connection |
| Firmware crashes in dmesg | `dmesg -T \| grep mt7921e` | Update linux-firmware from kernel.org |

### Swarm Not Starting

```bash
# Check free-router
systemctl --user status free-router
curl -s http://localhost:8920/health

# Check Hermes CLI
hermes --version
hermes config show

# Check config syntax
cat ~/Desktop/Projects/ENI_Swarm_NEW/config/swarm_config.json | python3 -m json.tool
```

### Builders Stuck/Stalled

```bash
# Check status files
ls -la ~/Desktop/Projects/ENI_Swarm_NEW/tasks/status/STATUS_*.md

# Master stall detection: 30 min = STALLED, 2 hr = CRITICAL
# Force restart stuck mini:
eni-swarm stop
# Then restart swarm
```

### Rate Limited (All Free Providers Exhausted)

```bash
# Check router status
curl -s http://localhost:8920/status | jq '.providers'

# Wait for cooldown (60s default) or add OpenRouter keys
# OPENROUTER_API_KEY_2, _3, etc. in ~/.hermes/.env
```

---

## Verification Checklist (Post-Reboot) + Fleet Monitor Parser Gotchas

The fleet monitor reference library expanded with three new reference files covering real-world parser gaps discovered during Aug 2026 fleet monitoring runs:

- **Shebang + python3 pitfall** (`references/fleet-monitor-python3-shebang.md`) — monitor_fleet.py had no shebang; `python` not on this system, only `python3`. Cron execution silently fails without `#!/usr/bin/env python3`.
- **IDLE→DONE misclassification** (`references/idle-state-parser-gap.md`) — Builders reporting `[IDLE]` state get mapped to `[DONE]` because the else-clause defaults to DONE. IDLE capacity is invisible in the ledger.
- **Partial-liveness signal** (`references/partial-staleness-live-signal.md`) — One fresh STATUS mtime among a sea of stale = at least one builder is still running. Diagnostic steps to find the live builder and check its FIFO.

Run this after every reboot to confirm 100% operational:

```bash
#!/bin/bash
# ~/Desktop/Projects/ENI_Swarm_NEW/verify_swarm_ready.sh

echo "=== KERNEL PARAMS ==="
cat /proc/cmdline | grep -E 'pcie_aspm|pcie_port_pm' && echo "✅" || echo "❌"

echo "=== MT7921E MODULE ==="
cat /sys/module/mt7921e/parameters/disable_aspm | grep -q Y && echo "✅ disable_aspm=Y" || echo "❌"

echo "=== BLUETOOTH ==="
rfkill list | grep -q "Bluetooth.*Soft blocked: yes" && echo "✅ BT blocked" || echo "❌"

echo "=== WIFI CONNECTION ==="
nmcli device show wlp4s0 | grep -q "STATE:.*100 (connected)" && echo "✅ Connected" || echo "❌"
nmcli -f in-use,ssid,bssid,chan,freq,signal,rate dev wifi list | grep -q "IN-USE.*5[0-9][0-9][0-9] MHz" && echo "✅ 5 GHz locked" || echo "❌"

echo "=== FREE ROUTER ==="
curl -sf http://localhost:8920/health >/dev/null && echo "✅ Router up" || echo "❌"

echo "=== SWARM CONFIG ==="
python3 -c "
import json
d=json.load(open('/home/hunter/Desktop/Projects/ENI_Swarm_NEW/config/swarm_config.json'))
assert d['concurrency']['max_concurrent_children']==4
assert d['concurrency']['launch_delay_seconds']==15
assert d['fleet_optimization']['stage_size']==4
assert d['rate_limiting']['max_api_calls_per_minute']==60
print('✅ Config optimized for MT7921e')
"
```

---

## Advanced: Impossible Swarm Upgrades (v2.0+)

The following upgrades transform the standard 60-mini swarm into an **Impossible Swarm** with genetic evolution, distributed gossip, semantic compression, and real-time streaming.

### 1. Genetic Evolution Integration

**Module:** `core/evolution.py` → `GeneticAlgorithm`, `EvolutionarySwarmIntegration`

```python
from core.evolution import GeneticAlgorithm, EvolutionarySwarmIntegration

# Initialize evolution engine
ga = GeneticAlgorithm(population_size=20, test_data=test_data)
ga.initialize_population()
await ga.run(generations=10)

# Integrate with swarm
evo_integration = EvolutionarySwarmIntegration(swarm)
await evo_integration.start_evolution(generations=10)
```

**Key features:**
- Compressor genomes with mutable genes (algorithm, parameters, pipeline stages)
- Fitness evaluation on real test data (ratio × speed)
- Hall of fame preserves best genomes
- Auto-deploys evolved compressors to swarm workers

### 2. Distributed Multi-Node Swarm (Gossip Protocol)

**Module:** `core/distributed.py` → `GossipProtocol`, `DistributedSwarm`, `LeaderElection`

```python
from core.distributed import DistributedSwarm

swarm = DistributedSwarm(
    node_id="eni-node-01",
    address="0.0.0.0:8930",
    peer_addresses=["192.168.1.10:8930", "192.168.1.11:8930"]
)
await swarm.start()

# Submit distributed tasks
task_id = await swarm.submit_task({"type": "compress", "data": "..."})

# Work stealing across nodes
# Leader election for coordination
```

**Gossip parameters:**
- `fanout=3` — each node gossips to 3 random peers
- `interval=1.0s` — gossip every second
- `suspicion_threshold=5.0s` — mark suspect, confirm dead at 10s

### 3. Semantic/Neural Compression

**Module:** `core/semantic.py` → `SemanticCompressor`, `SemanticEncoder`

```python
from core.semantic import SemanticCompressor, DomainType

compressor = SemanticCompressor(
    similarity_threshold=0.92,  # Deduplication threshold
    meaning_threshold=0.85      # Meaning preservation
)

result = compressor.compress(text, domain=DomainType.CODE)
# Auto-detects domain: CODE, LOGS, JSON, CHAT, SQL
# Semantic deduplication via embedding similarity
# Meaning verification via embedding similarity
```

### 4. Real-Time Streaming Compression

**Module:** `core/streaming.py` → `StreamProcessor`, `BackpressureController`

```python
from core.streaming import StreamProcessor, StreamPriority

processor = StreamProcessor()
await processor.start()

stream_id = await processor.multi_stream.create_stream(
    priority=StreamPriority.HIGH
)

async for chunk in data_generator():
    result = await processor.multi_stream.process_chunk(stream_id, chunk)
    if result:
        yield result

# Flush
final = await processor.multi_stream.process_chunk(stream_id, b"", is_final=True)
```

**Features:**
- Sliding window compression (LZ4/ZSTD/ZLIB)
- Backpressure with high/low watermarks
- Multi-stream with priority queue
- Checkpointing for fault tolerance
- Real-time metrics (throughput, latency, ratio)

### 5. Unified Impossible Integration

**Module:** `core/impossible.py` → `ImpossibleCompression`, `ImpossibleMode`

```python
from core.impossible import ImpossibleCompression, ImpossibleConfig, ImpossibleMode

config = ImpossibleConfig(
    mode=ImpossibleMode.IMPOSSIBLE_PLUS,
    use_evolution=True,
    use_semantic=True,
    use_streaming=False,
    use_distributed=False,
)

async with ImpossibleCompression(config) as ic:
    # Single compression
    result = await ic.compress(data, ImpossibleMode.IMPOSSIBLE_PLUS)
    
    # Streaming compression
    async for chunk in ic.compress(data_generator, ImpossibleMode.STREAMING):
        yield chunk
    
    # Round-trip verification
    verified = await ic.verify_roundtrip(data, ImpossibleMode.IMPOSSIBLE_PLUS)
```

**Impossible Modes:**
| Mode | Pipeline | Carrier | Round-trip |
|------|----------|---------|------------|
| FAST | LZ4 HC | — | — |
| BALANCED | ZSTD-19 | — | — |
| MAXIMUM | PAQ8PXD | — | — |
| IMPOSSIBLE | Wenyan→PAQ8→PXPipe→Glyph | PNG | ✅ |
| SEMANTIC | Embeddings + dedup | — | — |
| EVOLUTIONARY | Genetically evolved | — | — |
| IMPOSSIBLE_PLUS | Everything combined | PNG | ✅ |

### 6. Impossible Swarm Driver

**Module:** `core/swarm_driver.py` → `ImpossibleSwarm`, `ImpossibleSwarmWorker`

```python
from core.swarm_driver import ImpossibleSwarm, CompressionMode

swarm = ImpossibleSwarm(num_workers=24)
await swarm.start()

# Specialized workers:
# - 4 PAQ8 (MAXIMUM)
# - 3 ZSTD (BALANCED)  
# - 3 LZ4 (FAST)
# - 2 Brotli (BALANCED)
# - 2 LLM-optimized
# - 2 Code-aware
# - 2 Wenyan
# - 1 PXPipe steganography
# - 1 Glyph cache
# - 2 Adaptive
# - 2 IMPOSSIBLE

task_ids = await swarm.submit_batch(items, CompressionMode.IMPOSSIBLE)
results = [await swarm.get_result(tid) for tid in task_ids]
```

**Self-healing:**
- Distributor loop routes tasks to idle workers
- Healer loop restarts stuck workers (>2min no heartbeat)
- Dead worker replacement (>5min no heartbeat)
- Error rate monitoring (>50% failure = restart)

---

## Updated Files Created by This Skill

- `references/mt7921e-swarm-fixes.md` — WiFi fix procedure
- `references/impossible-swarm-upgrades.md` — This section (IMPOSSIBLE swarm patterns)
- `references/fleet-staleness-interpretation.md` — dormant-vs-live mtime analysis + alert-noise discrimination
- `references/stale-cron-job-remediation.md` — Stale builder cron job detection, tracing (jobs.json), disable, and output cleanup
- `references/fleet-monitor-fresh-mtime-parking.md` — trap: single fresh STATUS-file mtime can be an IDLE parking re-verify, not a wake-up; read content not just mtime
- `references/fleet-monitor-metadata-gap.md` — ghost-state IN-PROGRESS builders with zero metadata (verified/blocker/next=unknown); sub-swarm health indicators in builder headers; work-redistribution signals (catch-up builders); non-environmental BLOCKED reasons (awaiting PRODUCT_LEAD dispatch)
- `references/fleet-monitor-diagnostic-one-liners.md` — no-dump one-liner diagnostics
- `references/fleet-liveness-cross-check.md` — process/FIFO/mtime triangulation to distinguish live fleet from stale STATUS artifacts
- `references/fleet-state-classification-gap.md` — ACTIVE/BUILDING/IDLE headers misclassified as DONE by monitor_fleet.py; how to detect and work around
- `scripts/verify_swarm_ready.sh` — Post-reboot verification
- `scripts/verify_impossible_swarm.sh` — Impossible swarm verification
- `templates/eni-swarm.service` — Systemd unit template
- `templates/impossible-swarm-config.json` — Impossible swarm config