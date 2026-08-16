# Swarm WiFi Optimizer

Local HTTP proxy that enables 12–20 concurrent Hermes subagents on MT7921e
without WiFi drops by pooling TCP connections and adaptively throttling
based on real-time signal strength.

## Architecture

```
Subagent 1 ──┐
Subagent 2 ──┤               ┌──────────────────┐
Subagent 3 ──┼──HTTP────────→│ Swarm WiFi       │──urllib3 pool──→ Internet
Subagent 4 ──┤               │ Optimizer :8921   │  (50 keepalive)
   ...    ──┘               │                   │
                             │ • Signal monitor  │
                             │ • Request coalescer│
                             │ • Adaptive semaphore│
                             │ • Circuit breaker │
                             └──────────────────┘
```

## Signal → Concurrency Mapping

| Signal (dBm) | Max Concurrent | Quality |
|-------------|----------------|---------|
| > -55 | 20 | Excellent |
| -55 to -62 | 12 | Good |
| -62 to -68 | 8 | Decent |
| -68 to -75 | 5 | Weak |
| -75 to -85 | 2 | Very Weak |
| < -85 | 1 | Barely Connected |

## Key Mechanisms

1. **Connection Pool**: urllib3.PoolManager(num_pools=20, maxsize=50) — all
   subagents share one pool instead of each opening separate TCP connections.
   HTTP keepalive ensures connections are reused.

2. **Request Coalescing**: Identical GET requests within 500ms window are merged
   into one upstream call. Results are fanned out to all waiting subagents.
   Dramatically reduces upstream connections when multiple subagents fetch
   the same resource.

3. **Adaptive Throttling**: A semaphore whose max count adjusts every 2 seconds
   based on WiFi signal strength read from `iw dev wlp4s0 link`.

4. **Circuit Breaker**: Detects deauth events in dmesg. Blocks all requests
   for 30 seconds after deauth, then slowly recovers.

5. **Priority Queuing**: Critical requests (health checks) jump the line.

## Verified Configuration (2026-08-01)

- WiFi adapter: MT7921e (MediaTek MT7922)
- Signal: -60 dBm → 12 concurrent safe
- Hermes delegation config: `max_concurrent_children: 4` (without proxy)
- With proxy: can safely run 8–12 concurrent subagents
- Previous drops occurred at 6+ concurrent without proxy

## Start / Stop

```bash
# Start
python3 ~/.hermes/scripts/swarm_wifi_optimizer.py --port 8921 &

# Health check
curl http://localhost:8921/health
# → {"status":"ok","signal_dbm":-60,"concurrency_limit":12,"recovering":false}

# Full status
curl http://localhost:8921/status

# Kill
pkill -f swarm_wifi_optimizer
```

## Hermes Integration

To route all Hermes delegation traffic through the optimizer:

```bash
hermes config set delegation.proxy_url "http://127.0.0.1:8921"
```

Subagents will then use the proxy for all API calls, sharing the connection pool.

## Known Issues

- SyntaxError on `global INTERFACE` before assignment — fixed by moving
  `global INTERFACE` to top of `main()` before `argparse` references it.
- The proxy is HTTP-only (no TLS) — only use on localhost.
- Not a full forward proxy — only handles chat completions, models, and
  generic GET/POST via `/proxy` endpoint.