"""YouTube transcript puller with PIA VPN IP rotation.

Pulls full channel/single-video transcripts via yt-dlp + youtube-transcript-api
(if available), rotating the exit IP through Private Internet Access so YouTube
/ transcript endpoints never rate-limit or block us during a whole-channel pull.

PIA rotation strategy
---------------------
piactl is PIA's CLI. To rotate the IP we pick a fresh region and reconnect:
    piactl set region <region_id>
    piactl connect
This changes the visible egress IP. We rotate every N transcripts
(`rotate_every`, default 25) AND on any transport error, so a long channel pull
never trips Google's rate limiter on a single IP.

If piactl is present and `use_pia` is True (default), we rotate. If it's absent,
we degrade gracefully to backoff+retry so the module still works in offline or
VPN-less environments (the channel may simply pull slower / be more limited).

Transports (tried in order):
  1. yt-dlp (fast, supports both full + auto captions) -> builds a .vtt/.json,
     then we extract text.
  2. youtube_transcript_api (fallback, clean per-video timed text).

Output: one markdown file per video under <out>/<channel>/<video_id>.md, plus a
<out>/<channel>/_index.csv (id, title, duration, date, status).
"""
from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# PIA VPN control
# ---------------------------------------------------------------------------

class PIA:
    """Thin wrapper around piactl to rotate the exit IP."""

    def __init__(self, enabled: bool = True, piactl: Optional[str] = None) -> None:
        self.enabled = enabled
        self.piactl = piactl or shutil.which("piactl") or "piactl"
        self._region_used: List[str] = []
        self._available_checked = False

    def available(self) -> bool:
        return shutil.which("piactl") is not None

    def current_state(self) -> str:
        try:
            return subprocess.run([self.piactl, "get", "connectionstate"],
                                  capture_output=True, text=True, timeout=8).stdout.strip()
        except Exception:
            return "Unknown"

    def regions(self) -> List[str]:
        """Return available regions (long ids). Empty if unavailable."""
        try:
            out = subprocess.run([self.piactl, "get", "regions"],
                                 capture_output=True, text=True, timeout=15).stdout
            return [l.strip() for l in out.splitlines() if l.strip()]
        except Exception:
            return []

    def rotate(self, prefer_new: bool = True) -> bool:
        """Pick a (new) region and reconnect to get a fresh IP. Returns True on success."""
        if not self.enabled or not self.available():
            return False
        regions = self.regions()
        if not regions:
            return False
        # pick a region we haven't used, cycling if needed
        fresh = [r for r in regions if r not in self._region_used]
        pool = fresh or regions
        target = (pool * 2)[0]
        try:
            subprocess.run([self.piactl, "set", "region", target],
                           capture_output=True, timeout=15)
            subprocess.run([self.piactl, "connect"],
                           capture_output=True, timeout=30)
            # store so we cycle next time
            self._region_used.append(target)
            # wait for connected
            for _ in range(20):
                st = self.current_state()
                if st.lower() == "connected":
                    return True
                if st.lower() not in ("connecting", "reconnecting"):
                    break
                time.sleep(1.5)
            return self.current_state().lower() == "connected"
        except Exception:
            return False

    def disconnect(self) -> None:
        try:
            subprocess.run([self.piactl, "disconnect"], capture_output=True, timeout=15)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Transcript extraction
# ---------------------------------------------------------------------------

def _strip_vtt(text: str) -> str:
    """Strip VTT timestamps/markup -> plain text (one sentence per line-ish)."""
    lines = text.splitlines()
    out: List[str] = []
    for ln in lines:
        if re.match(r"^\d{2}:\d{2}", ln):          # cue number
            continue
        if "-->" in ln:                              # timestamp line
            continue
        ln = re.sub(r"<[^>]+>", "", ln).strip()       # html tags
        if ln and ln != "WEBVTT" and not ln.startswith("Kind:"):
            out.append(ln)
    return "\n".join(out)


# Hard ceiling: never start a fetch when the WiFi radio is too weak.
# Prevents the MT7921e from being hammered at poor signal.
_MAX_START_SIGNAL = -78   # dBm; if signal is at/below this, don't even begin


def _wifi_ok_to_fetch() -> bool:
    """True only if the WiFi signal is strong enough to safely fetch."""
    try:
        out = subprocess.run(["iw", "dev", "wlp4s0", "link"],
                             capture_output=True, text=True, timeout=6).stdout
        m = re.search(r"signal:\s*(-?\d+)", out)
        sig = int(m.group(1)) if m else None
    except Exception:
        sig = None
    # If we can't read signal, allow (don't block the pull) but the caller still
    # paces conservatively.
    return sig is None or sig > _MAX_START_SIGNAL


def _ytdlp_transcript(video_id: str, cookies: Optional[str] = None,
                      proxy: Optional[str] = None) -> Optional[str]:
    """Pull a transcript via yt-dlp. Returns plain text or None.

    WiFi/network-safe: yt-dlp is forced to a SINGLE fragment/socket connection
    and its rate is capped. If `proxy` (e.g. "socks5://127.0.0.1:9050") is given,
    ONLY yt-dlp routes through it (Tor / your own SOCKS) for IP rotation — the
    main system network is never touched, so it can't drop Ethernet/WiFi.
    """
    if not _wifi_ok_to_fetch():
        return None
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cmd = [
            "yt-dlp", "--no-download",
            "--concurrent-fragments", "1",
            "--limit-rate", "300K",
            "--socket-timeout", "20",
            "--retries", "3",
        ]
        if proxy:
            cmd += ["--proxy", proxy]
        cmd += [
            "--write-auto-subs", "--write-subs",
            "--sub-langs", "en.*", "-o", str(tmp / "sub.%(ext)s"),
            f"https://www.youtube.com/watch?v={video_id}",
        ]
        if cookies and Path(cookies).exists():
            cmd += ["--cookies", cookies]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        txt = ""
        for f in sorted(tmp.glob("sub.*")):
            if f.suffix in (".vtt", ".srt", ".json"):
                try:
                    if f.suffix == ".json":
                        data = json.loads(f.read_text())
                        txt += _json_to_text(data)
                    else:
                        txt += _strip_vtt(f.read_text(errors="replace"))
                except Exception:
                    continue
        return txt.strip() or None


def _json_to_text(data: dict) -> str:
    """yt-dlp json3/segments to text."""
    events = data.get("events") or []
    if not events:
        segs = data.get("segments") or []
        return " ".join(s.get("text", "") for s in segs if s.get("text"))
    out = []
    for e in events:
        if e.get("segs"):
            out.append(" ".join(s.get("utf8", "") for s in e["segs"] if s.get("utf8")))
    return " ".join(out)


def _yta_transcript(video_id: str) -> Optional[str]:
    """Fallback via youtube_transcript_api."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except Exception:
        return None
    try:
        api = YouTubeTranscriptApi()
        data = api.fetch(video_id)
        parts = []
        for s in data or []:
            t = (s.get("text") if isinstance(s, dict) else getattr(s, "text", None))
            if t:
                parts.append(t)
        return " ".join(parts).strip() or None
    except Exception:
        return None


def get_transcript(video_id: str, use_ytdlp: bool = True, cookies: Optional[str] = None,
                   proxy: Optional[str] = None) -> Optional[str]:
    """Return transcript text for a video, trying yt-dlp then the API."""
    if use_ytdlp:
        t = _ytdlp_transcript(video_id, cookies, proxy=proxy)
        if t:
            return t
    return _yta_transcript(video_id)


# ---------------------------------------------------------------------------
# Channel puller
# ---------------------------------------------------------------------------

@dataclass
class VideoMeta:
    id: str
    title: str = ""
    duration: float = 0.0
    channel: str = ""


def list_channel_videos(channel_url: str, cookies: Optional[str] = None) -> List[VideoMeta]:
    """Return all video ids/titles on a channel via yt-dlp flat playlist."""
    cmd = ["yt-dlp", "--flat-playlist", "--print",
           "%(id)s\t%(title)s\t%(duration)s", channel_url]
    if cookies and Path(cookies).exists():
        cmd.append("--cookies"); cmd.append(cookies)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    out = []
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 1 and re.match(r"^[A-Za-z0-9_-]{11}$", parts[0].strip()):
            vid = parts[0].strip()
            title = parts[1] if len(parts) > 1 else ""
            try:
                dur = float(parts[2]) if len(parts) > 2 and parts[2] else 0.0
            except ValueError:
                dur = 0.0
            out.append(VideoMeta(vid, title, dur))
    return out


def _wifi_signal() -> Optional[int]:
    """Read current WiFi signal (dBm) from iw, if available. Returns int or None."""
    try:
        out = subprocess.run(["iw", "dev", "wlp4s0", "link"],
                             capture_output=True, text=True, timeout=6).stdout
        m = re.search(r"signal:\s*(-?\d+)", out)
        return int(m.group(1)) if m else None
    except Exception:
        return None


# Per-signal minimum sleep (seconds) between pull steps so we never overflow the
# MT7921e firmware packet buffer (which is what drops WiFi under rapid traffic).
_SIGNAL_PACE = [
    # (max_dbm, sleep) — weaker signal -> longer safe pause
    (-55, 1.0),
    (-62, 2.0),
    (-68, 3.5),
    (-75, 6.0),
    (-85, 10.0),
    (-200, 15.0),
]


def _pace_for_signal(signal: Optional[int]) -> float:
    if signal is None:
        return 2.0  # conservative default when signal unknown
    for max_dbm, sleep in _SIGNAL_PACE:
        if signal >= max_dbm:
            return sleep
    return 15.0


def _safe_sleep(signal: Optional[int] = None, base: float = 1.0) -> None:
    """Sleep enough for the current signal so the pull never drops WiFi.
    Deliberately serial + paced: reliability over speed."""
    pace = _pace_for_signal(signal)
    time.sleep(max(base, pace))


def pull_channel(
    channel_url: str,
    out_dir: str | os.PathLike[str],
    rotate_every: int = 25,
    use_pia: bool = True,
    cookies: Optional[str] = None,
    dry_run: bool = False,
    pace: bool = True,          # WiFi-safe pacing on by default
    proxy: Optional[str] = None,  # e.g. socks5://127.0.0.1:9050 (per-process only)
) -> Dict[str, object]:
    """Pull every transcript on the channel into markdown, rotating IP via PIA.

    WiFi-safe: extraction is strictly serial and paced (never floods the radio),
    with an adaptive pause driven by live signal strength when `pace` is True.
    Returns a summary dict.
    """
    out = Path(out_dir)
    if dry_run:
        # offline determinism: a tiny fixed sample, no network listing
        meta = [
            VideoMeta("AJKVdQvjyXQ", "Sample Every Channel", 120.0 + i * 5)
            for i in range(3)
        ]
        channel_name = "dryrun_test"
    else:
        meta = list_channel_videos(channel_url, cookies)
        # channel name / slug
        m = re.search(r"@([A-Za-z0-9_\-\.]+)", channel_url)
        channel_name = m.group(1) if m else "unknown"
    channel_dir = out / channel_name
    channel_dir.mkdir(parents=True, exist_ok=True)

    pia = PIA(enabled=use_pia)
    index_path = channel_dir / "_index.csv"
    with open(index_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["video_id", "title", "duration", "date", "status"])

    ok = fail = 0
    for i, v in enumerate(meta, 1):
        # WiFi-safe: pace first so we never flood the radio
        signal = _wifi_signal() if pace else None
        if pace and i > 1:
            _safe_sleep(signal)
        # rotate IP occasionally
        if use_pia and pia.available() and i > 1 and (i % rotate_every == 0):
            pia.rotate()
        target = channel_dir / f"{v.id}.md"
        status = "skipped" if target.exists() else "pending"
        if dry_run:
            status = "dry"
        else:
            try:
                text = get_transcript(v.id, cookies=cookies, proxy=proxy)
                if text:
                    header = (f"# {v.title or v.id}\n\n"
                              f"- video: https://www.youtube.com/watch?v={v.id}\n"
                              f"- duration: {v.duration:.0f}s\n\n---\n\n")
                    target.write_text(header + text, encoding="utf-8")
                    status = "ok"; ok += 1
                else:
                    status = "no-transcript"; fail += 1
                # retry one transport error by rotating once
                if status == "no-transcript" and pia.available():
                    pia.rotate()
                    text = get_transcript(v.id, cookies=cookies, proxy=proxy)
                    if text:
                        header = (f"# {v.title or v.id}\n\n"
                                  f"- video: https://www.youtube.com/watch?v={v.id}\n"
                                  f"- duration: {v.duration:.0f}s\n\n---\n\n")
                        target.write_text(header + text, encoding="utf-8")
                        status = "ok"; ok += 1; fail -= 1
            except Exception:
                status = "error"; fail += 1
        with open(index_path, "a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow([v.id, v.title, v.duration, datetime.now().date().isoformat(), status])
        sys.stdout.write(f"[{i}/{len(meta)}] {v.id} {status}\n")
        sys.stdout.flush()

    return {"channel": channel_name, "total": len(meta), "ok": ok, "fail": fail,
            "dir": str(channel_dir)}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("url", help="channel or video url")
    ap.add_argument("--out", default="data/transcripts")
    ap.add_argument("--rotate-every", type=int, default=25)
    ap.add_argument("--no-pia", action="store_true", help="disable PIA rotation")
    ap.add_argument("--cookies", default=None, help="path to cookies.txt")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-pace", action="store_true",
                    help="disable WiFi-safe pacing (NOT recommended)")
    ap.add_argument("--proxy", default=None,
                    help="per-process SOCKS proxy for yt-dlp, e.g. socks5://127.0.0.1:9050 (Tor). "
                         "Only the pull routes through it; the system network is untouched.")
    ap.add_argument("--list", action="store_true", help="just list videos")
    args = ap.parse_args(argv)

    if args.list:
        metas = list_channel_videos(args.url, args.cookies)
        for m in metas:
            print(f"{m.id}\t{m.title}\t{m.duration:.0f}")
        return 0

    res = pull_channel(args.url, args.out, rotate_every=args.rotate_every,
                       use_pia=not args.no_pia, cookies=args.cookies,
                       dry_run=args.dry_run, pace=not args.no_pace,
                       proxy=args.proxy)
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "PIA", "get_transcript", "list_channel_videos", "pull_channel", "main",
    "VideoMeta", "__version__",
]
__version__ = "1.0.0"