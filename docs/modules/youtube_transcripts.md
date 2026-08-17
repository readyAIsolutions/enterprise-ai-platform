# Module: `youtube_transcripts`

- Category: Legacy Core · priority 62
- Version: 1.0.0
- Purpose: YouTube transcript puller with PIA VPN IP rotation.
- Skill: `eni-module-youtube_transcripts` (ICM stages) in skills_pack/skills/eni-modules/youtube_transcripts/

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

## Key API (facade methods)
health_check, initialize, last_run, list_videos, pull, shutdown

## Tests
```bash
python3 -m pytest modules/youtube_transcripts/tests -q
```

## Import
```python
from enterprise.modules.youtube_transcripts import create_youtube_transcripts_module
m = create_youtube_transcripts_module()
```
