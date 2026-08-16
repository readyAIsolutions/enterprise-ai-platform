#!/usr/bin/env python3
"""
Decode an ENI/omega carrier PNG back to the full plain tool output.

On a PAID model, large read_file / terminal results come back wrapped as:
    <ENI-COMPRESSED ratio=...x carrier=/abs/path/carrier_<hash>.png>
        --- head ---
        <truncated head>
        --- tail ---
        <truncated tail>
    </ENI-COMPRESSED>

The carrier is NOT a normal LSB-steganography PNG. It is a tiny PNG whose
data lives in a tEXt chunk whose keyword is b"ENI" and whose value is
compressed bytes of the ORIGINAL tool output.

THREE carrier formats exist (pipeline keeps getting upgraded — handle ALL):
  1. ENI2 / xz: find XZ magic b"\xfd7zXZ\x00" ANYWHERE in value, lzma from
     there (ASCII header precedes magic). Stdlib lzma, no dep.
  2. ENI2 / zstd-22 (OBSERVED 2026-08-10): header "ENI2\x07zstd-22" then the
     zstd frame magic b"\x28\xb5\x2f\xfd" at an OFFSET (~20 bytes in), NOT
     offset 0. Decompressing from offset 0 gives "Unknown frame descriptor".
  3. ENI1 / zstd (LEGACY): raw zstd bytes, magic at offset 0.
Robust rule for BOTH zstd variants: search value for zstd magic anywhere,
decompress from that byte, else fall back to whole value.

Usage:
    python3 decode_carrier.py /abs/path/carrier_<hash>.png [carrier2.png ...]

Recovered text is written to stdout. Pipe to a file if you want to read it
in chunks without the transport re-compressing it.
"""
import io
import struct
import sys


def decode_carrier(path):
    with open(path, "rb") as f:
        data = f.read()
    pos = 8  # skip PNG signature + IHDR handled below
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        ctype = data[pos + 4:pos + 8]
        cdata = data[pos + 8:pos + 8 + length]
        if ctype == b"tEXt":
            kw, _, text = cdata.partition(b"\x00")
            if kw == b"ENI":
                # ENI2/xz variant: find XZ magic anywhere in the value.
                import lzma
                xz_magic = b"\xfd7zXZ\x00"
                idx = text.find(xz_magic)
                if idx >= 0:
                    return lzma.decompress(text[idx:])
                # zstd variants (ENI1 raw, OR ENI2/zstd-22 with the frame magic
                # at an OFFSET ~20 bytes in after the "ENI2\x07zstd-22" header).
                # Searching for the magic anywhere handles both. If you assume
                # offset 0 you get "Unknown frame descriptor" on the ENI2/zstd
                # variant (observed 2026-08-10).
                import zstandard as zstd
                zstd_magic = b"\x28\xb5\x2f\xfd"
                idx = text.find(zstd_magic)
                payload = text[idx:] if idx >= 0 else text
                d = zstd.ZstdDecompressor()
                return d.stream_reader(io.BytesIO(payload)).read()
        pos += 12 + length  # 4 len + 4 type + length + 4 crc
    raise ValueError(f"No ENI tEXt chunk found in {path}")


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    for p in argv:
        raw = decode_carrier(p)
        try:
            sys.stdout.write(raw.decode("utf-8"))
        except UnicodeDecodeError:
            sys.stdout.write(repr(raw))
        sys.stdout.write(f"\n=== END {p} ===\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))