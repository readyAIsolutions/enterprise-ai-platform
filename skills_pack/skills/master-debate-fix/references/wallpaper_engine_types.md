# Wallpaper Engine Quick Reference

- **Scene type**: demon_core, fantasticcar, razer_vortex - need assets dir
- **Web type**: workshop ID 864286576 - needs CEF (included in build)
- **Video type**: MP4/WebM backgrounds - needs FFmpeg
- **LuBan**: OpenGL executable wallpapers from luban.zip

Assets dir: `$HOME/snap/steam/common/.local/share/Steam/steamapps/common/wallpaper_engine/assets`

## Stable Wallpaper Recommendations

**Video (most stable):**
- `1126300948` - Dragonslayer (Berserk) - 4K video
- `1929584653` - Guts - video
- `2048218531` - Dynamic Windows Glitch - 4K video

**Web (stable):**
- `1078208425` - Neptune Live2D
- `1278092907` - Monstercat Audio Visualizer

**Scene (avoid - crashes on shaders):**
- `2618420186` - auto gradient (crashes on LightingV1 shader)

## Test Commands
```bash
# Video wallpaper (stable)
./run-wallpaper.sh 1126300948 DisplayPort-0 stretch

# Scene wallpaper (may crash)
./run-wallpaper.sh 2618420186 DisplayPort-0 stretch

unzip ~/Downloads/luban.zip -d ~/wallpapers/
./run-wallpaper.sh ~/wallpapers/Ubuntu\ 64/LuBan fill
```