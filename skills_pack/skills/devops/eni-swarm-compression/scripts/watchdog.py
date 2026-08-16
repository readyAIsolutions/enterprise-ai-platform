# eni_swarm_compression/scripts/watchdog.py
# (Reference placeholder - actual at /home/hunter/Desktop/eni_compression/watchdog.py)

#!/usr/bin/env python3
"""
ENI Compression Swarm Health Watchdog
Runs every 5 minutes via cron - checks swarm health, restarts if dead
"""

import subprocess, time, sys
from pathlib import Path

ENI_DIR = Path("/home/hunter/Desktop/eni_compression")
STATUS_FILE = ENI_DIR / "STATUS_ENI_IMPOSSIBLE.md"
LOG_FILE = ENI_DIR / "watchdog.log"

def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")

def check_swarm():
    result = subprocess.run(
        ["pgrep", "-f", "eni_impossible_swarm.py"],
        capture_output=True, text=True
    )
    pids = result.stdout.strip().split()
    return len(pids) > 0, pids

def check_status_fresh():
    if not STATUS_FILE.exists():
        return False
    mtime = STATUS_FILE.stat().st_mtime
    return (time.time() - mtime) < 120

def check_master_growing():
    master = ENI_DIR / "MASTER_IMPOSSIBLE_PIPELINE.md"
    if not master.exists():
        return False
    size = master.stat().st_size
    last_size_file = ENI_DIR / ".last_master_size"
    last_size = 0
    if last_size_file.exists():
        last_size = int(last_size_file.read_text().strip())
    last_size_file.write_text(str(size))
    return size > last_size

def restart_swarm():
    log("RESTARTING SWARM")
    subprocess.run(["pkill", "-f", "eni_impossible_swarm.py"], capture_output=True)
    time.sleep(3)
    subprocess.Popen(
        ["python3", "eni_impossible_swarm.py"],
        cwd=ENI_DIR,
        stdout=open(ENI_DIR / "swarm.log", "a"),
        stderr=open(ENI_DIR / "swarm.err", "a")
    )
    log("Swarm restart initiated")

def main():
    alive, pids = check_swarm()
    status_fresh = check_status_fresh()
    master_growing = check_master_growing()
    
    log(f"Health check: alive={alive} pids={len(pids)} status_fresh={status_fresh} master_growing={master_growing}")
    
    if not alive or not status_fresh or not master_growing:
        log("HEALTH CHECK FAILED - restarting")
        restart_swarm()
        sys.exit(1)
    
    log("HEALTH CHECK OK")
    sys.exit(0)

if __name__ == "__main__":
    main()