# Onion "won't load / hangs forever" — diagnostic recipes

## Step-by-step (run in order)

1. SocksPort + web up?
   ```
   (exec 3<>/dev/tcp/127.0.0.1/9050) 2>/dev/null && echo UP || echo DOWN   # tor
   (exec 3<>/dev/tcp/127.0.0.1/8898) 2>/dev/null && echo UP || echo DOWN   # web
   ```
2. Web serves locally (proves content behind tor)?
   ```
   curl -s http://127.0.0.1:8898/ -o /dev/null -w "HTTP:%{http_code}\n"
   ```
3. End-to-end through tor (localhost proof — if this fails, HS itself is broken):
   ```
   curl -s --socks5-hostname 127.0.0.1:9050 http://wohw4tzhiaicitpwj7lx5sb754yoocofekwwis4ixbqudy2bas5pepqd.onion/ -o /dev/null -w "HTTP:%{http_code}\n"
   ```
4. Read the notice log for the smoking gun:
   ```
   grep -iE "no exit nodes|no running bridges|published|Bootstrapped 100" ~/Desktop/ENI\ Swarm/tor-data/notice.log | tail
   ```

## Interpretations
- `no exit nodes` OR `No running bridges` → egress firewall blocks Tor ORPort AND
  bridge IPs. Config is correct; the box cannot reach the Tor relay mesh.
  FIX PATHS (config alone cannot):
  - meek bridge (domain-fronting on 443 through a CDN) — needs meek-client binary
  - external SOCKS/HTTP proxy the egress allows → `Socks5Proxy ip:port` in torrc
  - host the HS on a VPS with open egress (same key)
- `Bootstrapped 100% (done)` + ports up + step-3 returns 200 → it IS reachable;
  the Android client issue is client-side (old TB, clock skew, cached descriptor).
  Tell LO to refresh / use a current Tor Browser.

## Reset recipe (use ONLY when consensus is stale, not for "no exit nodes")
```
rm -f ~/Desktop/ENI\ Swarm/tor-data/cached-microdesc-consensus \
      ~/Desktop/ENI\ Swarm/tor-data/cached-microdescs \
      ~/Desktop/ENI\ Swarm/tor-data/cached-microdescs.new \
      ~/Desktop/ENI\ Swarm/tor-data/cached-certs \
      ~/Desktop/ENI\ Swarm/tor-data/lock
# then kill watchdog's tor pid; watchdog restarts with fresh consensus
```

## Stray-binary check (before trusting any downloaded transport binary)
```
ls -l /path/to/obfs4proxy        # must be > 0 bytes
/path/to/obfs4proxy --version    # must print a version, not error
```
On this box obfs4proxy was unavailable: squashfs copy was 0-byte, no Go,
GitHub/dist downloads 404. Default to the proxy or VPS route.
