# Forge Geometry Debugging

Lessons from diagnosing why forge builds produce wrong shapes.

## PITFALL — Verify visually, never trust numbers alone

Blender sculpts can produce misleading numerical metrics. In one debug session, radial
CoV (coefficient of variation) measured 0.354 vs sphere ~0.03 — looked like a well-sculpted
mask on paper — but the user could SEE it was still an egg-shaped blob. Root cause: base
geometry was a UV sphere, deformations were too weak, and subsurf modifier rounded
everything back smooth.

**Rule: After changing forge geometry code, ALWAYS render at least one frame before
declaring victory.**

```python
# Minimal render check — run inside blender:
# blender -b --python render_check.py
import bpy
import sys

stl_path = sys.argv[-1]  # pass STL as last arg
bpy.ops.wm.stl_import(filepath=stl_path)
obj = bpy.context.active_object

# Position camera to face the object
bpy.ops.object.camera_add(location=(0, -200, 0))
cam = bpy.context.active_object
cam.rotation_euler = (1.5708, 0, 0)  # look along -Y

# Quick render
bpy.context.scene.render.filepath = '/tmp/forge_check.png'
bpy.context.scene.render.resolution_x = 800
bpy.context.scene.render.resolution_y = 600
bpy.ops.render.render(write_still=True)

# Bbox integrity check
dims = obj.dimensions
print(f'Bbox: {dims.x:.0f} x {dims.y:.0f} x {dims.z:.0f} mm')
```

If you can't render, at minimum: if a mask with 80mm nominal depth comes out at exactly
~80mm, the horns/snout didn't add any forward protrusion — the sculpt was cosmetic.
Real angular sculpt should push depth well past nominal.

## Forge motif/archetype routing diagnostic chain

When forge builds the wrong shape (plain mask instead of demon/Berserk), trace the
FULL routing chain. Every hop can silently drop params:

```
NL description
  → project_assembler._mask_parts() -- motif detection from keywords
    → decompose() -- forwards motif+style in part["params"]
      → server.py swarm-build dispatch -- forwards part["params"] to blender
        → blender_gen.gen_mask(motif=..., style=...) -- applies sculpt
```

Each hop fails independently:

| Hop | File | Line | What to check |
|-----|------|------|---------------|
| 1 | `project_assembler.py` | ~88 | regex matching: "berserk" → `motif="demon"`, `style="angular"` |
| 2 | `project_assembler.py` | ~299 | `_mask_parts()` must pass `motif` and `style` in the returned part dict |
| 3 | `server.py` | ~621 | build handler must forward `part["params"]` to `gen_mask(**params)` |
| 4 | `blender_gen.py` | ~1147 | `gen_mask()` must force `subsurf=0` when `style="angular"` |

Symptom when broken: "rave mask from Berserk" produces 150×100×80mm bbox (exactly
nominal, no horn protrusion) with spherical silhouette despite "sculpted" output.

## Blender cold-start timeout / missing STL pattern

Blender 5.x first launch after system boot compiles shaders (~90-120s cold start).
If the forge build timeout is 300s and Blender needs 120s cold + 180s sculpt, the
build times out mid-sculpt. The STL still flushes to disk AFTER the kill signal,
so the file EXISTS on disk but the part was marked FAILED and dropped from the
GUI file list.

**Fix pattern** (in build handler):
```python
# After timeout, grace-poll: check if STL landed despite killed process
for _ in range(10):
    if os.path.exists(expected_stl) and os.path.getsize(expected_stl) > 0:
        part["status"] = "completed"  # rescued from timeout
        break
    time.sleep(1)
# If rescued, retry once — Blender is now warm from first launch
```

## Calibration persistence

Calibration progress resets on page refresh because `calibrationProgress` in the
Zustand store wasn't persisted to localStorage.

**Fix:**
```javascript
// On every progress update, write to localStorage
localStorage.setItem('CAL_KEY', JSON.stringify(progress));

// On mount, hydrate from localStorage
const saved = localStorage.getItem('CAL_KEY');
if (saved) set({ calibrationProgress: JSON.parse(saved) });
```