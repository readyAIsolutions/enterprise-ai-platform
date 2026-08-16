# ENI carrier format — ENI2/xz upgrade (detected 2026-08-09)

The ENI/omega carrier pipeline upgraded its on-disk PNG format. Old decoders that only
handle the legacy zstd variant now FAIL on current carriers. This is the authoritative
decoder knowledge; `scripts/decode_carrier.py` implements it.

## How to tell which variant you have

- **ENI1 / zstd (legacy):** the tEXt value (keyword `b"ENI"`) is raw zstd-compressed bytes.
  `zstandard` required.
- **ENI2 / xz (current):** the tEXt value starts with a short ASCII header that contains
  the literal text `ENI2` and `xz`, followed by the XZ-compressed stream. The XZ magic
  bytes `b"\xfd7zXZ\x00"` appear somewhere mid-value (e.g. `...ENI2\x05xz-9e\xfd7...`).
  Decompress with Python stdlib `lzma` (no extra dep).

## Decode recipe (the part that actually matters)

Given the full PNG bytes, walk chunks by length prefix, find the tEXt chunk whose keyword
is `b"ENI"`, then:

```python
import lzma
xz_magic = b"\xfd7zXZ\x00"
idx = text.find(xz_magic)
if idx >= 0:
    out = lzma.decompress(text[idx:])          # ENI2/xz
else:
    import zstandard as zstd                    # ENI1/zstd fallback
    out = zstd.ZstdDecompressor().stream_reader(io.BytesIO(text)).read()
```

## The error tell

Recovering ENI2 content with a zstd-only decoder raises:

```
zstandard.backend_c.ZstdError: zstd decompress error: Unknown frame descriptor
```

**That error is not a broken carrier — it is the signal that the value is the xz variant.**
Decode with `lzma` (stdlib) instead. Do not conclude the PNG is corrupt or add dependencies
to chase the wrong codec.

## Checking the header without decompressing

```python
import io, struct
d = open("carrier_X.png", "rb").read(); pos = 8
while pos < len(d):
    ln = struct.unpack(">I", d[pos:pos+4])[0]; ct = d[pos+4:pos+8]
    if ct == b"tEXt":
        k, _, v = d[pos+8:pos+8+ln].partition(b"\x00")
        if k == b"ENI":
            print("header bytes:", v[:20])   # b'\x00...ENI2\x05xz-9e\xfd7...' -> xz variant
    pos += 12 + ln
```

`scripts/decode_carrier.py` in this skill auto-detects both. Prefer it over hand-rolling.