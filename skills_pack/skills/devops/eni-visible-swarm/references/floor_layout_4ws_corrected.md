# ENI 4-Workspace Floor Layout — CORRECTED (2026-07-11, LO definitive)

Supersedes the earlier "full-screen heartbeat" sketch in the old
`floor_layout_20260711.md`. This is the layout LO actually wants and that
`paint_4ws_programs.py` generates.

## Program → Workspace mapping (one program per WS)
- **WS1 (idx 0)** = STOCK bot (demiurge_scaffold) — ENI1–16 (preserve in-progress modules)
- **WS2 (idx 1)** = demiurge-3d — ENI17–32
- **WS3 (idx 2)** = demiurge/forex (demiurge_scaffold) — ENI33–48
- **WS4 (idx 3)** = lumen (LEASHED — code only, never launch the app) — ENI49–64

## Density
- 4 terms/screen in a 2×2 grid = 16 builders/workspace, 64 total.
- Lumen stays leashed: minis edit code + `pytest` only; NEVER `python -m lumen`,
  never open the PyQt6/WebGL app. After any repaint `pgrep -af [l]umen` must be empty.

## Screen slot geometry (absolute 6400×2160 canvas; `xrandr` origins)
- LEFT   DisplayPort-2  +0+0
- MIDDLE DisplayPort-0  +1920+0  (2560×1080)
- RIGHT  DisplayPort-1  +4480+0
- BOTTOM HDMI-A-0       +2274+1080

2×2 builder slots per screen (each ~918×466 except MIDDLE ~1244×400):
- left   : (30,98) (961,98) (30,612) (961,612)
- right  : (4510,98) (5441,98) (4510,612) (5441,612)
- bottom : (2304,1178) (3235,1178) (2304,1692) (3235,1692)
- mid    : (1920,245) (3200,245) (1920,655) (3200,655)

## Overlay windows (WS1 only, top strip of MIDDLE, OVER the grid — NOT covering)
- Heartbeat: `72x6+1920+8`  title `WS1::heart`  → runs `fleet_pulse.py` loop
- Master chat: `72x6+2880+8` title `WS1::master` → your single coordinator seat
- Each OTHER workspace's MIDDLE also gets its own small heartbeat `WSx::heart`.

## Builder windows
- SINGLE-TAB, title `ENI<n>::build` (NO master-chat tab — see the stampede pitfall).
- Proxy: `python3 ~/.local/bin/eni_agent_term.py --name ENI<n> --task ~/.cache/eni_parallel/task_ENI<n>.txt --repl "hermes chat --yolo -m $M --provider openrouter" --ctl /tmp/eni_ctl_ENI<n>`

## Pinning (launch-then-move, exact title)
`xfce4-terminal --disable-server --geometry <GEO> --title "ENI<n>::build" -e "bash /tmp/eni_tabs/run_ENI<n>.sh" </dev/null >/dev/null 2>&1 & disown`
then `WIN=$(wmctrl -l | awk -v t="ENI<n>::build" '$0 ~ t {print $1; exit}'); wmctrl -i -r "$WIN" -t <ws>`
EXACT-title match avoids ENI1/ENI10 substring collision.

## Pre-paint rule
The painter does NOT generate run-scripts. Generate them first:
`python3 paint_4ws_programs.py` writes `/tmp/eni_tabs/run_ENI*.sh` + `/tmp/paint_4ws_full.sh`.
Verify `ls /tmp/eni_tabs/run_ENI1.sh` before painting or the floor is empty.

## Reset-then-paint (one detached job so rapid user msgs can't SIGTERM it)
```
bash /tmp/reset_floor.sh && bash /tmp/paint_4ws_full.sh
```
reset_floor.sh: `pkill -f 'eni_agent_term[.]py'`; close windows titled
`ENI[0-9]+::` / `WS[0-9]+::heart` / `WS[0-9]+::master` via `wmctrl -c`;
`rm -f /tmp/eni_model_health /tmp/eni_model_ctr`.
