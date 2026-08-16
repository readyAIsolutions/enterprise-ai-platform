#!/usr/bin/env python3
"""Recover source from an ENI compression carrier PNG.

Usage:
    python3 recover_carrier.py /path/to/carrier_<hash>.png > out.py

Tool outputs in this environment come back wrapped in
`<ENI-COMPRESSED ... carrier=/path/to/carrier_<hash>.png ...>`. The full
lossless content is inside that carrier. This script extracts it.

Format (discovered by reverse-engineering, see
references/recovering-eni-carriers.md): the 1x1 PNG carries a `tEXt` chunk
(keyword `ENI`) whose value is
`[4B len]["ENI2"][1B name-len]["xz-9e"][xz stream from magic FD 37 7A 58 5A 00]`.
Decompress with FORMAT_XZ; the payload is JSON `{"content":"   1|...\n..."}`
with per-line `N|` prefixes that are stripped here.

Do NOT use engine.py's CLI (its PAQ8PXCompressor errors out before extract).
"""
import json
import lzma
import struct
import sys


def read_png_textext(path):
    data = open(path, "rb").read()
    pos, chunks = 8, []
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        ct = data[pos + 4:pos + 8].decode("latin1")
        cdata = data[pos + 8:pos + 8 + ln]
        chunks.append((ct, cdata))
        pos += 12 + ln
    return chunks


def recover(carrier):
    for ctype, cdata in read_png_textext(carrier):
        if not ctype.startswith("tEXt"):
            continue
        nul = cdata.find(b"\x00")
        val = cdata[nul + 1:]
        mi = val.find(b"\xfd7zXZ\x00")  # xz magic
        if mi < 0:
            continue
        out = lzma.decompress(val[mi:], format=lzma.FORMAT_XZ)
        content = json.loads(out)["content"]
        return "\n".join(line.split("|", 1)[1] if "|" in line else line
                         for line in content.split("\n"))
    raise SystemExit("no ENI tEXt/xz payload found in " + str(carrier))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.stdout.write(recover(sys.argv[1]))
