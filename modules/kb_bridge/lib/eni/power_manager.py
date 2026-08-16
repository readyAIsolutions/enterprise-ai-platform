#!/usr/bin/env python3
"""
ENI Swarm Power Manager — Control how many builders are active
===============================================================
Manages a "swarm power" slider (25%/50%/75%/100%) that controls
how many builders are active at any time.

Also exposes builder thinking/output streams for the dashboard.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

CACHE_DIR = Path.home() / ".cache" / "eni_swarm"
POWER_FILE = CACHE_DIR / "swarm_power.json"
BUILDER_LOG_DIR = CACHE_DIR / "builder_logs"
BUILDER_LOG_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_POWER_LEVELS = [0.25, 0.50, 0.75, 1.00]


def get_power_state() -> Dict[str, Any]:
    """Get current swarm power state."""
    if POWER_FILE.exists():
        try:
            return json.loads(POWER_FILE.read_text())
        except Exception:
            pass
    return {
        "level": 1.0,  # 100% default
        "active_builders": [],
        "total_builders": 50,
        "active_count": 50,
        "updated": time.time(),
    }


def set_power(level: float) -> Dict[str, Any]:
    """
    Set swarm power level.
    
    level: 0.25, 0.50, 0.75, or 1.0
    Returns new state.
    """
    level = round(level, 2)
    if level not in DEFAULT_POWER_LEVELS:
        level = min(DEFAULT_POWER_LEVELS, key=lambda x: abs(x - level))
    
    total = 50
    active_count = max(1, int(total * level))
    # Always use first N builders
    active_builders = [f"BUILDER_{i:02d}" for i in range(1, active_count + 1)]
    
    state = {
        "level": level,
        "active_builders": active_builders,
        "total_builders": total,
        "active_count": active_count,
        "updated": time.time(),
    }
    POWER_FILE.write_text(json.dumps(state, indent=2))
    
    # Signal inactive builders to pause
    _signal_inactive(active_builders)
    
    return state


def _signal_inactive(active: List[str]):
    """Send pause signal to builders not in the active list."""
    import os as _os
    for i in range(1, 51):
        name = f"BUILDER_{i:02d}"
        if name not in active:
            fifo = f"/tmp/eni_ctl_{name}"
            try:
                fd = _os.open(fifo, _os.O_WRONLY | _os.O_NONBLOCK)
                try:
                    _os.write(fd, b"<POWER MANAGEMENT> You are currently INACTIVE (swarm power reduced). Pause any active work. Write STATUS file with [IDLE] and wait.\n</POWER MANAGEMENT>\n")
                finally:
                    _os.close(fd)
            except OSError:
                pass


def is_builder_active(name: str) -> bool:
    """Check if a builder is active under current power settings."""
    state = get_power_state()
    return name in state.get("active_builders", [])


def get_builder_activity() -> List[Dict[str, Any]]:
    """
    Get recent builder thinking/output from log files.
    Scans builder log directory for recent activity.
    """
    activity = []
    # Read from builder log files
    for log_file in sorted(BUILDER_LOG_DIR.glob("BUILDER_*.log"), key=lambda f: f.stat().st_mtime, reverse=True):
        name = log_file.stem
        try:
            lines = log_file.read_text().strip().splitlines()
            # Get last 5 lines of output
            recent = lines[-5:] if len(lines) > 5 else lines
            mtime = log_file.stat().st_mtime
            activity.append({
                "name": name,
                "recent_output": "\n".join(recent),
                "output_lines": len(lines),
                "last_active": mtime,
                "age_seconds": time.time() - mtime,
            })
        except Exception:
            pass
    
    return activity[:20]  # Top 20 most recent


def log_builder_output(name: str, output: str):
    """Append builder output to its log file."""
    log_file = BUILDER_LOG_DIR / f"{name}.log"
    try:
        with open(log_file, "a") as f:
            f.write(output)
            if not output.endswith("\n"):
                f.write("\n")
    except Exception:
        pass


# ─── CLI ─────────────────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="ENI Swarm Power Manager")
    parser.add_argument("action", nargs="?", choices=["get", "set", "activity"],
                       default="get")
    parser.add_argument("--level", type=float, help="Power level (0.25, 0.50, 0.75, 1.0)")
    args = parser.parse_args()
    
    if args.action == "set":
        if not args.level:
            print("Usage: power set --level 0.50")
            return
        state = set_power(args.level)
        pct = int(state["level"] * 100)
        print(f"Swarm power: {pct}% ({state['active_count']}/{state['total_builders']} builders active)")
    elif args.action == "activity":
        activity = get_builder_activity()
        for a in activity:
            print(f"\n{'='*60}")
            print(f"  {a['name']}  ({a['age_seconds']:.0f}s ago, {a['output_lines']} lines)")
            print(f"  {'─'*56}")
            for line in a['recent_output'].splitlines():
                print(f"  {line[:100]}")
    else:
        state = get_power_state()
        pct = int(state["level"] * 100)
        print(f"Swarm power: {pct}% ({state['active_count']}/{state['total_builders']} builders active)")


if __name__ == "__main__":
    main()
