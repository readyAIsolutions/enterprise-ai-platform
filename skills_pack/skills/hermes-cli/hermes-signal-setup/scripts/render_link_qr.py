#!/usr/bin/env python3
"""Render a sgnl://linkdevice URI into a scannable QR PNG.

Use a LIVE link-process URI (e.g. a fresh `signal-cli link -n X` captured to
/tmp/sg_link_uri.txt while that process is still running). A QR rendered from a
link process that has already exhited / timed out reads as "network error" on
the phone — re-run this after any link regeneration.

Usage:
    python render_link_qr.py <uri_file> <venv_python> [out_png]

Example:
    python render_link_qr.py /tmp/sg_link_uri.txt /home/user/.venvs/train/bin/python /home/user/signal-cli/signal_link_qr.png
"""
from __future__ import annotations

import subprocess
import sys

try:
    import qrcode  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - install in a venv per PEP-668
    print("qrcode not importable here; install in a venv: "
          "<venv>/bin/pip install qrcode[pil]")
    sys.exit(2)


def main() -> int:
    assert len(sys.argv) >= 2, "usage: render_link_qr.py <uri_file> [out_png]"
    uri_file = sys.argv[1]
    out_png = sys.argv[2] if len(sys.argv) > 2 else "signal_link_qr.png"
    try:
        uri = open(uri_file, encoding="utf-8").read().strip()
    except OSError as e:
        print(f"cannot read uri file {uri_file}: {e}")
        return 1
    if not uri:
        print("uri file is empty — is the link process still running and producing output?")
        return 1
    qr = qrcode.QRCode(border=4, box_size=12)
    qr.add_data(uri)
    qr.make()
    qr.make_image(fill="black", back_color="white").save(out_png)
    print(f"saved {out_png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
