# Watching / transcribing a video behind a login wall (e.g. Facebook reel)

When the user says "actually watch the whole video" on a login-gated platform
(Facebook reels, IG, etc.), you can often get the **direct media file** from the
page/embed markup without auth, download it, and transcribe the audio. This
session: a Facebook reel was fully login-walled, but the raw 720p `.mp4` was
present in the page's JSON and downloadable anonymously.

## 1. Get the direct file URL from the markup

The player/video element only mounts when authed, but the media URLs are in the
page JSON. Approaches that worked:

- Browse to the page and inspect `<meta>`/title/OG for the caption + the
  platform's public video ID. (`canonical` link often carries the video id and a
  human-readable title.)
- Use curl against the page and its **public embed/plugin endpoint** and grep
  for media srcs. For Facebook the embed endpoint exposed the mp4:
  ```
  curl -s "https://www.facebook.com/plugins/video.php?href=<URL_ENCODED>&show_text=0" \
    -A "Mozilla/5.0" | grep -oiE 'hd_src|sd_src|video[^"]*\.mp4'
  ```
- pattern to grep: `sd_src\":\"https:\/\/...mp4?`, `hd_src\":\"...`, and bare
  `video...\.mp4` paths. Prefer `hd_` / 720p bitrate over `sd_`.

## 2. Download the media file

Use the exact URL (query params are signed + expiring) with a browser UA:
```bash
curl -sL -o reel.mp4 "<full_hd_src_url>" -A "Mozilla/5.0"
file reel.mp4    # should say: ISO Media, MP4 Base Media
ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 reel.mp4
```
Signed CDN links can expire; if 403/empty, re-fetch the embed/page and grab a
fresh URL. Some signed URLs contain escape sequences like `\u00253D` — decode
unescaped JSON (replace `\/`→`/`, `\u0026`→`&`, `%3D`→`=`) before curl.

## 3. Transcribe audio (faster-whisper)

- Extract mono 16k audio: `ffmpeg -y -i reel.mp4 -vn -ac 1 -ar 16000 reel.wav`
- faster-whisper is NOT on system python (PEP-668); install in an existing
  venv (e.g. the training venv): `<venv>/bin/pip install faster-whisper -q`
- Transcribe (CPU int8 is fine for a few-minute clip):
  ```python
  from faster_whisper import WhisperModel
  m = WhisperModel('base', device='cpu', compute_type='int8')
  segs, info = m.transcribe('reel.wav', beam_size=5, language='en')
  for s in segs: print(f"[{s.start:6.1f}-{s.end:6.1f}] {s.text.strip()}")
  ```
  'base' model ≈ 40s to transcribe 8.5 min of audio. Save the transcript to a
  file, then read it in full to actually understand the video's content /
  structure — transcription is how you "watch" a walled video when you can't
  view frames.

## 4. Frames (optional, for visual content)

`ffmpeg -i reel.mp4 -vf fps=1/frame%03d.jpg` then `vision_analyze` key frames.
For an 8-minute pitch video the transcript alone was sufficient; frames add
visual context (on-screen text, product shots).

## Notes

- This works because CDN media URLs are often not auth-checked at fetch time —
  the login wall gates the browser/app, not the raw file endpoint.
- Respect the DMCA/terms: this is for understanding content you already have a
  link to, not mass downloading.
