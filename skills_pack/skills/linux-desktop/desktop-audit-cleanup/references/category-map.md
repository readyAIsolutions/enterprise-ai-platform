# Folder Name Pattern → Category Mapping

## 3D_Printing/
- `3d files/`, `3d_files/`, `3D_Printing/`
- `*.stl`, `*.gcode`, `*.3mf`, `*.zip` (model archives)

## Apps/
- `*.desktop`, `*.AppImage`, `*.deb`, `*.sh` (launchers)
- `apps/`, `Applications/`

## Documents/
- `Docs/`, `Documents/`, `Misc/`
- `*.pdf`, `*.docx`, `*.md`, `*.txt`
- `*Resume*`, `*CV*`
- `STATUS_*.md`, `STATUS_*.json`
- `Screenshot*.png`, `*.jpg`
- `paint_*.log`, `paint_*.sh`

## Projects/ (then sub-categorize)

### Demiurge_3D/
- `Demiurge3D/`, `Demiurge_3D/`, `Demiurge 3D_Projects/`
- `Demiurge_3D_Website/`, `Demiurge_3D_Projects/`

### Demiurge_Trading/
- `Demiurge_Creed/`, `Demiurge_Marketing/`, `Demiurge_Marketing_OS/`
- `Demiurge_Pitch/`, `Demiurge_Scripts/`
- `StockBot/` (if mixed with trading)

### Demiurge_Drive/
- `Demiurge_Pitch/` (investor decks)
- `Demiurge_Scripts/` (NAS/deployment scripts)
- `NAS9_*`, `STATUS_DEMIURGE_MKT_*`

### ENI_Swarm/
- `ENI Swarm/`, `ENI_KB/`, `ENI_Compression/`, `eni_compression/`
- `ENI_Swarm_Archive/`, `ENI_CREATIVE_FRAMEWORK.md`
- `ENI_MASTERPIECE.md`, `ENI_*PROMPT.md`
- `eni_*.sh`, `eni_*.py`, `cookbook_swarm*.py`

### Cookbook/
- `cookbook_site/`, `cookbook_parts*/`
- `ANARCHIST_COOKBOOK*`
- `chapter_*.html`, `appendix_*.html`
- `search_*.json`, `site_*.js`, `site_*.css`

### Infrastructure/
- `tor-data/`, `torrc`, `tor.log`
- `cloudflared`, `cf_*.log`
- `onion_*.sh`, `onion_*.py`, `meek_client.py`, `obfs4proxy`
- `Commander/` (if system-level)

### Lumen/
- `Lumen/`, `lumen/`
- `lumen.AppImage`, `lumen.deb`
- Wallpaper engine code

### SKYNET/
- `SKYNET/`, `skynet/` (Hermes framework)

### StockBot/
- `StockBot/` (trading bot, features, gates, swarm)

### Archive/
- `UNCENSORED_FABLE5_ARCHIVE/`
- Old/obsolete versions

## Wallpapers/
- `Wallpaper/`, `Wallpapers/`
- `*.png`, `*.jpg`, `*.webp` (images only)

## Patterns to IGNORE (venv, cache, build artifacts)
- `__pycache__/`, `.venv/`, `.venv_*/`, `venv/`
- `dist/`, `build/`, `squashfs-root/`
- `*.egg-info/`, `.pytest_cache/`, `.mypy_cache/`
- `node_modules/`, `.git/` (except at repo root)
- `.~lock.*#`, `*.swp`, `*.swp`