#!/usr/bin/env python3
"""Test which wallpapers work without crashing - run via skill_manage."""
import subprocess
import os
import json
import time
from pathlib import Path

STEAM_WS = os.path.expanduser("~/snap/steam/common/.local/share/Steam/steamapps/workshop/content/431960")
ASSETS_DIR = os.path.expanduser("~/snap/steam/common/.local/share/Steam/steamapps/common/wallpaper_engine/assets")
ENGINE = "linux-wallpaperengine"
SCREEN = "DisplayPort-0"

def get_wallpaper_info(wid):
    """Get wallpaper info from project.json."""
    pjson = Path(STEAM_WS) / wid / "project.json"
    if pjson.exists():
        with open(pjson) as f:
            proj = json.load(f)
        return {
            "title": proj.get("title", wid),
            "type": proj.get("type", "unknown").lower(),
            "has_scene_pkg": os.path.exists(pjson.parent / "scene.pkg"),
            "has_video": any(f.endswith(('.mp4', '.webm', '.mkv')) for f in os.listdir(pjson.parent) if os.path.isfile(pjson.parent / f)),
            "has_html": os.path.exists(pjson.parent / "index.html"),
        }
    return None

if __name__ == "__main__":
    # Print all wallpapers and their file status
    if not os.path.isdir(STEAM_WS):
        print("Steam workshop not found")
        exit(0)
    
    working = []
    incomplete = []
    
    for wid in sorted(os.listdir(STEAM_WS))[:50]:
        wdir = os.path.join(STEAM_WS, wid)
        pjson = os.path.join(wdir, "project.json")
        if not os.path.isfile(pjson):
            continue
        
        with open(pjson) as f:
            proj = json.load(f)
        
        title = proj.get("title", wid)
        wtype = proj.get("type", "unknown").lower()
        files = os.listdir(wdir)
        
        has_scene_pkg = "scene.pkg" in files
        has_video = any(f.endswith(('.mp4', '.webm', '.mkv')) for f in files)
        has_html = "index.html" in files
        
        if wtype == "web" and has_html:
            working.append((wid, title, "web"))
        elif wtype == "video" and has_video:
            working.append((wid, title, "video"))
        elif wtype == "scene" and has_scene_pkg:
            working.append((wid, title, "scene"))
        elif wtype != "unknown":
            incomplete.append((wid, title, wtype, "missing_files"))
        else:
            incomplete.append((wid, title, wtype, "incomplete"))
    
    print("=== Working Wallpapers ===")
    for wid, title, typ in working[:10]:
        print(f"  {wid}: {title} ({typ})")
    
    print(f"\n=== Incomplete/Missing Files ({len(incomplete)}) ===")
    for wid, title, typ, reason in incomplete[:5]:
        print(f"  {wid}: {title} ({typ}) - {reason}")