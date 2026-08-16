# Sample previews & pack (lumen/samples_pack.py)

ADD-ONLY module (created by ENI mini B05 during the full-power parallel
build). Pure PIL + stdlib — no GPU / X11 / WebGL needed, so it runs in CI
and on the AppImage build host.

## Why it exists
PASS-5 claimed "8 real Lumen render stills linked as preview.png". On disk
those 8 are actually **flat 1-color solid blocks** (771 B, 640×360) — useless
as Library thumbnails — and the `image` sample shipped with **NO preview** at
all. `samples_pack.py` regenerates proper procedural previews and bundles the
sample set into a shippable pack.

## Module API (lumen/samples_pack.py)
- `render_preview(folder, manifest_dict, out_path, size=(640,360)) -> Path`
  Deterministic procedural still: brand gradient + seeded light-orbs +
  (shader/scene) sinusoidal bands + vignette + a bottom scrim with the
  wallpaper name + a kind badge (SHADER/VIDEO/IMAGE/WEB/SCENE). For
  `image` it downscales the real `wallpaper.png`; for `video` it tries an
  ffmpeg first-frame grab, else a faux play-glyph motif.
- `render_all_previews(root, size, overwrite=False) -> list[Path]`
  Refreshes previews across a samples tree. **Safe-by-default**: genuine
  multi-color renders are PRESERVED; only flat placeholders + missing
  previews are regenerated. `--overwrite` re-renders everything (would
  clobber the real renders — do NOT use in the normal build).
- `build_pack(root, out_dir, size, overwrite) -> dict`
  Refreshes previews, copies every sample folder into
  `<out_dir>/samples_pack/`, writes `samples_manifest.json`
  (name/version/preview_size/samples[]), then tars to
  `<out_dir>/samples_pack.tar.gz`. Returns tar path + manifest + the list
  of re-rendered previews.
- `extract_pack(tar_path, dest) -> int` — round-trip; returns the number
  of sample folders found.
- CLI: `python -m lumen.samples_pack [--root DIR] [--out DIR]
  [--size WxH] [--overwrite]`

## Flat-vs-genuine preview detection (the discriminator)
A *bad* placeholder is **≤16 distinct colors AND tiny bytes** (a 640×360
solid block is 771 B, 1 color). Genuine renders carry **thousands of
colors** — OR a **large byte size even when low-color** (a dark video frame
is only 165 colors but 503 KB). So the preserve rule keys off color count
(`FLAT_COLORS_MAX = 16`); the byte size is a secondary tell, not the gate.
Validate a preview headlessly with PIL:
```python
from PIL import Image
def is_flat(p, cap=16):
    with Image.open(p) as im:
        colors = im.convert("RGB").getcolors(maxcolors=100000)
    n = len(colors) if colors else 0
    return n <= cap
```
(NOTE: `getcolors` returns None if it exceeds `maxcolors` — always pass a
large cap and guard the None.)

## Hermetic asset-test trap (learned the hard way)
`render_all_previews` is ALSO the deliverable that you RUN against the live
`lumen/samples` to ship the fix. That run **mutates the repo** (writes the
new previews). If your pytest asserts repo state ("the `image` sample has no
preview", "this preview is a 1-color block"), the test GREENS once, then
REDS forever after the deliverable run, because the asset no longer matches
the assumption. **Fix: tests must construct their own fixtures** — in the
tmp copy, `unlink()` the preview to simulate "missing", or
`Image.new("RGB", size, color).save(p, "PNG")` to simulate a flat block —
then assert the generator's behavior. Never assert on pre-existing repo asset
state in an asset-generation test. Same trap applies to any generator you also
run in-place (store-art, gallery contact sheet, pack builder, etc.).
