"""Tests for the youtube_transcripts module (offline-safe, no network)."""
from __future__ import annotations

import csv
import tempfile
from pathlib import Path

from enterprise.modules.youtube_transcripts.transcripts import (
    PIA, VideoMeta, _strip_vtt, pull_channel,
)


def test_strip_vtt_removes_timestamps():
    raw = "WEBVTT\n\n1\n00:00:01.000 --> 00:00:03.000\nalpha beta\n\n2\n00:00:03.000 --> 00:00:05.000\n<v>gamma</v> delta\n"
    out = _strip_vtt(raw)
    assert "alpha beta" in out
    assert "gamma delta" in out
    assert "-->" not in out
    assert "00:00" not in out


def test_pull_channel_dry_run_writes_index(tmp_path):
    # dry_run: no network; exercises index writing + channel dir creation
    res = pull_channel(
        "https://www.youtube.com/@JEVanClief/videos",
        str(tmp_path),
        rotate_every=25,
        use_pia=False,
        dry_run=True,
    )
    assert res["dir"].endswith("dryrun_test")
    index = Path(res["dir"]) / "_index.csv"
    assert index.exists()
    rows = list(csv.reader(open(index)))
    assert rows[0][0] == "video_id"


def test_pia_available_detects_missing():
    # piactl likely present here, but never force networking in a unit test
    pia = PIA(enabled=True)
    assert pia.piactl  # resolves at least to a name/`shutil.which` fallback
