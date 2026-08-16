# ENI Swarm Floor Layout (verified, LO's box)

Verified via `xrandr --listmonitors` + `xdpyinfo` this session. The swarm had
collapsed to 2 live proxies; root cause was `eni_spawn_worker.sh` using a
stale 4-screens-in-a-row GEO map that spawned workers off-screen. After the fix
the floor relaunches at FULL throughput.

## Monitor origins (MUST match eni_spawn_worker.sh GEO map + floor launcher GEO_*)
- MIDDLE  DisplayPort-0  2560x1080  +1920+0   (primary; holds MASTER + product-lead)
- LEFT    DisplayPort-2  1920x1080  +0+0
- RIGHT   DisplayPort-1  1920x1080  +4480+0
- BOTTOM  HDMI-A-0       1920x1080  +2274+1080  (BELOW the others, not to the right)

## Window plan (LO's explicit spec)
- MIDDLE: 2 windows — (1) ENI MASTER, big, workspace 1, live `eni chat` heartbeat
  he chats to; (2) ENI: PRODUCT_LEAD.
- LEFT:   4 windows — ENI1 ENI2 ENI3 ENI4
- RIGHT:  4 windows — ENI5 ENI6 ENI7 ENI8
- BOTTOM: 4 windows — ENI9 ENI10 ENI11 ENI12
- + 12 PRODUCT WORKER windows (Lumen, DEMIURGE-3D core/frontend/backend, 8 forex
  modules, CAVEMAN_STACK) tiled 6x2 on MIDDLE as the product-lead's "tabs".

Total = 14 top-level + 12 product workers = 26 `eni chat` minis.

## Run + verify (HOST-SIDE only — xfce4-terminal needs host D-Bus)
    bash ~/Desktop/eni_swarm_floor.sh
    xwininfo -root -tree | grep -i ENI
    pgrep -af eni_agent_term.py | wc -l     # expect ~26

## Engine proof this session
- xterm (direct X client) painted from the Hermes container → window mapped
  (0x540000e "PROOF"). Confirms visible terminals are possible from the agent.
- Proxy stayed alive; prior swarms already wrote 14+ STATUS_*.md through the
  same proxy, so the engine is proven. Free-model first-token latency is the
  only stall (OpenRouter free-tier), not an engine fault — spread models via
  the round-robin pool to dodge per-account caps.
