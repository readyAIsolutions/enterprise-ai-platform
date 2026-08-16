---
name: hermes-file-converter
description: Convert files between formats — images (Pillow 12.1.1), documents (LibreOffice 26.2 headless), audio/video (ffmpeg 8.0.1), archives (tar/gzip/7z), and data formats (CSV/JSON/XML/YAML). All tools pre-installed on this Ubuntu 26.04 box.
---

# Hermes File Converter

Universal file format conversion using pre-installed tools on this box:
Pillow for images, LibreOffice headless for documents, ffmpeg for media,
tar/gzip/7z for archives, and Python stdlib for data formats.

No ImageMagick (`convert`, `magick`) or pandoc installed — we use alternate
tools that achieve the same results without additional installs.

## Trigger Conditions

Use this skill when the user asks to:
- Convert images between formats (PNG ↔ JPG ↔ WebP ↔ BMP ↔ GIF ↔ TIFF)
- Resize, crop, or compress images
- Convert documents (DOCX ↔ PDF ↔ ODT ↔ TXT ↔ HTML)
- Convert or compress audio/video files
- Create or extract archives (tar.gz, zip, 7z)
- Convert data between CSV, JSON, XML, YAML formats

---

## SECTION A: Image Conversion (Pillow 12.1.1)

### A1. Basic format conversion

```python
from PIL import Image
img = Image.open("input.png")
img.save("output.jpg", quality=85)      # PNG → JPEG
img.save("output.webp", quality=80)      # PNG → WebP
img.save("output.bmp")                   # PNG → BMP
img.save("output.tiff", compression="lzw")  # PNG → TIFF
```

### A2. Resize images (maintain aspect ratio)

```python
from PIL import Image
img = Image.open("large.jpg")
width, height = img.size
new_width = 800
ratio = new_width / width
new_height = int(height * ratio)
img = img.resize((new_width, new_height), Image.LANCZOS)
img.save("resized.jpg", quality=85)
```

### A3. Batch convert all PNGs in a directory to WebP

```python
from PIL import Image
from pathlib import Path

src_dir = Path("/path/to/images")
for png_file in src_dir.glob("*.png"):
    img = Image.open(png_file)
    webp_file = png_file.with_suffix(".webp")
    img.save(webp_file, quality=80, method=6)
    print(f"  {png_file.name} -> {webp_file.name}")
```

### A4. Strip EXIF / reduce file size

```python
from PIL import Image
img = Image.open("photo_with_exif.jpg")
data = list(img.getdata())
clean = Image.new(img.mode, img.size)
clean.putdata(data)
clean.save("stripped.jpg", quality=75, optimize=True)
```

### A5. Create a thumbnail

```python
from PIL import Image
img = Image.open("huge_image.png")
img.thumbnail((300, 300), Image.LANCZOS)  # preserves aspect ratio
img.save("thumbnail.jpg", quality=80)
```

---

## SECTION B: Document Conversion (LibreOffice 26.2 headless)

LibreOffice headless is the Swiss Army knife for document conversion. It handles
DOCX, PDF, ODT, TXT, HTML, RTF, and more — no pandoc needed.

### B1. Convert anything to PDF

```bash
# DOCX → PDF
libreoffice --headless --convert-to pdf input.docx --outdir /tmp/

# ODT → PDF
libreoffice --headless --convert-to pdf report.odt

# HTML → PDF
libreoffice --headless --convert-to pdf page.html

# TXT → PDF
libreoffice --headless --convert-to pdf notes.txt
```

Output file lands in the same directory as input (or `--outdir`).

### B2. Convert DOCX to ODT or plain text

```bash
# DOCX → ODT
libreoffice --headless --convert-to odt input.docx

# DOCX → TXT (plain text extract)
libreoffice --headless --convert-to "txt:Text" input.docx
```

### B3. Convert PDF to DOCX

```bash
libreoffice --headless --convert-to docx document.pdf
```

Note: Complex PDF layouts (multi-column, heavy graphics) may not convert
perfectly. This is a limitation of LibreOffice's PDF import, not the command.

### B4. Merge multiple DOCX into one PDF

```bash
# First merge in LibreOffice by opening all files, then export
libreoffice --headless --convert-to pdf file1.docx file2.docx file3.docx
# Each file gets its own PDF. To merge PDFs, use a Python tool:
python3 -c "
from pypdf import PdfMerger
merger = PdfMerger()
for f in ['file1.pdf', 'file2.pdf', 'file3.pdf']:
    merger.append(f)
merger.write('merged.pdf')
merger.close()
"
```

Note: `pypdf` may need `pip install pypdf`. If not available, merge the DOCX
files first by manually copying content.

### B5. Convert Markdown to PDF via LibreOffice

```bash
# LibreOffice can open .md files and convert:
libreoffice --headless --convert-to pdf README.md
```

### B6. Supported LibreOffice output filters

| Filter                | Extension | Notes                       |
|-----------------------|-----------|-----------------------------|
| `pdf`                 | .pdf      | Most reliable               |
| `docx`                | .docx     | Office Open XML             |
| `odt`                 | .odt      | OpenDocument                |
| `txt:Text`            | .txt      | Plain text (loses formatting) |
| `html`                | .html     | HTML export                 |
| `pptx`                | .pptx     | PowerPoint                  |
| `xlsx`                | .xlsx     | Excel spreadsheet           |

---

## SECTION C: Audio/Video Conversion (ffmpeg 8.0.1)

### C1. Convert video formats

```bash
# MKV → MP4 (copy streams, no re-encode — FAST)
ffmpeg -i input.mkv -c copy output.mp4

# Any format → MP4 (re-encode with H.264)
ffmpeg -i input.webm -c:v libx264 -preset medium -crf 23 -c:a aac -b:a 128k output.mp4

# MOV → MP4
ffmpeg -i input.mov -c:v libx264 -crf 23 output.mp4

# WebM → MP4
ffmpeg -i input.webm -c:v libx264 -crf 23 -c:a aac output.mp4
```

### C2. Extract audio from video

```bash
# Extract to MP3
ffmpeg -i video.mp4 -vn -c:a libmp3lame -q:a 2 audio.mp3

# Extract to WAV (lossless)
ffmpeg -i video.mp4 -vn -c:a pcm_s16le audio.wav

# Extract to AAC/M4A
ffmpeg -i video.mp4 -vn -c:a aac -b:a 192k audio.m4a
```

### C3. Convert audio formats

```bash
# WAV → MP3
ffmpeg -i input.wav -c:a libmp3lame -b:a 320k output.mp3

# FLAC → MP3
ffmpeg -i input.flac -c:a libmp3lame -q:a 2 output.mp3

# MP3 → WAV
ffmpeg -i input.mp3 output.wav

# OGG → MP3
ffmpeg -i input.ogg -c:a libmp3lame output.mp3
```

### C4. Compress/resize video

```bash
# Reduce to 720p
ffmpeg -i input.mp4 -vf "scale=-2:720" -c:v libx264 -crf 23 -preset medium -c:a aac -b:a 128k output_720p.mp4

# Target specific file size (2-pass encoding)
# Pass 1
ffmpeg -i input.mp4 -c:v libx264 -b:v 1000k -pass 1 -an -f null /dev/null
# Pass 2
ffmpeg -i input.mp4 -c:v libx264 -b:v 1000k -pass 2 -c:a aac -b:a 128k output.mp4

# Simple CRF-based (lower CRF = better quality, higher = smaller)
# CRF 18 = near lossless, CRF 23 = default, CRF 28 = small file
ffmpeg -i input.mp4 -c:v libx264 -crf 28 -preset slower output_compressed.mp4
```

### C5. Trim / cut video without re-encoding

```bash
# Cut from 00:30 to 02:00 (fast, no re-encode)
ffmpeg -ss 00:00:30 -i input.mp4 -to 00:02:00 -c copy output_cut.mp4
```

### C6. Get media info (ffprobe)

```bash
ffprobe -v quiet -print_format json -show_format -show_streams video.mp4
```

---

## SECTION D: Archive Creation & Extraction

### D1. tar.gz (most common on Linux)

```bash
# Create: compress a directory
tar -czf archive.tar.gz /path/to/directory/

# Extract
tar -xzf archive.tar.gz

# List contents without extracting
tar -tzf archive.tar.gz

# Extract to specific directory
tar -xzf archive.tar.gz -C /target/dir/
```

### D2. zip (cross-platform)

```bash
# Create
zip -r archive.zip /path/to/directory/

# Extract
unzip archive.zip -d /target/dir/

# List contents
unzip -l archive.zip
```

### D3. 7z (highest compression)

```bash
# Create with maximum compression
7z a -mx=9 archive.7z /path/to/directory/

# Extract
7z x archive.7z -o/target/dir/

# List contents
7z l archive.7z
```

### D4. gzip / bzip2 (single files)

```bash
# Compress single file
gzip large_file.txt          # produces large_file.txt.gz

# Decompress
gunzip large_file.txt.gz     # or: gzip -d large_file.txt.gz

# Keep original when compressing
gzip -k large_file.txt
```

---

## SECTION E: Data Format Conversion (Python stdlib)

### E1. JSON → CSV

```python
import json, csv

with open('data.json') as f:
    data = json.load(f)

# Assumes data is a list of dicts with consistent keys
if isinstance(data, list) and len(data) > 0:
    with open('data.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
    print(f"Converted {len(data)} rows to data.csv")
```

### E2. CSV → JSON

```python
import csv, json

with open('data.csv') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

with open('data.json', 'w') as f:
    json.dump(rows, f, indent=2)
print(f"Converted {len(rows)} rows to data.json")
```

### E3. JSON → YAML

```python
import json, yaml

with open('data.json') as f:
    data = json.load(f)

with open('data.yaml', 'w') as f:
    yaml.dump(data, f, default_flow_style=False, sort_keys=False)
```

### E4. YAML → JSON

```python
import yaml, json

with open('data.yaml') as f:
    data = yaml.safe_load(f)

with open('data.json', 'w') as f:
    json.dump(data, f, indent=2)
```

### E5. XML to JSON (with stdlib)

```python
import xml.etree.ElementTree as ET
import json

def xml_to_dict(element):
    result = {}
    for child in element:
        if len(child) == 0:
            result[child.tag] = child.text or ""
        else:
            result[child.tag] = xml_to_dict(child)
    return result

tree = ET.parse('data.xml')
root = tree.getroot()
data = {root.tag: xml_to_dict(root)}

with open('data.json', 'w') as f:
    json.dump(data, f, indent=2)
```

### E6. Excel (.xlsx) to CSV via LibreOffice

```bash
# Convert XLSX to CSV
libreoffice --headless --convert-to csv input.xlsx --outdir /tmp/
```

---

## SECTION F: PDF Manipulation (Pillow + Python)

### F1. Convert PDF pages to images

```python
# Requires: pip install pypdf2 (or pdf2image + poppler)
# Without extra deps, use this approach:
from PIL import Image

# If you have a single-page PDF, LibreOffice can convert it:
# libreoffice --headless --convert-to png document.pdf
# Then use Pillow:
img = Image.open("document.png")
img.save("document.jpg", quality=85)
```

### F2. Extract text from PDF via LibreOffice

```bash
# Convert to text
libreoffice --headless --convert-to "txt:Text" document.pdf
cat document.txt
```

---

## Pitfalls

1. **No ImageMagick**: This box has Pillow but NOT ImageMagick (`convert`/`magick`).
   Always use Python + Pillow for image operations, not `convert` commands.

2. **No pandoc**: Use LibreOffice headless for document conversion instead.
   LibreOffice handles DOCX→PDF, ODT→PDF, HTML→PDF, TXT→PDF, and more.

3. **LibreOffice lock files**: If a previous LO process crashed, you may see
   `.~lock.filename#` files. Delete them before retrying:
   ```bash
   find . -name '.~lock.*' -delete
   ```

4. **LibreOffice is slow to start**: First invocation takes 2-4 seconds as the
   process initializes. Batch multiple conversions in one command to amortize:
   ```bash
   libreoffice --headless --convert-to pdf *.docx
   ```

5. **ffmpeg overwrites without asking**: Always use `-n` (never overwrite) or
   check that the output file doesn't exist before converting.

6. **ffmpeg codec availability**: `libmp3lame` for MP3 encoding and `libx264`
   for H.264 are included in this Ubuntu 26.04 ffmpeg build. If a codec is
   missing, ffmpeg will tell you clearly.

7. **Pillow plugin for WebP**: Pillow 12.1.1 supports WebP natively. No extra
   install needed.

8. **Large video re-encodes can take hours**: Always warn the user and offer
   `-c copy` (stream copy, no re-encode) when possible. Use `-preset ultrafast`
   for quick drafts.

9. **tar with absolute paths**: `tar -czf` preserves absolute paths by default,
   which can be dangerous on extraction. Use `-C` to change directory or provide
   relative paths:
   ```bash
   tar -czf archive.tar.gz -C /path/to parent_dir/
   ```

10. **CSV dialect issues**: Different tools expect different CSV delimiters.
    Python's `csv.Sniffer` can auto-detect:
    ```python
    with open('unknown.csv') as f:
        dialect = csv.Sniffer().sniff(f.read(1024))
        f.seek(0)
        reader = csv.reader(f, dialect)
    ```

## Verification

```bash
# Test image conversion
python3 -c "
from PIL import Image
img = Image.new('RGB', (100, 100), color='red')
img.save('/tmp/test_convert.png')
img2 = Image.open('/tmp/test_convert.png')
img2.save('/tmp/test_convert.jpg', quality=85)
from pathlib import Path
print(f'PNG: {Path(\"/tmp/test_convert.png\").stat().st_size} bytes')
print(f'JPG: {Path(\"/tmp/test_convert.jpg\").stat().st_size} bytes')
print('Image conversion: OK')
"

# Test document conversion
echo "Hello World" > /tmp/test_doc.txt
libreoffice --headless --convert-to pdf /tmp/test_doc.txt --outdir /tmp/ 2>&1
ls -la /tmp/test_doc.pdf && echo "Document conversion: OK"

# Test ffmpeg
ffmpeg -f lavfi -i color=c=black:s=32x32:d=1 -c:v libx264 -t 1 /tmp/test_video.mp4 -y 2>&1 | tail -1
ls -la /tmp/test_video.mp4 && echo "Video encoding: OK"

# Cleanup
rm -f /tmp/test_convert.png /tmp/test_convert.jpg /tmp/test_doc.txt /tmp/test_doc.pdf /tmp/test_video.mp4
```
