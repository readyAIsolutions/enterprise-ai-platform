# Forge 3D Pipeline — Blender + FreeCAD + OpenSCAD

The Demiurge3D forge now uses three generators routed by part archetype.
All run headless on LO's box.

## Architecture

```
User text prompt
    │
    ▼
project_assembler.decompose()  ← splits into fitting parts with tolerances
    │
    ├── freecad:bracket  →  freecad_gen.py  →  FreeCAD AppImage (parametric mechanical)
    ├── freecad:hinge    →  freecad_gen.py
    ├── freecad:box      →  freecad_gen.py
    ├── freecad:pin      →  freecad_gen.py
    ├── blender:mask     →  blender_gen.py  →  Blender 5.0 (organic/sculpted)
    ├── blender:drone    →  blender_gen.py
    ├── blender:vase     →  blender_gen.py
    └── (fallback)       →  OpenSCAD (simple primitives)
    │
    ▼
STL files in project dir  →  frontend shows result + files
```

## Files

| File | Role |
|------|------|
| `forge/project_assembler.py` | Decomposes text → part manifest with dimensions, tolerances, connections |
| `forge/freecad_gen.py` | Headless FreeCAD parametric generator (bracket, hinge, box, pin) |
| `forge/blender_gen.py` | Headless Blender organic generator (mask, drone, vase, gear) |
| `forge/pipeline.py` | Old OpenSCAD-based pipeline (fallback for basic shapes) |

## API Entry Point

`POST /api/forge/swarm-build` with `{"spec": {"description": "rave mask from anime Berserk"}}`

The swarm-build endpoint was updated (2026-07-23) to:
1. Run `project_assembler.decompose()` to get an intelligent part manifest
2. Route each part to the correct generator (FreeCAD for mechanical, Blender for organic)
3. Collect STLs into a project directory
4. Return `{ok, project_dir, files, parts, summary}`

Fallback: if no description is provided, falls through to old `swarm_design.to_forge_spec() +
pipeline.build()` path.

## Blender Headless Pattern

Blender 5.0.1 runs headless via:
```bash
blender --background --python forge/blender_gen.py
```

**Args file approach** (required — Blender 5.0.0+ doesn't pass `--` args cleanly):
Write `/tmp/blender_args.json` before invoking:
```json
{"prompt": "bracket 60x40x6 with 4 m3 holes", "out": "/tmp/out.stl"}
```

**API changes from Blender 4.x to 5.0:**
- `bpy.ops.wm.stl_export(use_selection=True)` → `export_selected_objects=True`
- `bpy.ops.object.delete(use_confirm=False)` crashes on empty scene → wrap in `if bpy.context.scene.objects:`
- The `--` separator for script args is broken → use JSON file + read in `__main__`

See `references/blender_headless.md` for the full script template.

## FreeCAD Headless Pattern

FreeCAD 1.0.2 AppImage at `~/Apps/3d-tools/FreeCAD.AppImage`:
```bash
echo 'import FreeCAD; ...' | ~/Apps/3d-tools/FreeCAD.AppImage --console
```
Or pipe a script: `~/Apps/3d-tools/FreeCAD.AppImage --console /tmp/script.py`

The script must call `App.closeDocument()` to exit cleanly (otherwise stays in
interactive console mode and times out). Wrap with `timeout 120` — headless
operations should complete in under 30s for typical parts.

## Pitfalls

1. **FreeCAD AppImage is 760MB.** Download takes ~30s on LO's connection.
   Install to `~/Apps/3d-tools/` — the forge looks here.

2. **`--run` is ambiguous in FreeCAD 1.0** — use `--console <script.py>` instead.

3. **OrcaSlicer detection** — added AppImage path to `_ORCA_CANDIDATES` in `forge/slicer.py`:
   `/home/hunter/Apps/3d-tools/OrcaSlicer.AppImage`

4. **OrcaSlicer v2.4.2 ships aarch64 + x86_64 separately.** Filter GitHub assets
   for `'Linux' in name and 'AppImage' in name and 'aarch64' not in name`.
