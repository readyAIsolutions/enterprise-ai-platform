# Swarm Turbocharger — Full Architecture

## Problem

MT7921e WiFi firmware crashes under AI swarm concurrency. The bottleneck is NOT bandwidth (270 Mbps rx is plenty) or TCP connections — it's PACKET BURSTS saturating the firmware buffer.

## Solution: 5-Layer Optimization

```
LAYER 5: Signal-Adaptive Auto-Tuning
  Monitors WiFi signal dBm every 1.5s, adjusts concurrency in real-time.
  Aggressive tiers: -48=80, -52=70, -56=60, -60=50, -65=40, -70=25, -75=15
  
LAYER 4: Delta-Based Retry Tracking
  Reads "iw dev wlp4s0 station dump" for tx retries/failures.
  Tracks DELTA (new - previous), not absolute count (which is always high on old interfaces).
  Penalty triggers at >50 retries per 1.5s poll interval → halves concurrency.

LAYER 3: Token-Bucket Packet Pacing
  Rate limiter prevents burst overflow. 0.7 req/sec per concurrent slot sustained.
  4x burst capacity. Example at 50 concurrent: 35 req/s sustained, 140 burst.
  Unlike semaphore (concurrency only), this limits REQUESTS PER SECOND.

LAYER 2: Connection Multiplexing
  urllib3 PoolManager with 60 pools, 120 keepalive connections.
  HTTP/1.1 keepalive reuses TCP connections (no new handshake per request).
  Connection pre-warming on startup.

LAYER 1: Kernel TCP Tuning
  net.core.rmem_max/wmem_max = 16MB
  net.core.netdev_max_backlog = 5000
  net.ipv4.tcp_slow_start_after_idle = 0
  net.ipv4.tcp_fastopen = 3
```

## Files

- Script: `~/.hermes/scripts/swarm_turbocharger.py` (531 lines)
- Systemd: `~/.config/systemd/user/swarm-turbocharger.service`
- Enterprise module: `enterprise/modules/swarm_network/` (23/23 tests)
- Enterprise skill: `claude-code-superior` (covers turbocharger usage)

## Commands

```bash
# Start (manual)
python3 ~/.hermes/scripts/swarm_turbocharger.py --port 8922

# Auto-start on boot
systemctl --user enable swarm-turbocharger
systemctl --user start swarm-turbocharger

# Health check
curl http://localhost:8922/health
# → {"status":"ok","proxy":"swarm_turbocharger","concurrency":50,"signal":-59}

# Full status
curl http://localhost:8922/turbo/status

# Configure Hermes
hermes config set delegation.max_concurrent_children 50
```

## Concurrency Tiers

| Signal (dBm) | Agents | Sustained (req/s) | Burst |
|-------------|--------|-------------------|-------|
| > -48 | 80 | 56 | 224 |
| > -52 | 70 | 49 | 196 |
| > -56 | 60 | 42 | 168 |
| > -60 | 50 | 35 | 140 |
| > -65 | 40 | 28 | 112 |
| > -70 | 25 | 17 | 68 |
| > -75 | 15 | 10 | 40 |

## Enterprise Integration

```python
from enterprise.modules.swarm_network import SwarmNetworkBridge
import asyncio

bridge = SwarmNetworkBridge()
asyncio.run(bridge.initialize())
health = asyncio.run(bridge.health_check())
# health.max_concurrency → 50
# health.turbocharger_running → True
# health.recommendations → []

# Turbo mode: 25% above conservative limits
turbo = bridge.enable_turbo()  # → 62 at -60 dBm
```

## History

- v1.0 (Swarm WiFi Optimizer): Basic connection pooling, 12 concurrent max
- v2.0 (Turbocharger): 5-layer optimization, 40→80 concurrent, kernel tuning, token bucket, delta retry tracking