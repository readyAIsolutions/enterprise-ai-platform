# eni_swarm_compression/scripts/quick_status.py
# (Reference placeholder - actual at /home/hunter/Desktop/eni_compression/quick_status.py)

#!/usr/bin/env python3
"""Quick status for Hermes/cron"""

from pathlib import Path

ENI_DIR = Path("/home/hunter/Desktop/eni_compression")
STATUS_FILE = ENI_DIR / "STATUS_ENI_IMPOSSIBLE.md"

if STATUS_FILE.exists():
    print(STATUS_FILE.read_text())
else:
    print("STATUS: UNKNOWN - file missing")