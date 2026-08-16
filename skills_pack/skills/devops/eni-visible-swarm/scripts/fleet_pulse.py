#!/usr/bin/env python3
# =============================================================================
# fleet_pulse.py  --  LIVE-FLOOR ENI heartbeat  (one line, ~60s)
# -----------------------------------------------------------------------------
# Counts ONLY builder windows actually alive RIGHT NOW (xfce4-terminal windows
# titled MASTER:<PROJECT>_<N>), reads the freshest STATUS_<...>.md per project to
# gauge progress, and flags stalls (alive window but stale/blocked STATUS).
# Ignores the hundreds of historical STATUS_* files from old sweeps (ws0-ws3,
# w1-w99) that the older eni_heartbeat.py counted (it reported minis=149 and a
# FALSE gate=GREEN). This is the accurate on-monitor pulse.
#   [HH:MM:SS] ENI PULSE | windows=N  STOCKBOT:4 DEMIURGE3D:4 DEMIURGE:2 LUMEN:2 PL:1 | stalls: none | gate=RED
# Usage:  python3 fleet_pulse.py            # loop forever, 60s tick
#         python3 fleet_pulse.py --once     # one line, then exit (cron / testing)
# =============================================================================
import os, re, time, glob, sys

ENI_DIR = os.path.dirname(os.path.abspath(__file__))

# ---- 1. alive builder windows (ground truth = process list) ----------------
def alive_windows():
    # title looks like: MASTER:STOCKBOT_B1  /  MASTER:PL  /  MASTER:PRODUCT_LEAD
    out = {}
    with os.popen("ps -eo args 2>/dev/null") as f:
        for line in f:
            m = re.search(r"--title\s+MASTER:([A-Z0-9_]+)", line)
            if m:
                out[m.group(1)] = out.get(m.group(1), 0) + 1
    return out

# ---- 2. project progress from freshest STATUS per project ------------------
# Project key = strip trailing _B<n> / _w<...> / _ws<...> from STATUS filename.
PROJ_RE = re.compile(r"^STATUS_(.+?)_(?:B\d+|w\d+|ws\d+)?\.md$")
def project_of(fname):
    m = PROJ_RE.match(fname)
    if not m:
        return None
    return m.group(1)

def progress():
    now = time.time()
    best = {}  # project -> (mtime, state)
    for path in glob.glob(os.path.join(ENI_DIR, "STATUS_*.md")):
        fn = os.path.basename(path)
        proj = project_of(fn)
        if not proj:
            continue
        mt = os.path.getmtime(path)
        state = "?"
        try:
            with open(path) as fh:
                head = fh.read(400)
            sm = re.search(r"(?i)\b(STATUS|DONE|BLOCKED|STALLED|PROGRESS|PAUSED)\b", head)
            if sm:
                state = sm.group(1).upper()
        except Exception:
            pass
        if proj not in best or mt > best[proj][0]:
            best[proj] = (mt, state)
    return best, now

# ---- 3. assemble the line --------------------------------------------------
def tick():
    wins = alive_windows()
    best, now = progress()

    # normalise window titles -> project (strip _B<n>, map PL/PRODUCT_LEAD)
    def pkey(n):
        n = re.sub(r"_B\d+$", "", n)          # STOCKBOT_B1 -> STOCKBOT
        return "PL" if n in ("PL", "PRODUCT_LEAD") else n

    counts = {}
    for name, c in wins.items():
        k = pkey(name)
        counts[k] = counts.get(k, 0) + c

    order = ["STOCKBOT", "DEMIURGE3D", "DEMIURGE", "LUMEN", "PL"]
    proj_parts = []
    total_windows = 0
    for p in order:
        if p in counts:
            proj_parts.append(f"{p}:{counts[p]}")
            total_windows += counts[p]
    for p in sorted(counts):
        if p not in order:
            proj_parts.append(f"{p}:{counts[p]}")
            total_windows += counts[p]

    # stalls: project has alive window but freshest STATUS older than 10 min,
    # or freshest STATUS state is BLOCKED/STALLED/PAUSED.
    STALE_MIN = 10
    stalls = []
    for p, c in counts.items():
        if p == "PL":
            continue
        b = best.get(p)
        if not b:
            stalls.append(f"{p}(no STATUS)")
            continue
        mt, state = b
        age = int((now - mt) / 60)
        if state in ("BLOCKED", "STALLED", "PAUSED"):
            stalls.append(f"{p}={state}")
        elif age > STALE_MIN:
            stalls.append(f"{p}={age}m-stale")

    stall_str = " ".join(stalls) if stalls else "none"
    ts = time.strftime("%H:%M:%S")
    line = (f"[{ts}] ENI PULSE | windows={total_windows}  "
            f"{' '.join(proj_parts)} | stalls: {stall_str} | gate=RED")
    print(line, flush=True)

if __name__ == "__main__":
    if "--once" in sys.argv:
        tick()
    else:
        try:
            while True:
                t0 = time.time()
                tick()
                time.sleep(max(1, 60 - (time.time() - t0)))
        except KeyboardInterrupt:
            pass
