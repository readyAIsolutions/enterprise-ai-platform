---
name: eni-module-youtube_transcripts
description: Operate the ENI Enterprise `youtube_transcripts` module (Legacy Core) — YouTube transcript puller with PIA VPN IP rotation. Use when working with youtube_transcripts in the Enterprise Platform.
---

# Module skill: youtube_transcripts

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: YouTube transcript puller with PIA VPN IP rotation.

## What it does
YouTube transcript puller with PIA VPN IP rotation.

Pulls full-channel or per-video transcripts (yt-dlp + youtube-transcript-api),
rotating the exit IP through Private Internet Access so a whole-channel pull
never gets rate-limited or blocked by Google.

This is a Network/Research capability module:
  * `list_channel_videos(url)`   -> all video metadata on a channel
  * `pull_channel(url, out)`     -> write one .md per video + _index.csv
  * `get_transcript(video_id)`   -> text for a single video
  * PIA rotation on interval + on transport error (opt-out with use_pia=False)

## Key API (facade methods on the @module class)
- health_check\n- initialize\n- last_run\n- list_videos\n- pull\n- shutdown

## Use
Import via:
```python
from enterprise.modules.youtube_transcripts import create_youtube_transcripts_module
m = create_youtube_transcripts_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/youtube_transcripts/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
