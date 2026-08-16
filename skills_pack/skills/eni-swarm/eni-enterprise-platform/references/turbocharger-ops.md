# Swarm Turbocharger Operations

## Quick Status

```bash
curl http://localhost:8922/health
# → {"status":"ok","concurrency":50,"signal":-59}

# Full status
curl http://localhost:8922/turbo/status
```

## Aggressive Concurrency Tiers

| Signal (dBm) | Agents | Sustained req/s | Burst |
|-------------|--------|-----------------|-------|
| > -48 | 80 | 56 | 224 |
| > -52 | 70 | 49 | 196 |
| > -56 | 60 | 42 | 168 |
| > -60 | 50 | 35 | 140 |
| > -65 | 40 | 28 | 112 |
| > -70 | 25 | 17 | 70 |

## 5-Layer Optimization

1. **Kernel TCP tuning** — 16MB buffers, 5000 backlog, TFO, no slow-start-after-idle
2. **Token bucket pacing** — 0.7 req/sec per slot, 4x burst, prevents firmware buffer overflow
3. **Connection multiplexing** — 60 pools, 120 keepalive, HTTP/1.1 reuse
4. **Delta health tracking** — Tracks retry RATE (per 1.5s poll) not absolute count
5. **Signal-adaptive tiers** — Auto-scales concurrency based on iw dev wlp4s0 link signal

## Lifecycle Management

From the enterprise module:

```python
from enterprise.modules.swarm_network import SwarmNetworkBridge
import asyncio

bridge = SwarmNetworkBridge()
await bridge.initialize()     # Auto-starts turbocharger if not running
health = await bridge.health_check()

bridge.enable_turbo()         # +25% concurrency
bridge.disable_turbo()        # Back to standard
bridge.restart_turbocharger() # Kill + restart
await bridge.shutdown()       # Graceful stop
```

## Systemd

```bash
systemctl --user enable swarm-turbocharger  # Auto-start on boot
systemctl --user start swarm-turbocharger   # Manual start
systemctl --user status swarm-turbocharger  # Check status
journalctl --user -u swarm-turbocharger -f  # Follow logs
```

## Hermes Config

```bash
hermes config set delegation.max_concurrent_children 50
```

## Troubleshooting

### Port already in use
```bash
fuser -k 8922/tcp
sleep 2
systemctl --user restart swarm-turbocharger
```

### Turbocharger not starting
```bash
# Check script exists
ls ~/.hermes/scripts/swarm_turbocharger.py

# Run manually to see errors
python3 ~/.hermes/scripts/swarm_turbocharger.py --port 8922

# Verify imports
python3 -c "import urllib3; print('urllib3 OK')"
```

### Signal dropped, concurrency low
```bash
# Check actual signal
iw dev wlp4s0 link | grep signal

# The turbocharger auto-adapts. If signal is -70 dBm, 25 concurrent is correct.
# Move closer to AP or use Ethernet for higher concurrency.
```