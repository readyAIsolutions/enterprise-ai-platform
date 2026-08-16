# Product-Swarm Pulse — live signal table (2026-07-11)

The product swarm = 4 lines built by `hermes chat -q` mini-builders:
STOCKBOT, DEMIURGE (forex bot), DEMIURGE3D, LUMEN.

## Live signals (what to read — NOT the stale files)
| Metric | Command |
|---|---|
| alive builder windows | `wmctrl -l | grep -E 'ENI:' | grep -vc HEARTBEAT` |
| alive builder processes | `pgrep -fc 'hermes chat -q'` (≈13/line → ~52) |
| STOCKBOT progress | newest mtime of `/home/hunter/Commander/demiurge_scaffold/STATUS_STOCKBOT*.md` |
| DEMIURGE(bot) progress | newest mtime of `/home/hunter/Commander/demiurge_scaffold/STATUS_DEMIURGE*.md` |
| DEMIURGE3D progress | newest mtime of `/home/hunter/Desktop/demiurge-3d/STATUS_DEMIURGE-3D*.md` |
| LUMEN progress | newest mtime of `/home/hunter/Desktop/apps/lumen/STATUS_*LUMEN*.md` |
| STALL | live process exists but project-root STATUS mtime > 10 min |

## STALE-FILE TRAP (do not get fooled)
`eni_swarm/STATUS_*_B*.md` (STATUS_STOCKBOT_B1.md … STATUS_LUMEN_B5.md) are written by an
OLD `eni_agent_term.py` product-swarm deploy. They go stale (~8h observed) while the fleet
is still running. Never use them as the liveness signal. Also: a bare sweep of ALL
`STATUS_*.md` on disk (the old `eni_heartbeat.py` mistake) counts hundreds of historical
files (ws0..ws3, w1..w99) and lies (e.g. `minis=149`, false `gate=GREEN`).

## Stall post-mortem (this session)
Pulse showed `win:49 live:48 | SB:464m DG:552m D3D:515m LM:504m | STALL SB DG D3D LM`.
48–52 `hermes chat -q` processes were ALIVE but every project-root STATUS was ~8h old →
fleet-wide stall: processes running but not writing progress. Window/process count alone
would have reported "healthy". The pulse must combine alive-count + STATUS-age to surface
this. Recovery = diagnose why builders froze (API 429 loop? dead REPL?) then restart.

## Launch
`DISPLAY=:0 xfce4-terminal --disable-server --title "ENI:HEARTBEAT_PULSE" -e "bash /home/hunter/Commander/eni_swarm/heartbeat.sh"`
Launch via `terminal(background=true)` — the terminal tool REJECTS foreground `&`/`setsid`/`nohup`.
Verify: `wmctrl -l | grep HEARTBEAT_PULSE`.
