#!/usr/bin/env python3
"""
Fleet Monitor — one-shot report pass (report-only; never dispatches/edits builders).

Run this standalone after `monitor_fleet.py` writes HEARTBEAT_LEDGER.md, OR
copy its body into an execute_code block. It implements the 'compute, don't
dump' technique from references/fleet-monitor-concise-summary.md: it computes
aggregate counts in-process and emits a SHORT report, so the environment never
wraps/elides a huge multiline dump into an <ENI-COMPRESSED> block.

Usage:
    python3 fleet_monitor_pass.py /home/hunter/Commander/eni_swarm

Correctly handles the two known pitfalls:
  * Zero-padded builder filenames (STATUS_BUILDER_01..50, NOT 1..50) — derives
    the real path/number from glob, never reconstructs "STATUS_BUILDER_{n}.md".
  * Empty STATUS files silently dropped by the crash guard (ledger rows < files)
    — reported so a truncated builder isn't mistaken for a lost worker.
"""
import os, re, sys, time, glob, subprocess

BASE = sys.argv[1] if len(sys.argv) > 1 else "/home/hunter/Commander/eni_swarm"
BUILDS = os.path.join(BASE, "builds")

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout

# --- 1. run the ledger writer if not already run ---
sh(f"cd {BASE} && python3 monitor_fleet.py 2>&1")

# --- 2. per-builder likely state + mtime ---
now = time.time()
by_state = {"DONE": [], "IN-PROGRESS": [], "BLOCKED": []}
recent = []   # mtime within 24h
mtime_dates = {}
empty_files = []
total = parsed = 0
for f in glob.glob(os.path.join(BUILDS, "STATUS_BUILDER_*.md")):
    total += 1
    n = int(re.search(r"STATUS_BUILDER_(\d+)\.md", os.path.basename(f)).group(1))
    size = os.path.getsize(f)
    m = os.path.getmtime(f)
    d = time.strftime("%Y-%m-%d", time.localtime(m))
    mtime_dates[d] = mtime_dates.get(d, 0) + 1
    age_h = (now - m) / 3600
    if size == 0:
        empty_files.append(n)
        continue          # crash guard skips these -> absent from ledger
    parsed += 1
    if age_h < 24:
        recent.append((n, round(age_h, 1)))
    state = "UNKNOWN"
    try:
        for line in open(f, errors="replace"):
            ul = line.upper()
            if ("[" in ul or "STATE" in ul or "STATUS" in ul) and re.search(r"IN[-_ ]?PROGRESS", ul):
                state = "IN-PROGRESS"; break
            if "BLOCKED" in ul:
                state = "BLOCKED"; break
        if state == "UNKNOWN":
            first = next((l.strip() for l in open(f, errors="replace") if l.strip()), "")
            m2 = re.match(r"\[([^\]]+)\]", first)
            state = m2.group(1).strip().upper() if m2 else "UNKNOWN"
    except OSError:
        state = "UNREADABLE"
    mapped = "BLOCKED" if state == "BLOCKED" else ("IN-PROGRESS" if state.startswith("IN") else "DONE")
    by_state.setdefault(mapped, []).append(n)

print(f"SCANNED {total} files -> PARSED {parsed} (ledger rows). "
      f"{len(empty_files)} empty/crash-guard-dropped: "
      f"{sorted(empty_files) if empty_files else 'none'}")

print(f"STATE: DONE={len(by_state['DONE'])} IN-PROGRESS={len(by_state['IN-PROGRESS'])} "
      f"BLOCKED={len(by_state['BLOCKED'])}")
print("  IN-PROGRESS:", sorted(by_state["IN-PROGRESS"]) or "-")
print("  BLOCKED:", sorted(by_state["BLOCKED"]) or "-")

print("MTIME BY DATE (dormancy source of truth, NOT ledger states):")
for d in sorted(mtime_dates):
    flag = "  <-- today/recent" if d >= time.strftime("%Y-%m-%d", time.localtime(now - 3600)) else ""
    print(f"  {d}: {mtime_dates[d]}{flag}")
print("RECENT (<24h):", sorted(recent) or "none  ->  fleet fully dormant")

# --- 3. corroboration: builder PIDs, control FIFOs, strander find procs ---
pids = sh("ps aux | grep -iE 'eni-mini|status_builder|demiurge|eni_swarm' | grep -v grep | grep -vE 'avahi|odoo|postgres'").strip()
fifos = sh("ls /tmp/eni_ctl_BUILDER_* 2>/dev/null").strip()
stranders = sh("ps aux | grep 'find / -iname' | grep -v grep").strip()
print("BUILDER PIDS:", "none" if not pids else pids)
print("CONTROL FIFOs:", fifos if fifos else "none (no routing)")
print("STRANDER find-procs:", "none" if not stranders else stranders)

print("\nINTERPRETATION:")
# Single shared old date across all active builders == parked floor.
if len(mtime_dates) == 2 and not recent:
    print("  One old parking date across all builders + no recent file = FRESH-PARKED / DORMANT.")
elif len(mtime_dates) == 1:
    print("  All files share ONE date = parked floor / dormant; no per-builder churn since.")
else:
    print("  Recent files detected -> inspect each recent builder's head (IDLE check-in vs real task).")
print("  A single recent file usually = daily IDLE self-check (head reads 'IDLE'), NOT a live task.")