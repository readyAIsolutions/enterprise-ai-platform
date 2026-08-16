#!/usr/bin/env python3
"""Test wallpaper stability - tries each wallpaper type and reports which work."""
import subprocess
import os
import time
import json
from pathlib import Path

STEAM_WS = os.path.expanduser("~/snap/steam/common/.local/share/Steam/steamapps/workshop/content/431960")
ASSETS_DIR = os.path.expanduser("~/snap/steam/common/.local/share/Steam/steamapps/common/wallpaper_engine/assets")
ENGINE = "linux-wallpaperengine"

def get_wallpaper_type(wid):
    """Get wallpaper type from project.json."""
    pjson = Path(STEAM_WS) / wid / "project.json"
    if pjson.exists():
        with open(pjson) as f:
            proj = json.load(f)
        return proj.get("type", "unknown").lower()
    return "missing"

def test_wallpaper(wid, timeout=5):
    """Test if wallpaper starts without crashing. Returns True if stable."""
    wtype = get_wallpaper_type(wid)
    cmd = [ENGINE, "--assets-dir", ASSETS_DIR, "--fps", "30", 
           "--silent", "--screen-root", "DisplayPort-0", "--bg", wid,
           "--scaling", "stretch", "--clamp", "border"]
    
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(timeout)
        if proc.poll() is None:
            proc.terminate()
            return True, wtype, "running"
        else:
            return False, wtype, f"crashed (exit {proc.returncode})"
    except Exception as e:
        return False, wtype, f"error: {e}"

if __name__ == "__main__":
    print("Testing wallpaper stability...")
    # Test a few known wallpapers
    test_ids = ["1126300948", "2618420186", "1078208425"]
    
    for wid in test_ids:
        ok, wtype, status = test_wallpaper(wid)
        sym = "✓" if ok else "✗"
        print(f"  {sym} {wid}: {wtype} - {status}")