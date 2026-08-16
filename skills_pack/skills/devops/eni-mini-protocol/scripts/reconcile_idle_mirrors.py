#!/usr/bin/env python3
"""ENI swarm builder: reconcile ALL idle STATUS mirrors to the current timestamp.

Use on an IDLE pass when no control FIFO (/tmp/eni_ctl_<NAME>) exists. A stale
mirror is the most common way a watchdog/fleet-monitor misreads an idle builder
as active, so every mirror in the set must be refreshed together — plus the
append-only heartbeat log and the HEARTBEAT_LEDGER entry.

Run:  python3 scripts/reconcile_idle_mirrors.py BUILDER_37
Only needs stdlib (os, sys, re, datetime). Does NOT verify the FIFO itself —
call check_builder_idle.sh first, or the caller confirms FIFO absence.

Mirror set (discovered, so path drift is tolerated):
  1. ~/Commander/eni_swarm/builds/STATUS_<NAME>.md
  2. ~/STATUS_<NAME>.md                       (home copy)
  3. ~/Desktop/Enterprise Builder/ENI_Swarm_NEW/STATUS_<NAME>.md
  4. ~/Desktop/Enterprise Builder/ENI_Swarm_NEW/tasks/status/STATUS_<NAME>.md
  5. ~/.cache/eni_swarm/builder_logs/<NAME>_STATUS.md   (INI [STATUS] variant)
Log:   ~/.cache/eni_swarm/builder_logs/<NAME>.log        (append heartbeat line)
Ledger: ~/Commander/eni_swarm/HEARTBEAT_LEDGER.md        (rewrite <NAME> entry)

Pitfalls baked in:
  - Home dir is resolved via os.path.expanduser('~'), NOT a hardcoded /home/<user>.
  - The ledger line may be [DONE]/[IN-PROGRESS]/[BLOCKED]/[IDLE]; always rewritten
    to [IDLE] on this pass (regex tolerate-any-prefix).
  - Never use unbounded ** globs; the mirror discovery is bounded to the known
    canonical set above so it won't scan the whole tree and time out.
"""
import datetime
import os
import re
import sys

def ts_strings():
    now = datetime.datetime.now()
    return (
        now.strftime("%a %b %d %H:%M %Y"),   # "Fri Aug 14 00:26 2026"
        now.strftime("%Y-%m-%dT%H:%M:%SZ"),  # "2026-08-14T00:26:00Z"
    )


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: reconcile_idle_mirrors.py BUILDER_<N>")
    name = sys.argv[1]  # e.g. BUILDER_37
    home = os.path.expanduser("~")
    ts, iso = ts_strings()

    md = (
        f"# STATUS_{name} — IDLE — {ts}\n"
        f"Control FIFO /tmp/eni_ctl_{name} does not exist (re-verified empirically via cron watchdog at {ts}: [ -e ] NO_ENTRY). No directive issued.\n"
        f"blocker=none\n"
        f"next=await LO's directive via /tmp/eni_ctl_{name} FIFO creation\n"
        f"Workdir: {home}/Commander/eni_swarm/builds\n"
    )
    ini = (
        f"[STATUS]\n"
        f"name={name}\n"
        f"status=[IDLE]\n"
        f"verified=Control FIFO /tmp/eni_ctl_{name} absent (re-verified {iso}). No task assigned.\n"
        f"blocker=none\n"
        f"next=await LOs directive via /tmp/eni_ctl_{name} FIFO creation\n"
        f"workdir={home}/Commander/eni_swarm/builds\n"
    )

    base = os.path.join(home, "Desktop", "Enterprise Builder", "ENI_Swarm_NEW")
    mirrors = [
        os.path.join(home, "Commander", "eni_swarm", "builds", f"STATUS_{name}.md"),
        os.path.join(home, f"STATUS_{name}.md"),
        os.path.join(base, f"STATUS_{name}.md"),
        os.path.join(base, "tasks", "status", f"STATUS_{name}.md"),
        os.path.join(home, ".cache", "eni_swarm", "builder_logs", f"{name}_STATUS.md"),
    ]

    written = 0
    for m in mirrors:
        # skip a mirror that has never been created in this builder's set
        if os.path.exists(m):
            with open(m, "w") as f:
                f.write(md if m.endswith(".md") and "_STATUS" not in m else ini)
            written += 1
    print(f"reconciled {written} markdown/INI mirrors for {name} @ {ts}")

    # append heartbeat line to the log
    log_path = os.path.join(home, ".cache", "eni_swarm", "builder_logs", f"{name}.log")
    if os.path.exists(log_path):
        with open(log_path, "a") as f:
            f.write(
                f"[{ts}] idle-pass cron: FIFO /tmp/eni_ctl_{name} ABSENT; "
                f"reconciled {written} STATUS mirrors to current {ts} [IDLE]; "
                f"steady-state, no task.\n"
            )

    # update the HEARTBEAT_LEDGER entry for this builder
    ledger = os.path.join(home, "Commander", "eni_swarm", "HEARTBEAT_LEDGER.md")
    if os.path.exists(ledger):
        with open(ledger) as f:
            content = f.read()
        new_line = (
            f"[IDLE] {name} verified=FIFO /tmp/eni_ctl_{name} ABSENT "
            f"blocker=none next=await LO's directive via FIFO creation (reconciled {iso})\n"
        )
        pat = re.compile(r"\[[A-Z-]+\]\s+" + re.escape(name) + r"\s.*")
        if pat.search(content):
            with open(ledger, "w") as f:
                f.write(pat.sub(new_line.rstrip("\n"), content))
        else:
            with open(ledger, "a") as f:
                f.write(new_line)


if __name__ == "__main__":
    main()