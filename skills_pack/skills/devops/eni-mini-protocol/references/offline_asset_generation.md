# Offline asset / preview generation (pure stdlib)

Proven in DEMIURGE3D `backend/demiurge/models/model_library.py` (ENI mini B05, 2026-07-11).
No Pillow / numpy / OpenSCAD / display required — `zlib` + `struct` + `array` only. The
whole thing is fully offline-testable (pytest, no network, no GPU).

## When to use
- Generate model thumbnails / contact sheets in CI or a headless agent runtime.
- Build a catalog/preview layer over STL/3MF output (the ADD-ONLY sub-task pattern).
- Any task that needs a viewable PNG but cannot depend on Pillow.

## PNG encoder (RGB, 8-bit, filter type 0, no dependencies)
```python
import struct, zlib

def encode_png(fb: bytes, size: int) -> bytes:
    """fb = raw RGB bytes, length size*size*3. Returns PNG bytes."""
    W = H = size
    if len(fb) != W * H * 3:
        raise ValueError(f"fb size {len(fb)} != {W*H*3}")
    raw = bytearray()
    stride = W * 3
    for y in range(H):
        raw.append(0)                      # filter type 0 (None) per scanline
        raw += fb[y * stride:(y + 1) * stride]
    comp = zlib.compress(bytes(raw), 9)

    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))  # 8-bit, color type 2 (RGB)
    png += chunk(b"IDAT", comp)
    png += chunk(b"IEND", b"")
    return png
```
Decoding for tests (no Pillow): assert `png[:8] == b"\x89PNG\r\n\x1a\n"`, walk chunks,
parse IHDR (depth==8, ctype==2), `zlib.decompress` IDAT, strip the leading filter byte per
scanline, and assert a non-background pixel ratio > 0.02 (proves non-blank).

## Minimal binary STL reader
```python
def read_stl(path):
    data = Path(path).read_bytes()
    n_tri = struct.unpack_from("<I", data, 80)[0]
    off = 84
    verts = []
    for _ in range(n_tri):
        vals = struct.unpack_from("<12f", data, off)      # normal(3) + 3 verts * xyz
        verts += [vals[3:6], vals[6:9], vals[9:12]]
        off += 50
    return verts, n_tri
```
ASCII STL: regex `vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)` (detect by
`data[:5].lstrip().lower().startswith(b"solid") and b"facet" in data[:2048]`). Deduplicate
vertices (round to 4 dp) for a clean triangle-index list; drop degenerate (a==b/c) triangles.

## Minimal 3MF reader (single object, core-2015-02 schema)
Zip member `3D/3dmodel.model`; parse `<vertices>/<vertex x y z>` and
`<triangles>/<triangle v1 v2 v3>` under `{ns}resources/{ns}object/{ns}mesh` (ns =
`http://schemas.microsoft.com/3dmanufacturing/core/2015/02`). Merge all objects into one
mesh for thumbnails/bbox. NOTE: this drops per-object identity + material/color — fine for
previews, insufficient for painted/multi-part assemblies.

## Software rasterizer (orthographic + z-buffer + two-sided Lambert)
- Center on centroid, rotate (Y then X), orthographic project `x*scale + W/2, H/2 - y*scale`.
- `scale = (min(W,H)/2 - margin) / (extent/2)` where extent = max bbox dim (fit to viewport).
- Per triangle: face normal in camera space, `shade = ambient + diffuse * |n . light|`
  (two-sided: abs), clamp RGB.
- Painter's algorithm with a per-pixel depth buffer (`array.array("f")`); for each triangle
  compute bounding box, barycentric test, keep the nearest fragment. Subsampling for speed:
  `tris = tris[::step]` with `step = len//max_tris` when triangle count is huge.

## Pitfall: a resolver that RAISES on missing files
If the module's `_resolve(rel)` raises `ModelLibraryError` (or any exception) when the file
is absent — instead of returning a non-existent `Path` — do NOT call
`self._resolve(x).exists()`; it throws before `.exists()` is reached. Wrap in try/except and
treat the exception as "missing":
```python
def _file_exists(self, entry):
    try:
        return self._resolve(entry.rel_path).exists()
    except ModelLibraryError:
        return False
gone = [e.id for e in self._entries.values() if not _file_exists(e)]
```
This is exactly the bug that produced RED in `prune_missing()` during B05 — fixed this way.
(Pyright note: resolve `_resolve_id()` to a local var with a `None`-guard before passing it
into a function that expects `str`, or the type checker flags `str | None`.)

## Verification gate (keep it in the test file)
- Decode the PNG (above) and assert signature + non-background ratio > 0.02 (non-blank).
- Determinism: same mesh + view + size => byte-identical framebuffer (catches uninitialized
  state). Different view => different bytes (proves the view matrix is applied).
- Perf: a 12-tri cube @64px iso should render in < 50 ms; expose `max_tris` subsample so
  high-poly models stay bounded.

## See also
- `eni-mini-protocol` SKILL.md — ADD-ONLY advance discipline, STATUS report format, and the
  stale-temp-dir smoke pitfall (a reused temp dir's leftover `library.json` can fake a bug).
