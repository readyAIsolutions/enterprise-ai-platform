#!/usr/bin/env python3
"""Pull EVERYTHING (all channel transcripts + all paper feeds), serial + paced.

WiFi-safety: extraction is strictly sequential, paced by live signal strength,
and rotates the PIA exit IP on any failure/block (with retry). This never floods
the MT7921e radio the way parallel pulls did.

Usage:
  python3 scripts/pull_all.py [--source CHANNEL_HANDLE|papers]...
        --all        pull every configured channel + all paper feeds
        --papers     pull only paper feeds
        --dry-run    don't network, just print the source list
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO.parent))   # parent so `enterprise` resolves
sys.path.insert(0, str(REPO))

CHANNELS = {
    "matthew_berman": "https://www.youtube.com/@matthew_berman/videos",
    "jason_ai": "https://www.youtube.com/@jasonai/videos",
    "cole_medin": "https://www.youtube.com/@ColeMedin/videos",
    "ray_fernando": "https://www.youtube.com/@rayfernando/videos",
    "karpathy": "https://www.youtube.com/@AndrejKarpathy/videos",
    "3b1b": "https://www.youtube.com/@3blue1brown/videos",
    "statquest": "https://www.youtube.com/@statquest/videos",
    "2minutepapers": "https://www.youtube.com/@TwoMinutePapers/videos",
    "ai_explained": "https://www.youtube.com/@aiexplained-official/videos",
    "wes_roth": "https://www.youtube.com/@WesRoth/videos",
    "david_shapiro": "https://www.youtube.com/@davethetrader/videos",
    "liam_ottley": "https://www.youtube.com/@liamottley/videos",
    "julian_goldie": "https://www.youtube.com/@JulianGoldieSEO/videos",
}


def _sig() -> int | None:
    try:
        out = subprocess.run(["iw", "dev", "wlp4s0", "link"],
                             capture_output=True, text=True, timeout=6).stdout
        m = __import__("re").search(r"signal:\s*(-?\d+)", out)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def _pace(sig: int | None) -> float:
    p = s = 2.0
    if sig is None: return 3.0
    if sig >= -55: return 1.5
    if sig >= -62: return 2.5
    if sig >= -68: return 4.0
    if sig >= -75: return 7.0
    return 12.0


def _pia_rotate(retries=3):
    if not __import__("shutil").which("piactl"):
        return False
    regions = subprocess.run(["piactl", "get", "regions"],
                             capture_output=True, text=True, timeout=15).stdout.splitlines()
    if not regions: return False
    for _ in range(retries):
        r = (regions * 3)[_ % len(regions)]
        subprocess.run(["piactl", "set", "region", r], capture_output=True, timeout=15)
        subprocess.run(["piactl", "connect"], capture_output=True, timeout=30)
        for _ in range(12):
            st = subprocess.run(["piactl", "get", "connectionstate"],
                                capture_output=True, text=True, timeout=8).stdout.strip()
            if st.lower() == "connected": return True
            time.sleep(1.5)
    return False


def pull_channel(url: str, out: str, paced=True) -> dict:
    cmd = ["python3", str(REPO / "scripts" / "yt_pull.py"), url,
           "--out", out, "--rotate-every", "20"]
    if not paced: cmd.append("--no-pace")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=6000)
    for line in r.stdout.splitlines():
        print("   ", line)
    return {"rc": r.returncode, "out": r.stdout[-400:]}


def pull_papers(out: str) -> dict:
    sys.path.insert(0, str(REPO.parent))
    from enterprise.modules.paper_feeds.papers import pull_all_feeds
    return pull_all_feeds(out)


def pull_all(sources: dict, out_dir: str, paced=True) -> None:
    print("=== ENI: pulling ALL sources (serial + WiFi-paced) ===")
    for name, url in sources.items():
        print(f"\n[channel] {name} -> {url}")
        for attempt in range(3):
            res = pull_channel(url, out_dir, paced=paced)
            if res["rc"] == 0:
                # success or already-done; move on
                if "no-transcript" in res["out"] and attempt < 2:
                    _pia_rotate()
                    time.sleep(5)
                    continue
                break
            _pia_rotate()
            time.sleep(6)
    print("\n[feed] paper feeds")
    pull_papers(out_dir)


def main(argv) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--papers", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-pace", action="store_true")
    ap.add_argument("--source", action="append", default=[])
    ap.add_argument("--out", default="data/transcripts")
    a = ap.parse_args(argv)

    out = str(REPO / a.out)
    if a.papers:
        print("papers only"); pull_papers(out); return 0
    sources = {k: v for k, v in CHANNELS.items() if k in a.source} if a.source else CHANNELS
    if a.dry_run:
        print("\n".join(f"{k} -> {v}" for k, v in sources.items()))
        print("paper feeds: arxiv hf pwc alphaxiv")
        return 0
    if not sources:
        print("no sources; use --all or --source NAME"); return 2
    pull_all(sources, out, paced=not a.no_pace)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))