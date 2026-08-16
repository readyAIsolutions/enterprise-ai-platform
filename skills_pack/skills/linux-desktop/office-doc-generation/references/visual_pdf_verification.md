# Visual PDF verification (defect-check technique)

When you generate a designed PDF (ReportLab, two-column, etc.) you MUST visually
verify it. Text-layer greps and page counts lie — a 1-page PDF can still have
cut-off text, leaked/scrambled text, or a near-empty trailing page that greps
won't catch.

## The vision-model summarization trap
If you render the PDF to PNG and ask a vision model "critique this resume /
does it look professional?", it will often return a generic SUMMARY of the
content and SKIP the defect checklist (overlap, cutoff, empty gaps, contrast).
This wastes a round and ships a broken layout.

## Fix: crop + narrow question (when vision is available)
1. Render at decent res: `pdftoppm -png -r 200 file.pdf /tmp/preview`
2. Crop the region in question and ask ONLY about it:
   ```python
   from PIL import Image
   im = Image.open('/tmp/preview-1.png'); w,h = im.size
   im.crop((0, int(h*0.72), w, h)).save('/tmp/preview_bottom.png')  # bottom strip
   im.crop((0, 0, int(w*0.32), h)).save('/tmp/preview_side.png')    # sidebar
   ```
3. Ask a narrow question, e.g. "Read aloud every line in this sidebar from top to
   bottom; note exactly where there is a blank gap with no text." Narrow > generic.

## Fix: PIXEL-BAND SCAN (works when vision is DOWN — used this session)
`vision_analyze` can 404 ("no endpoints support image input"). Do NOT stall — you
can detect the layout bugs with pure Pillow. Scan text-density per horizontal band
and per column:

```python
from PIL import Image
im = Image.open('/tmp/preview-1.png').convert('RGB'); w,h = im.size
bg = im.getpixel((int(w*0.05), int(h*0.45)))   # sample the sidebar bg color
def is_text(px):
    return not (abs(px[0]-bg[0])<35 and abs(px[1]-bg[1])<35 and abs(px[2]-bg[2])<35) \
           and not (px[0]>240 and px[1]>240 and px[2]>240)
for frac in (0.20, 0.45):        # 0.20 = sidebar text column, 0.45 = main column
    x = int(w*frac); prev = 0
    for y0 in range(0, h, 120):
        cnt = sum(1 for y in range(y0, min(y0+120, h)) if is_text(im.getpixel((x, y))))
        gap = ' GAP' if prev > 3 and cnt == 0 else ''
        print(f'x={frac} y={y0:4d} t={cnt}{gap}'); prev = cnt
```

Interpretation:
- **CRITICAL: scan at x≈20% of width, NOT x≈4-6%.** The far-left band is the frame's
  LEFT MARGIN (leftPadding=LM) and is ALWAYS blank there — scanning it gives false
  "GAP" alarms and sends you chasing a non-bug. Real sidebar text lives ~15-25% in.
- Sidebar column (x≈0.20) should be CONTINUOUS top→bottom. A zero-text band in the
  MIDDLE = the two-frame overflow bug (sidebar leaked into main). Fix per SKILL.md:
  move summary/education/references OUT of the sidebar into the main column.
- Bottom-most text: `for y in range(h-1,0,-1): if is_text(...): last=y; break`.
  `last/h*11` = inches from top on Letter; want the last real text ≤ ~10.3" (leaves a
  clean bottom margin, no cutoff). Blank below that is just margin, not a defect.
- Also confirm page count: `open(pdf,'rb').read().count(b'/Type /Page') - count(b'/Type /Pages')`.

## What to check on a designed resume specifically
- Sidebar text LEAKING into the main column / a mid-page blank band (two-frame
  overflow). Fix: shorten the sidebar — keep only name+contact+skills there, move
  summary/education/references to the main column.
- Near-empty TRAILING PAGE or big empty gap at the bottom of the main column.
  Fix: trim SPACING first (margins, spacers), not fonts (keep ≥9pt).
- Low-contrast / "see-through" sidebar text. Fix for this user: LIGHT-blue sidebar
  bg (#cfe0f2) + DARK text (#0d2236 / #0b3d6b). Verify objectively: sample a text
  pixel vs bg — text avg should be clearly dark (e.g. RGB ~(30,40,60)), not near-bg.
- The PDF VIEWER's own chrome (page tabs, "Page 2 of 2") is NOT part of your document.

## Pipe: re-verify after EVERY edit
After patching content and re-running the builder, re-render and re-scan. A content
edit that shifts text can re-trigger overflow. Also: if a build ERRORS, the old PDF
stays on disk — always check the builder's exit code / "PDF built" line before
trusting a re-render, or you'll be inspecting a stale file.
