#!/usr/bin/env python3
"""
floor_setup.py — ONE-SHOT paint of LO's 72-window build floor (4 workspaces,
4 terms/screen on ALL 4 screens, one project per workspace, heartbeat+master
overlay on the middle). No global re-paint watchdog (that's what crashed the box).
Self-heal lives ONLY in each builder's own while-true loop. Window capture is by
ID-diff (xfce4-terminal --title does NOT stick on this box, so title-based dedup
would relaunch forever). KILL-ONLY memory sentinel prevents OOM.

Usage:
  python3 floor_setup.py            # generate + launch detached
  python3 floor_setup.py --no-launch# just (re)generate scripts, don't paint
Verify: `wmctrl -l` for windows; /tmp/eni_logs/<NAME>.log for live REPLs.

LAYOUT (LO's exact spec, 2026-07-11):
  WS1 middle=HEARTBEAT+MASTER ; WS2/3/4 middle=HEARTBEAT only (master WS1-only)
  Each workspace: 4 screens x 4 terms (2x2) = 16 builders + 2 overlay = 18 windows
  WS1=STOCKBOT(demiurge_scaffold)  WS2=DEMIURGE3D  WS3=DEMIURGEFX  WS4=LUMEN(leashed)
  LUMEN is CODE-ONLY: never launch `python -m lumen` GUI.
"""
import os, glob

TAB = "/tmp/eni_tabs"
PAR = "/tmp/eni_parallel"
os.makedirs(TAB, exist_ok=True)
os.makedirs(PAR, exist_ok=True)

# proxy flag is --ctl (NOT --fifo) on this box — verify: python3 ~/.local/bin/eni_agent_term.py --help
PROXY = "/home/hunter/.local/bin/eni_agent_term.py"
LIVE = ["tencent/hy3:free", "qwen/qwen3-coder:free", "meta-llama/llama-3.3-70b-instruct:free"]

PROJ = [
    ("STOCKBOT",   "SB",  0, "/home/hunter/Commander/demiurge_scaffold"),
    ("DEMIURGE3D", "D3D", 1, "/home/hunter/Desktop/demiurge-3d"),
    ("DEMIURGEFX", "FX",  2, "/home/hunter/Commander/demiurge_scaffold"),
    ("LUMEN",      "LM",  3, "/home/hunter/Desktop/apps/lumen"),
]
SCREENS = {
    "left":   (0,    0,    1920, 1080),
    "right":  (4480, 0,    1920, 1080),
    "bottom": (2274, 1080, 1920, 1080),
    "mid":    (1920, 0,    2560, 1080),
}
GAP = 6

def cell_rect(screen, slot):
    sx, sy, sw, sh = SCREENS[screen]
    cw = (sw - 3 * GAP) // 2
    ch = (sh - 3 * GAP) // 2
    col = slot % 2
    row = slot // 2
    return sx + GAP + col * (cw + GAP), sy + GAP + row * (ch + GAP), cw, ch

BRIEFS = {
    "FX": ("FOREX trading-bot builder for the DEMIURGE FTMO forex/stock bot "
           "(broker-free; deploy gate = purged-CV AUC>=0.55 AND walk-forward OOS>=36mo/500trades "
           "AND fill-degradation>=0.70). Work in /home/hunter/Commander/demiurge_scaffold. "
           "ADD-ONLY modules only; never edit core backtest/walk_forward/purged_cv or config.py. "
           "Write STATUS_<NAME>.md with a PASS/FAIL board using real numbers, a what-adds-R list, and an UNVALIDATED section."),
    "D3D": ("3D-print builder for DEMIURGE-3D (separate from the forex bot) at "
            "/home/hunter/Desktop/demiurge-3d. Strengthen/extend its modules, run its tests "
            "(backend/tests cwd, project venv). ADD-ONLY. Write STATUS_<NAME>.md with a real PASS/FAIL board and what-adds-R list."),
    "LM": ("LUMEN builder at /home/hunter/Desktop/apps/lumen (PyQt6 WebGL wallpaper engine). "
           "CODE-ONLY: edit, fix, harden, run pytest/flake8/mypy/importlint. "
           "LEASH: NEVER run `python -m lumen`, never open the GUI, never grab the X display. "
           "App stays CLOSED. Write STATUS_<NAME>.md."),
    "SB": ("STOCK bot builder for /home/hunter/Commander/demiurge_scaffold (DEMIURGE stock/forex scaffold). "
           "Build/extend broker-free modules (ADD-ONLY; never edit core or config.py). Write STATUS_<NAME>.md "
           "with a PASS/FAIL board, what-adds-R list, and UNVALIDATED section."),
}

for ws, (pname, pref, ws_idx, wd) in enumerate(PROJ):
    for slot in range(16):
        name = "%s%02d" % (pref, slot + 1)
        brief = BRIEFS[pref]
        task = ("Project: %s (workspace %d/4). %s\nYour name: %s. Workdir: %s.\n"
                "Resume from your STATUS_%s.md if present; otherwise start the highest-value "
                "ADD-ONLY module. Self-test as you go. Keep building across interruptions.\n"
                % (pname, ws + 1, brief, name, wd, name))
        open("%s/task_%s.txt" % (PAR, name), "w").write(task)
        run = (
            "#!/usr/bin/env bash\n"
            "# %s builder — self-heal ONLY (no global repaint). LUMEN: code-only, never launch GUI.\n"
            "export DISPLAY=:0.0\n"
            "export PATH=\"$HOME/.local/bin:$HOME/bin:$PATH\"\n"
            "export HERMES_CTL_FIFO=/tmp/eni_ctl_%s\n"
            "mkdir -p /tmp/eni_logs\n"
            "pkill -9 -f \"eni_agent_term.py --name %s\" 2>/dev/null\n"
            "while [ \"$(free -m | awk '/Mem:/{print $7}')\" -lt 3000 ]; do sleep 15; done\n"
            "sleep $(( (RANDOM %% 50) + 3 ))   # one-time stagger so 64 chats don't fork at once\n"
            "while true; do\n"
            "  python3 %s --name %s --ctl /tmp/eni_ctl_%s --task %s/task_%s.txt --repl \"hermes chat --yolo -m %s --provider openrouter\" 2>&1 | tee -a /tmp/eni_logs/%s.log\n"
            "  sleep 3\n"
            "done\n"
            % (name, name, name, PROXY, name, name, PAR, name, LIVE[slot % 3], name)
        )
        open("%s/run_%s.sh" % (TAB, name), "w").write(run)
        os.chmod("%s/run_%s.sh" % (TAB, name), 0o755)
        st = (
            "#!/usr/bin/env bash\n"
            "while true; do clear; echo \"== %s status ==\"; "
            "tail -n 20 /home/hunter/Commander/demiurge_scaffold/STATUS_%s.md 2>/dev/null || "
            "tail -n 20 /home/hunter/Desktop/demiurge-3d/STATUS_%s.md 2>/dev/null || "
            "tail -n 20 /home/hunter/Desktop/apps/lumen/STATUS_%s.md 2>/dev/null; sleep 6; done\n"
            % (name, name, name, name)
        )
        open("%s/status_%s.sh" % (TAB, name), "w").write(st)
        os.chmod("%s/status_%s.sh" % (TAB, name), 0o755)

def heartbeat_script(ws, pname):
    return (
        "#!/usr/bin/env bash\n"
        "echo \"=== %s HEARTBEAT (WS%d) ===\"\n"
        "while true; do\n"
        "  alive=$(for p in $(pgrep -x xfce4-terminal); do grep -qa 'run_' /proc/$p/cmdline 2>/dev/null && echo x; done | wc -l)\n"
        "  recent=$(find /home/hunter/Commander/demiurge_scaffold /home/hunter/Desktop/demiurge-3d /home/hunter/Desktop/apps/lumen -name 'STATUS_*.md' -mmin -10 2>/dev/null | wc -l)\n"
        "  echo \"$(date +%%T) %s: windows=$alive recent_STATUS(10m)=$recent gate=BUILDING\"\n"
        "  sleep 10\n"
        "done\n" % (pname, ws + 1, pname)
    )

for ws, (pname, pref, ws_idx, wd) in enumerate(PROJ):
    open("%s/heart_%s.sh" % (TAB, pname), "w").write(heartbeat_script(ws, pname))
    os.chmod("%s/heart_%s.sh" % (TAB, pname), 0o755)
    if ws == 0:
        open("%s/master_WS1.sh" % TAB, "w").write(
            "#!/usr/bin/env bash\nexec hermes chat --yolo -m tencent/hy3:free --provider openrouter\n")
        os.chmod("%s/master_WS1.sh" % TAB, 0o755)

lines = ["#!/usr/bin/env bash",
         'export DISPLAY=:0.0; export PATH="$HOME/.local/bin:$HOME/bin:$PATH"',
         'TAB=/tmp/eni_tabs; PAR=/tmp/eni_parallel',
         'mkdir -p /tmp/eni_logs',
         'echo "[driver] start $(date +%T)"']
for ws, (pname, pref, ws_idx, wd) in enumerate(PROJ):
    lines.append('echo "[driver] WS%d %s"' % (ws + 1, pname))
    for slot in range(16):
        name = "%s%02d" % (pref, slot + 1)
        scr = {0: "left", 1: "right", 2: "bottom", 3: "mid"}[slot // 4]
        sslot = slot % 4
        x, y, w, h = cell_rect(scr, sslot)
        # ONE program per workspace: every screen (left/right/bottom/mid) of
        # WS<ws> belongs to this project, so ALL builders go to workspace `ws`.
        ws_for_win = ws
        mx = SCREENS["mid"][0]
        lines.append('  before=$(wmctrl -l 2>/dev/null | awk \'{print $1}\' | sort)')
        lines.append('  xfce4-terminal --disable-server -e "bash %s/run_%s.sh" --geometry 90x24+%d+%d </dev/null >/dev/null 2>&1 &' % (TAB, name, x, y))
        lines.append('  for i in $(seq 1 40); do after=$(wmctrl -l 2>/dev/null | awk \'{print $1}\' | sort); new=$(comm -13 <(echo "$before") <(echo "$after") | head -1); [ -n "$new" ] && break; sleep 0.3; done')
        lines.append('  [ -n "$new" ] && wmctrl -i -r "$new" -e 0,%d,%d,%d,%d && wmctrl -i -r "$new" -t %d' % (x, y, w, h, ws_for_win))
    # heartbeat overlay on this project's workspace (ID-diff capture + move)
    lines.append('  hb=$(wmctrl -l 2>/dev/null | awk \'{print $1}\' | sort); xfce4-terminal --disable-server -e "bash %s/heart_%s.sh" --geometry 120x8+%d+8 </dev/null >/dev/null 2>&1 &' % (TAB, pname, mx))
    lines.append('  for i in $(seq 1 30); do ha=$(wmctrl -l 2>/dev/null | awk \'{print $1}\' | sort); hn=$(comm -13 <(echo "$hb") <(echo "$ha") | head -1); [ -n "$hn" ] && break; sleep 0.3; done; [ -n "$hn" ] && wmctrl -i -r "$hn" -t %d' % (ws))
    if ws == 0:
        # master chat overlay (WS1 only) — also moved to WS1
        lines.append('  mb=$(wmctrl -l 2>/dev/null | awk \'{print $1}\' | sort); xfce4-terminal --disable-server -e "bash %s/master_WS1.sh" --geometry 120x20+%d+8 </dev/null >/dev/null 2>&1 &' % (TAB, mx + 980))
        lines.append('  for i in $(seq 1 30); do ma=$(wmctrl -l 2>/dev/null | awk \'{print $1}\' | sort); mn=$(comm -13 <(echo "$mb") <(echo "$ma") | head -1); [ -n "$mn" ] && break; sleep 0.3; done; [ -n "$mn" ] && wmctrl -i -r "$mn" -t 0')
    lines.append('  sleep 1')
lines.append('echo "[driver] DONE $(date +%T) windows=$(wmctrl -l 2>/dev/null | wc -l)"')
open("%s/driver.sh" % TAB, "w").write("\n".join(lines) + "\n")
os.chmod("%s/driver.sh" % TAB, 0o755)

sentinel = (
    "#!/usr/bin/env bash\n"
    "# KILL-ONLY OOM pressure valve. Never launches (cannot cause a runaway).\n"
    "LOG=/tmp/eni_mem_sentinel.log; echo $$ > /tmp/eni_mem_sentinel.pid\n"
    'echo "$(date +%T) sentinel start" >> "$LOG"\n'
    "while true; do\n"
    '  avail=$(free -m | awk \'/Mem:/{print $7}\')\n'
    '  if [ "$avail" -lt 1500 ]; then\n'
    "    victim=$(ps --no-headers -o pid,rss,args -e | grep 'hermes chat --yolo' | grep -v grep | sort -k2 -n | tail -1 | awk '{print $1}')\n"
    '    [ -n "$victim" ] && kill -TERM "$victim" 2>/dev/null && echo "$(date +%T) CRITICAL avail=${avail}MB killed biggest agent (memguard reparks it)" >> "$LOG"\n'
    "    sleep 5\n"
    "  else sleep 20; fi\n"
    "done\n"
)
open("%s/mem_sentinel.sh" % TAB, "w").write(sentinel)
os.chmod("%s/mem_sentinel.sh" % TAB, 0o755)

print("generated: 64 run + 64 status + 4 heart + 1 master + driver.sh + mem_sentinel.sh")
print("run count:", len(glob.glob("%s/run_*.sh" % TAB)))
