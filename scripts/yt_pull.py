#!/usr/bin/env python3
"""eni-yt — channel transcript puller with PIA VPN IP rotation.

Usage:
  python3 scripts/yt_pull.py <channel_or_video_url> [--out data/transcripts]
        [--rotate-every 25] [--list] [--dry-run] [--no-pia] [--cookies COOKIES]
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO.parent))   # parent so `enterprise` pkg resolves
sys.path.insert(0, str(REPO))

from enterprise.modules.youtube_transcripts import cli_main


if __name__ == "__main__":
    sys.exit(cli_main(sys.argv[1:]))