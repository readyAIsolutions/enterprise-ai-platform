#!/usr/bin/env python3
"""ENI transcript paper pull daemon — persistent, self-pacing, WiFi-safe.

Reads a queue of sources (channels + paper feeds), pulls them in SMALL batches,
checks live WiFi signal between every batch, and idles when the radio is weak.
Persists progress so it survives restarts and can run slowly overnight.

This deliberately does NOT pull everything at once. It works a few items at a
time, waits for the signal to recover, and continues — finishing the whole queue
over hours without ever dropping WiFi.

Queue state lives in data/pull_daemon_state.json (source -> done flag). Re-run
resumes where it left off.

Usage:
  python3 scripts/pull_daemon.py                    # start (foreground)
  python3 scripts/pull_daemon.py --one              # one batch then exit
  python3 scripts/pull_daemon.py --list             # print queue only
  python3 scripts/pull_daemon.py --reset            # clear done flags
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO.parent))
sys.path.insert(0, str(REPO))

CHANNELS = {
    "jevanclief": "https://www.youtube.com/@JEVanClief/videos",
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
    "david_shapiro": "https://www.youtube.com/@DavidShapiroAI/videos",
    "liam_ottley": "https://www.youtube.com/@liamottley/videos",
    "julian_goldie": "https://www.youtube.com/@JulianGoldieSEO/videos",
}

PAPER_FEEDS = ["arxiv", "hf", "pwc", "alphaxiv"]

STATE_FILE = "data/pull_daemon_state.json"
TRANSCRIPTS_DIR = "data/transcripts"
PAPERS_DIR = "data/papers"
LOG_FILE = "data/pull_daemon.log"

# Batch size: how many transcripts to pull before re-checking signal + idling.
# Strictly ONE source at a time = never parallel, never a burst.
DEFAULT_BATCH = 1
# Per-item paced sleep floor (seconds).
MIN_PACE = 2.0


def _log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(Path(REPO) / LOG_FILE, "a") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def _signal() -> Optional[int]:
    try:
        out = subprocess.run(["iw", "dev", "wlp4s0", "link"],
                             capture_output=True, text=True, timeout=6).stdout
        m = re.search(r"signal:\s*(-?\d+)", out)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def _idle_for(signal: Optional[int]) -> float:
    """Recommended idle (seconds) for the current signal — the WiFi-safe pace."""
    if signal is None:
        return 6.0
    if signal >= -55:
        return 3.0
    if signal >= -62:
        return 5.0
    if signal >= -68:
        return 9.0
    if signal >= -75:
        return 20.0
    if signal >= -85:
        return 45.0
    return 90.0


def _load_state() -> Dict[str, str]:
    p = Path(REPO) / STATE_FILE
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def _save_state(state: Dict[str, str]) -> None:
    p = Path(REPO) / STATE_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(p)


def _run(cmd: List[str], timeout: int = 7200) -> int:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    out = (r.stdout or "") + (r.stderr or "")
    if out:
        _log(out[-300:])
    return r.returncode


def _pull_channel(name: str, url: str) -> int:
    _log(f"channel {name}: pull started")
    # Per-process Tor SOCKS proxy for IP rotation — only yt-dlp rides it, so the
    # main network (Ethernet) is never touched and can't drop.
    proxy = os.environ.get("ENI_PULL_PROXY", "socks5://127.0.0.1:9050")
    return _run([
        sys.executable, str(REPO / "scripts" / "yt_pull.py"),
        url, "--out", str(REPO / TRANSCRIPTS_DIR),
        "--rotate-every", "9999",   # PIA rotate off; Tor rotates itself
        "--no-pia", "--proxy", proxy,
    ])


def _pull_papers() -> int:
    _log("paper feeds: pull started")
    return _run([
        sys.executable, "-c",
        ("import sys; sys.path.insert(0,'/home/hunter/Desktop/Enterprise Builder/enterprise');"
         "from enterprise.modules.paper_feeds.papers import pull_all_feeds;"
         "print(pull_all_feeds('/home/hunter/Desktop/Enterprise Builder/enterprise/data/papers'))"),
    ])


def _remaining(state: Dict[str, str]) -> List[tuple]:
    """Return not-yet-done sources as (kind, name, target_fn)."""
    queue = []
    for name, url in CHANNELS.items():
        if state.get(f"chan:{name}") != "done":
            queue.append(("channel", name, lambda u=url, n=name: _pull_channel(n, u)))
    for feed in PAPER_FEEDS:
        if state.get(f"feed:{feed}") != "done":
            queue.append(("feed", feed, lambda f=feed: _pull_papers()))
    return queue


def _one_batch(state: Dict[str, str], batch: int) -> bool:
    """Pull up to `batch` remaining sources (or one channel = whole channel's
    batch-limited transcripts via the paced puller). Returns True if any done."""
    queue = _remaining(state)
    if not queue:
        return False
    worked = False
    for kind, name, fn in queue[:batch]:
        sig = _signal()
        if sig is not None and sig <= -80:
            # WiFi far too weak to pull safely — pause until it recovers.
            _log(f"WiFi too weak ({sig} dBm); pausing 90s instead of pulling.")
            time.sleep(90)
            return worked
        _log(f"→ {kind} {name} (signal {sig} dBm, idle {_idle_for(sig)}s)")
        time.sleep(_idle_for(sig))  # breathe before each source
        rc = fn()
        # mark done only on success (yt_pull returns 0 from CLI main always;
        # treat no-transcript as done too but keep failures to retry via PIA)
        if kind == "feed":
            state[f"feed:{name}"] = "done"
            worked = True
        else:
            state[f"chan:{name}"] = "done" if rc in (0,) else "retry"
            worked = True
        _save_state(state)
    return worked


def main(argv: List[str]) -> int:
    mode = argv[0] if argv else "run"
    if mode == "--list":
        state = _load_state()
        for kind, name, _ in _remaining(state):
            print(f"{kind}: {name}")
        return 0
    if mode == "--reset":
        _save_state({})
        print("reset")
        return 0

    state = _load_state()
    _log("=== ENI pull daemon starting (WiFi-safe, persistent) ===")
    if mode == "--one":
        _one_batch(state, DEFAULT_BATCH)
        _log("one batch done; exiting (--one)")
        return 0

    # loop 24/7: keep working; when the queue is momentarily empty, idle and
    # rescan so newly uploaded videos get pulled over time.
    while True:
        worked = _one_batch(state, DEFAULT_BATCH)
        if not worked:
            _log("queue momentarily empty; idle 20 min then rescan for new content.")
            time.sleep(1200)
            # rescan: reset done flags on channels every cycle so new uploads
            # that appear (already-pulled files are skipped by the puller) get
            # caught on the next pass.
            _save_state({})


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))