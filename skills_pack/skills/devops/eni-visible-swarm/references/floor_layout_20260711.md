# Floor Layout — 2026-07-11 (LO's clarified spec)

## Monitor canvas (xrandr --listmonitors, verified)
- LEFT   DisplayPort-2  1920x1080  +0+0
- MIDDLE DisplayPort-0  2560x1080  +1920+0   (primary, ultrawide)
- RIGHT  DisplayPort-1  1920x1080  +4480+0
- BOTTOM HDMI-A-0       1920x1080  +2274+1080
Total ~6430x2160, one 4-monitor canvas (NOT 4 X11 workspaces for this layout).

## LO's spec (verbatim intent)
- Middle monitor = heartbeat + master as ONE full-screen command bar, ABOVE the builders.
- 4 builders per side screen, 1 program per screen.
- Across all reachable workstations (only WS1 reachable on this box; others need discovery/VPN).

## Working painter shape (paint_LO_v4.sh)
- MIDDLE: `xfce4-terminal --disable-server --tab -T "CMD::heart" -e "bash run_HEART.sh" --tab -T "CMD::master" -e "bash run_MASTER.sh" &` then `wmctrl -r "CMD::heart" -e 0,1920,0,2560,1080`
- Each builder window = 2 tabs (tab1 `ENI<n>::master` = `hermes chat --yolo -m <slug> --provider openrouter`, tab2 `ENI<n>::build` = `bash run_ENI<n>.sh`).
- Side 2x2 grid constants (measured even): term ~950x510, TMARGIN=10/15, steps 960/520.
  LEFT base (0,0):      (10,15),(970,15),(10,535),(970,535)
  RIGHT base (4510,0):  (4520,15),(5480,15),(4520,535),(5480,535)
  BOTTOM base (2274,1080): (2284,1095),(3234,1095),(2284,1620),(3234,1620)
- Stagger: `sleep 2.5` between each window launch (kills the 429 stampede).
- Launch DETACHED (terminal background=true OR execute_code `subprocess.Popen(...,start_new_session=True)`) — LO's rapid messages SIGINT a foreground paint.

## Tradeoff (must tell LO)
"heartbeat full-screen middle" + "4 builders/screen, 1 program/screen" + 16 minis = 3 side screens for 4 programs. Resolution chosen this session: caveman_stack (ENI13–16) SHARES the BOTTOM screen (8 windows). Alt: heartbeat large-left + caveman 2x2 right-half on middle (keeps exactly 4/screen). LO picked full-screen heartbeat.

## LUMEN LEASH (SAFETY — non-negotiable)
Minis building Lumen (LEFT, ENI1–4) are CODE-ONLY. NEVER launch `python -m lumen`, never open the PyQt6 app, never let it grab the X display / spawn WebGL on the AMD RX5700XT box. A prior Lumen launch forced multiple PC reboots. Verify: `pgrep -af [l]umen` must return nothing after repaint.

## v3 baseline (verified-painted, 19 windows) for fallback
If the v4 full-screen spec is rejected, the v3 layout painted + verified: MIDDLE = 1 window (heartbeat tab + master tab) at (1930,15,2540,175) ABOVE 4 builders at (1930,205)/(3210,205)/(1930,630)/(3210,630) w1268 h352; LEFT/RIGHT/BOTTOM each 4 builders 2x2 (950x510); 16 builder windows + 1 command bar = 19 windows, 19 proxies, lumen absent.

## Verify after paint (separate call, after LO stops sending)
- `wmctrl -l -G | grep -E 'CMD::|ENI[0-9]+::'` → expect 17 windows (1 cmd bar + 16 builders).
- `pgrep -af eni_agent_term | wc -l` → 16+ (one per builder; cmd-bar heartbeat/master also proxied).
- `pgrep -af [l]umen` → empty (leash holds).
- `free -m` / `nproc` → box has 30GB RAM / 24 CPUs, safe for 17 windows.
