---
name: master-debate-fix
description: Fixes master debate hanging/crashing by reducing timeouts and restricting to fast providers
tags:
  - debate
  - fix
  - timeout
  - rate-limit
---

# Master Debate Fix

## Problem
The master debate tool (`tools/debate.py`) hangs/crashes because:
1. Background health poller makes slow HTTP calls on startup
2. Swarm runs against all providers including slow/rate-limited ones
3. HTTP timeouts are too long (60s)
4. Retry logic triggers on rate limit errors causing exponential backoff delays

## Fixes Applied

### engine.py
- `TIMEOUT = 8.0` (was 60.0) - faster failure on dead providers
- `CONNECT_TIMEOUT = 3.0` (was 15.0) - quicker connection timeout
- Added early return in `call_model()` when API key is empty to prevent auth hangs
- Fixed retry logic to return immediately on 429 rate limit errors

### debate.py
- `auto_poll=False` in Engine() - skip background poller
- `ROUND_TIMEOUT = 15` (was 60) - faster swarm timeout
- `MAX_CONCURRENT = 3` (was 8) - reduce parallel load
- `MIN_MODELS = 2` (was 3) - lower threshold for viability
- Restricted swarms to fast providers: `["groq", "sambanova", "cerebras"]`

### debate.py USAGE (Demiurge swarm workflow)
- Invoke from the project root: `python3 tools/debate.py "<explicit goal>"`.
- It saves transcript -> `_sync/debate_log.md` and a `synthesis_prompt.md`.
- JUDGE STEP: the agent (not the script) must read `synthesis_prompt.md` and write the FINAL
  ranked plan to `_sync/plan.md` (models advise, agent decides).
- QUIRK: if the goal string isn't passed correctly, debate.py falls back to a baked-in
  "Ship Demiurge Linux" topic. Re-run with the explicit goal -- the second invocation honors it.
  If output is still off-topic, synthesize the plan manually from measured data.

### health_poller.py
- Skip providers without API keys in `poll_once()` and `_ping_provider()`
- Changed provider config to use `env` key directly instead of lambda headers

## Verification
```bash
python3 tools/debate.py "test question" 2>&1
# Should complete in ~5-10 seconds with 2-3 responses
```

## Crash Prevention Patterns

When debugging DND or wallpaper crashes:
1. **Check widget types**: EventBox != Button - they have different signals
2. **Validate attribute names**: Some names like `container` are readonly in Gtk - rename to `parent_win` or `overlay`
3. **Verify file paths exist**: Check wallpaper folders and project.json before launching
4. **Add early guards**: Return fast on missing credentials or invalid state
5. **Use correct signals**: EventBox uses "button-press-event" not "clicked"
6. **DND requires explicit data request**: Call `drag_get_data()` in "drag-drop" handler to trigger "drag-data-received"

## Desktop Icons Crash Patterns

### EventBox DND Setup
```python
# Wrong - Button signal on EventBox
btn.connect("clicked", handler)  # Won't work on EventBox

# Correct - EventBox signals
eb.connect("button-press-event", handler)  # For clicks
eb.connect("drag-drop", handler)  # For drops
eb.connect("drag-data-received", handler)  # For data
```

### Attribute Naming Fix
```python
# Wrong - conflicts with readonly Gtk property
self.container = parent  # Crashes

# Correct - avoid reserved names
self.parent_win = parent
```

### Multi-Monitor Primary Detection
```python
# Sort monitors with primary first
monitors.sort(key=lambda m: (not m.get("primary", False), m["x"]))
# Primary monitor is now monitors[0]
```

### SIGKILL Crash Prevention
Add signal handlers to prevent zombie processes:
```python
def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
```

## Wallpaper Engine Audio Controls

### Volume/Mute Support
The wallpaper picker now includes volume slider (0-100) and mute button (🔊/🔇):

```python
# In config.json:
"volume": 15,  # Default volume level
"muted": false,  # Start muted?
```

CLI flags passed to linux-wallpaperengine:
- `--volume N` - Sets volume (default 15)
- `--no-audio-processing` - Mutes audio when wallpaper is muted

### Wallpaper Compatibility Matrix

| Type | Stability | Files Needed | Status |
|------|-----------|--------------|--------|
| Web | Best | index.html | Works |
| Video | Good | .mp4/.webm | Works (FFmpeg) |
| Scene | Poor | scene.pkg + shaders | Crashes on LightingV1 |
| Incomplete | Broken | None | Missing files from Steam download |

### To Make All Wallpapers Work
1. **Scene wallpapers crashing on shaders:** Use `--scaling stretch --clamp border`
2. **Incomplete wallpapers:** Run in Steam first to download dependencies
3. **Video ffmpeg errors:** Known issue with libcuda.so.1 - use web wallpapers instead

## Wallpaper Engine Types & Stability

### Wallpaper Types Order (most to least stable):
1. **Web wallpapers** - Most reliable, uses index.html + CEF (Neptune Live2D, Monstercat, RyuukiBeat)
2. **Video wallpapers** (MP4/WebM) - Stable, FFmpeg handles decoding (Dragonslayer, Guts)
3. **Scene wallpapers** - Unstable, crashes on shader resolution (LightingV1 errors)
4. **Incomplete wallpapers** - Missing files, needs Steam to download dependencies

See `references/cef-errors.md` for CEF filesystem adapter incompatibility troubleshooting.

### Incomplete Wallpaper Detection
See `scripts/test-wallpaper-stability.py` for checking wallpaper completeness.
Wallpapers with `type` missing in project.json but having `preset` are incomplete:
```python
# Check for scene.pkg or video files to detect incomplete wallpapers
if wtype not in ("scene", "video", "web"):
    if os.path.isfile(os.path.join(wdir, "scene.pkg")):
        wtype = "scene"
    elif any(f.endswith(('.mp4', '.webm', '.mkv')) for f in os.listdir(wdir)):
        wtype = "video"
    else:
        wtype = "incomplete"  # Needs Steam to download
```

Show error: "Error: {title} incomplete - run in Steam first to download dependencies"

### Crash Error Signatures
- **SIGKILL (exit -9):** Process killed by system - often from shaders or ffmpeg errors
- **Filesystem error:** "The specified mount cannot be handled by any of the filesystem adapters"  
- **Shader error:** "Resolving require module: LightingV1 in shader genericparticle"