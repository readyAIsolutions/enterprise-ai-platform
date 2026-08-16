#!/usr/bin/env python3
"""
ENI swarm HEARTBEAT - the live pulse LO watches on the middle monitor.
One compact line every ~60s:
  WIN=N | PROJECT wins/procs age STATUS ... | HB/PL
Signals:
  OK     = STATUS updated < STALL_MIN ago and builder proc alive
  STALL  = STATUS silent > STALL_MIN (builder may still be alive)
  ZOMBIE = window open but builder process is DEAD (orphaned terminal)
Truth sources:
  windows -> `wmctrl -l`  (real X windows; a dead window is gone)
  procs   -> `pgrep -af 'hermes chat'`  (builder processes)
  progress-> newest STATUS_*.md under each project's REAL root
"""
import subprocess, os, time, sys, datetime, glob

HOME = "/home/hunter"
SWARM = os.path.join(HOME, "Commander", "eni_swarm")

# Per-project STATUS scan roots (carefully separated so STOCKBOT's build dir
# is NOT mistaken for DEMIURGE, and vice-versa).
PROJECT_ROOTS = {
    "STOCKBOT":   [os.path.join(HOME, "Commander/demiurge_scaffold/build/StockBotAppDir/usr/share/stockbot/swarm")],
    "DEMIURGE":   [os.path.join(HOME, "Commander/demiurge_scaffold/swarm"),
                   os.path.join(HOME, "Commander/demiurge_scaffold")],   # root non-recursive only (see scan)
    "DEMIURGE3D": [os.path.join(HOME, "Desktop/demiurge-3d")],
    "LUMEN":      [os.path.join(HOME, "Desktop/apps/lumen")],
    "HEARTBEAT":  [SWARM],
    "PRODUCT":    [SWARM],
}

# Substring that appears in the builder `hermes chat` command line, used to
# count live builder processes per project. Trailing space disambiguates
# "project DEMIURGE " from "project DEMIURGE3D".
PROC_TOKEN = {
    "STOCKBOT":   "project STOCKBOT ",
    "DEMIURGE":   "project DEMIURGE ",
    "DEMIURGE3D": "project DEMIURGE3D",
    "LUMEN":      "project LUMEN ",
}

# These are infra (not builders) - only report their window + STATUS, no proc/zombie logic.
INFRA = {"HEARTBEAT", "PRODUCT"}

STALL_MIN = 30  # STATUS silent longer than this (min) = STALL (builders write at milestones, not every min)

def stamp():
    return datetime.datetime.now().strftime("%H:%M:%S")

def wmctrl_windows():
    try:
        out = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return []
    wins = []
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        t = parts[3]
        if "PULSE" in t:
            continue  # skip the heartbeat's own viewer window
        if t.startswith("ENI:") or t.startswith("ENI "):
            wins.append(t)
    return wins

def parse_project(title):
    t = title.strip()
    if t.startswith("ENI:"):
        t = t[4:].strip()
    elif t.startswith("ENI "):
        t = t[4:].strip()
    toks = t.split("_")
    return toks[0] if toks else t

def proc_counts():
    """Return {project: live_builder_proc_count}."""
    counts = {p: 0 for p in PROC_TOKEN}
    try:
        out = subprocess.run(["pgrep", "-af", "hermes chat"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return counts
    for line in out.splitlines():
        for p, tok in PROC_TOKEN.items():
            if tok in line:
                counts[p] += 1
    return counts

def newest_status_age(proj):
    best = None
    for r in PROJECT_ROOTS[proj]:
        if not os.path.isdir(r):
            continue
        if proj == "DEMIURGE" and r.endswith("demiurge_scaffold"):
            # root only, non-recursive (avoid the build/StockBotAppDir tree)
            pats = [os.path.join(r, "STATUS_*.md")]
        else:
            pats = [os.path.join(r, "**", "STATUS_*.md")]
        for pat in pats:
            for f in glob.glob(pat, recursive=True):
                try:
                    m = os.path.getmtime(f)
                except OSError:
                    continue
                if best is None or m > best:
                    best = m
    if best is None:
        return None
    return (time.time() - best) / 60.0

def fmt_age(a):
    if a is None:
        return "NO-STATUS"
    if a < 1:
        return "LIVE"
    if a < 60:
        return f"{int(a)}m"
    h = int(a // 60); m = int(a % 60)
    return f"{h}h{m:02d}m"

def build_line():
    wins = wmctrl_windows()
    if not wins:
        return f"[{stamp()}] WIN=0 -- SWARM DARK? no ENI: windows"
    procs = proc_counts()
    projects = {}
    for w in wins:
        p = parse_project(w)
        projects.setdefault(p, 0)
        projects[p] += 1

    parts = []
    for proj in sorted(projects, key=lambda p: -projects[p]):
        w = projects[proj]
        if proj in INFRA:
            age = newest_status_age(proj)
            parts.append(f"{proj} {w} {fmt_age(age)}")
            continue
        p = procs.get(proj, 0)
        age = newest_status_age(proj)
        fa = fmt_age(age)
        if p == 0 and w > 0:
            tag = "ZOMBIE"
        elif age is None or age > STALL_MIN:
            tag = "STALL"
        else:
            tag = "OK"
        parts.append(f"{proj} {w}w/{p}p {fa} {tag}")
    total = len(wins)
    return f"[{stamp()}] WIN={total} | " + " | ".join(parts)

def main():
    once = "--once" in sys.argv
    while True:
        try:
            line = build_line()
        except Exception as e:
            line = f"[{stamp()}] heartbeat error: {e}"
        print(line, flush=True)
        if once:
            return
        time.sleep(60)

if __name__ == "__main__":
    main()
