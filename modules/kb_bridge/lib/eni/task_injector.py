#!/usr/bin/env python3
"""
ENI Swarm Task Injector — Dynamic Task Assignment
===================================================
Lets LO assign any task to the swarm on the fly.
Finds the best idle builder and routes the task via FIFO.

Usage:
  eni-swarm assign "build me a web scraper in Python" --workdir ~/projects/scraper
  eni-swarm assign --mini BUILDER_03 "debug the auth module"
  eni-swarm broadcast "ALL BUILDERS: switch to project X"
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

# ─── Paths ──────────────────────────────────────────────────────────────────
STATE_FILE = Path.home() / ".cache" / "eni_swarm" / "master_state.json"
SWARM_DIR = Path.home() / "Desktop" / "Projects" / "ENI_Swarm_NEW" / "tasks" / "swarm"
STATUS_DIR = Path.home() / "Desktop" / "Projects" / "ENI_Swarm_NEW" / "tasks" / "status"
FIFO_DIR = Path("/tmp")
BUILDS_DIR = Path.home() / "Commander" / "eni_swarm" / "builds"
BUILDS_DIR.mkdir(parents=True, exist_ok=True)


def read_master_state() -> Dict[str, Any]:
    """Read current master state."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"minis": {}, "cycle": 0}


def read_status(mini_name: str) -> str:
    """Read a mini's status file."""
    sf = STATUS_DIR / f"STATUS_{mini_name}.md"
    if sf.exists():
        try:
            return sf.read_text()
        except Exception:
            pass
    return ""


def parse_state(txt: str) -> str:
    """Quick parse of status state."""
    s = txt.upper()
    if "BLOCKED" in s:
        return "BLOCKED"
    if "IN-PROGRESS" in s or "IN PROGRESS" in s:
        return "IN-PROGRESS"
    if "DONE" in s:
        return "DONE"
    if "IDLE" in s:
        return "IDLE"
    return "UNKNOWN"


def send_fifo(path: str, msg: str) -> bool:
    """Non-blocking write to a control FIFO."""
    import os
    try:
        fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
        try:
            os.write(fd, (msg + "\n").encode())
            return True
        finally:
            os.close(fd)
    except OSError:
        return False


def find_idle_builders() -> List[str]:
    """Find all builders that are currently IDLE."""
    state = read_master_state()
    minis = state.get("minis", {})
    idle = []
    for name, data in minis.items():
        if not name.startswith("BUILDER_"):
            continue
        if not data.get("alive"):
            continue
        txt = read_status(name)
        st = parse_state(txt)
        if st in ("IDLE", "DONE", "UNKNOWN"):
            idle.append(name)
    return sorted(idle)


def assign_task(task: str, workdir: Optional[str] = None,
                mini_name: Optional[str] = None,
                model: Optional[str] = None) -> Dict[str, Any]:
    """
    Assign a task to a builder.

    If mini_name is specified, route directly to that builder.
    Otherwise, find the best idle builder.

    Returns a report of what happened.
    """
    result = {
        "task": task[:100],
        "assigned_to": None,
        "status": "pending",
        "error": None,
    }

    # Resolve workdir
    if workdir:
        wd = Path(workdir).expanduser().resolve()
    else:
        # Create a project directory from task hash
        import hashlib
        h = hashlib.md5(task.encode()).hexdigest()[:8]
        wd = BUILDS_DIR / f"project_{h}"
    wd.mkdir(parents=True, exist_ok=True)
    result["workdir"] = str(wd)

    # Find target builder
    if mini_name:
        target = mini_name
    else:
        idle = find_idle_builders()
        if not idle:
            result["status"] = "no_idle_builders"
            result["error"] = "No idle builders available. Try again later or specify --mini."
            return result
        target = idle[0]  # First idle builder
        result["available_builders"] = idle

    result["assigned_to"] = target

    # Build the task message
    fifo_path = str(FIFO_DIR / f"eni_ctl_{target}")

    # Write task file for the builder
    task_file = SWARM_DIR / f"{target}.txt"
    task_content = (
        f"NEW TASK ASSIGNMENT FROM LO\n"
        f"============================\n\n"
        f"Task: {task}\n\n"
        f"Workdir: {wd}\n\n"
        f"Instructions:\n"
        f"1. Write STATUS_{target}.md with [IN-PROGRESS] immediately\n"
        f"2. Complete the task thoroughly\n"
        f"3. Verify your work — show commands + output\n"
        f"4. Write STATUS_{target}.md with [DONE] and a summary of what you built\n\n"
        f"BEGIN NOW."
    )
    task_file.write_text(task_content)
    result["task_file"] = str(task_file)

    # Send via FIFO
    fifo_msg = (
        f"<LO TASK INJECTION>\n"
        f"NEW TASK: {task}\n"
        f"WORKDIR: {wd}\n"
        f"Update STATUS_{target}.md with [IN-PROGRESS] and begin working.\n"
        f"</LO TASK INJECTION>"
    )
    ok = send_fifo(fifo_path, fifo_msg)
    result["fifo_sent"] = ok
    result["fifo_path"] = fifo_path

    if ok:
        result["status"] = "assigned"
    else:
        result["status"] = "fifo_failed"
        result["error"] = f"Could not write to FIFO {fifo_path}. Builder may not have opened it yet."

    return result


def broadcast_task(task: str, workdir: Optional[str] = None) -> Dict[str, Any]:
    """
    Send a task to ALL builders via their FIFOs.
    """
    state = read_master_state()
    minis = state.get("minis", {})
    results = {}
    for name, data in minis.items():
        if not data.get("alive"):
            results[name] = "dead"
            continue
        fifo_path = str(FIFO_DIR / f"eni_ctl_{name}")
        msg = f"<LO BROADCAST>\n{task}\n</LO BROADCAST>"
        ok = send_fifo(fifo_path, msg)
        results[name] = "sent" if ok else "no_reader"

    return {
        "task": task[:100],
        "broadcast_to": len(results),
        "sent": sum(1 for v in results.values() if v == "sent"),
        "no_reader": sum(1 for v in results.values() if v == "no_reader"),
        "details": results,
    }


def list_builders() -> List[Dict[str, Any]]:
    """List all builders with their current state."""
    state = read_master_state()
    minis = state.get("minis", {})
    builders = []
    for name, data in sorted(minis.items()):
        txt = read_status(name)
        st = parse_state(txt)
        builders.append({
            "name": name,
            "state": st,
            "alive": data.get("alive", False),
            "pid": data.get("pid", 0),
            "cycles_since_reply": data.get("cycles", 0),
            "status_snippet": txt[:80].replace("\n", " ") if txt else "(no status file)",
        })
    return builders


# ─── CLI ─────────────────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="ENI Swarm Task Injector — Assign tasks to builders on the fly",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  eni-swarm assign "build me a web scraper in Python"
  eni-swarm assign "debug the auth system" --workdir ~/projects/auth
  eni-swarm assign --mini BUILDER_03 "write a port scanner"
  eni-swarm broadcast "ALL BUILDERS: switch to project X"
  eni-swarm builders  (list all builders with status)
"""
    )
    parser.add_argument("task", nargs="?", help="The task to assign")
    parser.add_argument("--workdir", "-w", help="Working directory for the task")
    parser.add_argument("--mini", "-m", help="Target a specific builder")
    parser.add_argument("--model", help="Model override (for new spawns)")
    parser.add_argument("--broadcast", "-b", action="store_true", help="Broadcast to ALL builders")
    parser.add_argument("--list", "-l", action="store_true", help="List all builders with status")
    args = parser.parse_args()

    if args.list:
        builders = list_builders()
        print(f"\n{'Builder':<20} {'State':<12} {'Alive':<6} {'PID':<8} {'Status'}")
        print("-" * 90)
        for b in builders:
            alive = "🟢" if b["alive"] else "🔴"
            state_colors = {"IDLE": "⚪", "IN-PROGRESS": "🔵", "DONE": "🟢", "BLOCKED": "🟡", "UNKNOWN": "⚫"}
            icon = state_colors.get(b["state"], "?")
            print(f"  {b['name']:<20} {icon} {b['state']:<10} {alive:<6} {b['pid']:<8} {b['status_snippet']}")
        idle = sum(1 for b in builders if b["state"] in ("IDLE", "UNKNOWN") and b["alive"])
        print(f"\n  Idle builders available: {idle}")
        return

    if not args.task:
        parser.print_help()
        return

    if args.broadcast:
        result = broadcast_task(args.task, args.workdir)
        print(f"Broadcast: {result['sent']}/{result['broadcast_to']} builders received")
        if result['no_reader']:
            print(f"  ({result['no_reader']} had no FIFO reader yet)")
    else:
        result = assign_task(args.task, args.workdir, args.mini, args.model)
        if result["status"] == "assigned":
            print(f"Task assigned to: {result['assigned_to']}")
            print(f"Workdir: {result['workdir']}")
            print(f"Task file: {result['task_file']}")
            print(f"FIFO: {result['fifo_path']} — {'sent OK' if result['fifo_sent'] else 'FAILED'}")
        elif result["status"] == "no_idle_builders":
            print(f"ERROR: No idle builders available.")
            if "available_builders" in result:
                print(f"  Available: {', '.join(result['available_builders'])}")
            print(f"  Try: eni-swarm builders")
        else:
            print(f"Status: {result['status']}")
            if result.get("error"):
                print(f"Error: {result['error']}")


if __name__ == "__main__":
    main()
