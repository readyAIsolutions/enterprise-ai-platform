"""YouTube transcript puller with PIA VPN IP rotation.

Pulls full-channel or per-video transcripts (yt-dlp + youtube-transcript-api),
rotating the exit IP through Private Internet Access so a whole-channel pull
never gets rate-limited or blocked by Google.

This is a Network/Research capability module:
  * `list_channel_videos(url)`   -> all video metadata on a channel
  * `pull_channel(url, out)`     -> write one .md per video + _index.csv
  * `get_transcript(video_id)`   -> text for a single video
  * PIA rotation on interval + on transport error (opt-out with use_pia=False)
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from enterprise.platform_kernel import HealthStatus, Module, module

from .transcripts import (  # noqa: F401
    PIA,
    VideoMeta,
    get_transcript,
    list_channel_videos,
    main as cli_main,
    pull_channel,
)

logger = logging.getLogger("eni.yt")

__version__ = "1.0.0"


@module(
    name="youtube_transcripts",
    version="1.0.0",
    config_defaults={
        "out_dir": "data/transcripts",
        "rotate_every": None,  # None -> decide in pull (default 25)
        "use_pia": True,
    },
)
class YouTubeTranscriptsModule(Module):
    """Kernel module exposing the channel transcript puller + PIA rotation."""

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._last_run: Optional[dict[str, Any]] = None
        self._init_error: Optional[str] = None

    async def initialize(self) -> None:
        self.status = HealthStatus.HEALTHY
        try:
            import shutil
            if not shutil.which("yt-dlp"):
                logger.info("yt-dlp not on PATH — transcript puller uses API fallback only")
        except Exception as exc:
            self._init_error = str(exc)
            self.status = HealthStatus.DEGRADED

    async def health_check(self) -> HealthStatus:
        if self._init_error:
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY

    async def shutdown(self) -> None:
        self.status = HealthStatus.UNKNOWN
        logger.info("youtube_transcripts module shutdown")

    # facade
    def list_videos(self, url: str) -> list[VideoMeta]:
        return list_channel_videos(url)

    def pull(self, url: str, out_dir: Optional[str] = None) -> dict[str, Any]:
        out = out_dir or self.config.get("out_dir", "data/transcripts")
        res = pull_channel(url, out,
                           rotate_every=int(self.config.get("rotate_every") or 25),
                           use_pia=bool(self.config.get("use_pia", True)))
        self._last_run = res
        return res

    def last_run(self) -> Optional[dict[str, Any]]:
        return dict(self._last_run) if self._last_run else None


def create_youtube_transcripts_module(
    config: Optional[dict[str, Any]] = None,
) -> YouTubeTranscriptsModule:
    return YouTubeTranscriptsModule(config=config or {})


__all__ = [
    "YouTubeTranscriptsModule",
    "create_youtube_transcripts_module",
    "pull_channel",
    "list_channel_videos",
    "get_transcript",
    "PIA",
    "VideoMeta",
    "cli_main",
    "__version__",
]