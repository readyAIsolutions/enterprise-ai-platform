## Working Provider Combinations

For fastest response with free tier:
```python
fast_providers = ["groq", "sambanova", "cerebras"]  # ~0.3-0.5s response
rate_limited = ["openrouter"]  # Often returns 429
slow = ["anthropic", "openai"]  # Paid, slower
```

## Wallpaper Engine Crash Patterns

### Scene Wallpapers Crash on Shaders
**Symptom:** Process dies with exit code -9 (SIGKILL) during "Resolving require module: LightingV1"
**Cause:** Missing shader assets or GPU/driver incompatibility
**Fix:** Prefer video wallpapers for stability. Scene wallpapers with custom shaders (LightingV1, etc.) often crash.

## Stability Hierarchy
1. **Web wallpapers** - Most reliable, uses index.html + CEF (Neptune Live2D, Monstercat, RyuukiBeat)
2. **Video wallpapers** (MP4/WebM) - Stable, FFmpeg handles decoding (Dragonslayer, Guts)
3. **Scene wallpapers** - Unstable, crashes on shader resolution (LightingV1, genericparticle)
4. **Incomplete wallpapers** - Missing files, needs Steam to download dependencies first

## Incomplete Wallpapers
These show "unknown" type or have `preset` but no `scene.pkg`/`mp4`/`index.html`:
- Run in Steam Wallpaper Engine FIRST to download dependencies
- Mark as "incomplete" in picker - show error when user tries to apply
- Cannot run directly via linux-wallpaperengine binary

### Known Stable Wallpapers
- **Web (most stable):** `1078208425` (Neptune Live2D), `1278092907` (Monstercat), `1104570570` (RyuukiBeat)
- **Video:** `1126300948` (Dragonslayer), `1929584653` (Guts)
- **Scene (may crash):** `2618420186` (auto gradient), `1208251528` (Kermit XP)

### Crash-Resistant Launch Pattern
Always use `stretch` scaling with `clamp border` for best compatibility:
```bash
linux-wallpaperengine --scaling stretch --clamp border
```

## Using Steam to Download Dependencies

For wallpapers showing "incomplete" or crashing, launch them once in Steam:

```bash
# Launch Steam Wallpaper Engine
steam steam://install/431960

# Common wallpapers needing Steam download:
# - 2526570366 - Cat (scene)
# - 1914447853 - ae86 drifting gif (scene)
# - 1900119721 - Kermit business (Hardbass) (scene)
```

After running in Steam once, the wallpaper files will download and linux-wallpaperengine will work.