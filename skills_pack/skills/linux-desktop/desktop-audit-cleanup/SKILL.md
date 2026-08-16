---
name: desktop-audit-cleanup
description: Audit and reorganize a chaotic Linux desktop/home directory. Identify duplicates, scattered project folders, stray files, and daemon-recreated directories. Consolidate everything into a clean category-based structure under ~/Projects/ with a minimal Desktop (5-7 top-level folders only).
category: linux-desktop
tags: [desktop, cleanup, organization, audit, deduplication, daemon-management]
---

# Desktop Audit & Cleanup Skill

## When to Use
- Desktop has 20+ folders/files mixed together (projects, docs, screenshots, binaries, configs)
- Duplicate folders exist in multiple locations (e.g., `~/Desktop/ENI_KB`, `~/Projects/ENI_Swarm/KnowledgeBase`, `~/Projects/ENI_Swarm/ENI_KB`)
- Daemons/background processes keep recreating deleted folders
- User wants "everything in its place" with a clean Desktop

## Workflow

### 1. Audit (Read-Only First)
```bash
ls -la ~/Desktop/
tree ~/Desktop -L 2 -d  # or: find ~/Desktop -maxdepth 2 -type d
```
Map every top-level item to its **true category**:
| Category | Examples |
|----------|----------|
| `3D_Printing/` | STL, G-code, printer configs |
| `Apps/` | `.desktop`, `.AppImage`, `.deb` |
| `Documents/` | PDFs, resumes, notes, screenshots |
| `Projects/` | All code repos, swarms, bots, pipelines |
| `Wallpapers/` | Images only |

### 2. Create Target Structure
```bash
mkdir -p ~/Desktop/{3D_Printing,Apps,Documents,Projects,Wallpapers}
mkdir -p ~/Desktop/Projects/{Demiurge_3D,Demiurge_Trading,Demiurge_Drive,ENI_Swarm,Cookbook,Infrastructure,Lumen,SKYNET,StockBot,Archive}
```

### 3. Move & Consolidate (Batch Commands)
Move each category in parallel batches. **Always move hidden files too** (`mv src/.* dest/ 2>/dev/null`).

```bash
# Example: move all Demiurge folders
mv ~/Desktop/Demiurge* ~/Desktop/Projects/Demiurge_Trading/ 2>/dev/null
mv ~/Desktop/Demiurge\ * ~/Desktop/Projects/Demiurge_Trading/ 2>/dev/null
```

### 4. Handle Duplicates
Find and merge duplicates across locations:
```bash
find ~/Desktop -name "*KB*" -type d
find ~/Desktop -name "*compression*" -type d
```
**Rule**: Keep the most complete version (usually under `Projects/`), delete the rest.

### 5. Kill Daemon Processes Before Deleting
If a folder reappears after `rm -rf`, a process is recreating it:
```bash
ps aux | grep -i <folder_name>
pkill -9 -f <process_name>
# Then delete
```

Common culprits in this environment:
- `eni_kb_daemon` → recreates `ENI_KB/`
- `eni_master_compression_driver.py` → recreates `eni_compression/`
- `eni_impossible_swarm.py` → recreates `eni_compression/`

### 6. Verify Clean Desktop
```bash
ls -la ~/Desktop/
# Should show ONLY: 3D_Printing/ Apps/ Documents/ Projects/ Wallpapers/
```

### 7. Verify Projects Structure
```bash
tree ~/Desktop/Projects -L 2 -d
```

## Pitfalls
- **Spaces in folder names**: Quote or escape (`Demiurge\ Marketing`)
- **Symlinks**: `app.py -> /other/path` — move target, not link, or update link
- **Hidden files**: `.git`, `.venv`, `.env`, `.~lock.*` — move with `mv src/.* dest/`
- **Running processes**: Always `pkill` before `rm -rf` on daemon-managed dirs
- **Nested duplicates**: `Demiurge_Creed/Demiurge_Creed/` — flatten before moving

## Reference Files
- `references/daemon-process-list.md` — Known daemons that recreate folders
- `references/category-map.md` — Master mapping of folder name patterns → category