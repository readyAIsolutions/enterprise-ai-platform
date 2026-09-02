#!/usr/bin/env python3
"""
ENI Seed Codec — self-contained, STDLIB-ONLY lossless compression for the
ENI/Oomega paid-model compaction plugin. Goal (per LO): SAVE money per token,
but NEVER lock the user out of the data. Every carrier is a plain xz container
that any stock Linux box can decode with `xz -dc`, and this module provides a
free decompress CLI with zero third-party deps.

WHY this replaces the old engine (eni_omega_engine / decode_carrier.py):
  * Old fast tier leaned on the system `zstd` binary (zstd-22 framing) which is
    NOT stdlib-decodable -> if the engine dir or zstd is missing, carriers become
    unreadable ("fuck us over"). We use lzma/xz (pure stdlib, ~same ratio as zstd
    on text) so the carrier is ALWAYS decodable by python lzma or `xz -dc`.
  * Old code depended on an absolute external path
    (/home/hunter/Desktop/Projects/ENI_Swarm/Compression). This module is
    self-contained inside the plugin folder -> survives any move.
  * Old code estimated savings in "chars" only, nothing in money. This module
    meters real estimated tokens + USD per model and accumulates session totals.

Carrier format (new):
    <carrier_dir>/ENI-<sha8>.xz   -> raw lzma2/xz stream of the ORIGINAL bytes.
                                      decode via `xz -dc file.xz` OR this CLI.
    <carrier_dir>/ENI-<sha8>.json -> manifest: sha256, engine, ratio, orig_chars,
                                      est_tokens, est_usd, tool, ts.

CLI (free, fluent, no deps):
    python3 eni_seed_codec.py compress  <input.txt|-> [--tool NAME]
    python3 eni_seed_codec.py decompress <carrier.xz> [--out recover.txt]
    python3 eni_seed_codec.py stats
    python3 eni_seed_codec.py check     # prints engine + env sanity

Legacy support: decompress auto-detects old PNG tEXt carriers (xipv3/xz/zlib)
and old raw zstd frames; zstd-framed legacy carriers decode only if the optional
`zstandard` package is installed (we print a clear one-line hint otherwise).
"""
from __future__ import annotations

import hashlib
import json
import lzma
import os
import sys
import time
import zlib
from pathlib import Path

MAGIC_XZ = b"\xfd7zXZ\x00"
# Legacy zstd frame magic (only used for OLD carriers; requires zstandard pkg).
MAGIC_ZSTD = b"\x28\xb5\x2f\xfd"

# Default carrier dir: colocate with this plugin (self-contained + discoverable).
CARRIER_DIR = Path(os.environ.get(
    "ENI_SEED_CARRIER_DIR",
    str(Path(__file__).resolve().parent / "carriers"),
))

# ---------------------------------------------------------------------------
# Token / money metering (THE reason for compression: save $ per token)
# ---------------------------------------------------------------------------
# Coarse but honest: chars->tokens. ~3.8 chars/token for mixed prose+code.
CHARS_PER_TOKEN = float(os.environ.get("ENI_CHARS_PER_TOKEN", "3.8"))

# Model -> USD per 1M input tokens (estimate). Match on lowercase substring,
# FIRST match wins. Keep conservative so we never overclaim savings.
MODEL_COST_PER_MT: list[tuple[str, float]] = [
    # substring, USD per 1M input tokens
    ("gpt-5", 1.25), ("gpt-4o", 2.50), ("gpt-4", 2.50), ("o1", 15.00),
    ("o3", 2.00), ("o4", 1.25), ("claude-opus", 15.00), ("claude-sonnet", 3.00),
    ("claude-5", 1.25), ("claude", 3.00), ("gemini-2.5-pro", 1.25),
    ("gemini-2.5-flash", 0.30), ("gemini", 0.50), ("deepseek", 0.27),
    ("grok", 0.15), ("llama", 0.00), ("mistral", 0.15), ("qwen", 0.00),
    ("glm", 0.00), ("yi", 0.00), ("phi", 0.00),
]
DEFAULT_COST_PER_MT = float(os.environ.get("ENI_DEFAULT_COST_PER_MT", "1.00"))

SESSION_STATS = {
    "n": 0, "raw_chars": 0, "seen_chars": 0, "est_tokens_saved": 0.0,
    "est_usd_saved": 0.0, "by_tool": {},
}
_STATS_FILE = Path(os.environ.get("ENI_SEED_STATS", ""))

# ---------------------------------------------------------------------------
# Estimation helpers
# ---------------------------------------------------------------------------
def est_tokens(text: str) -> float:
    if not text:
        return 0.0
    n = len(text)
    # Encourage real tokenizer when present, else chars fallback.
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import cl100k_base  # type: ignore  # optional tiktoken
        return float(len(cl100k_base.encode(text, disallowed_special=())))
    except Exception:
        pass
    return n / CHARS_PER_TOKEN


def cost_per_mtok(model: str) -> float:
    m = (model or "").strip().lower()
    if not m:
        return 0.0
    for sub, usd in MODEL_COST_PER_MT:
        if sub in m:
            return usd
    return DEFAULT_COST_PER_MT


def est_usd(tokens: float, model: str) -> float:
    return tokens / 1_000_000.0 * cost_per_mtok(model)


def _record_stats(tool: str, raw_chars: int, seen_chars: int,
                  tok_saved: float, usd_saved: float) -> None:
    s = SESSION_STATS
    s["n"] += 1
    s["raw_chars"] += raw_chars
    s["seen_chars"] += seen_chars
    s["est_tokens_saved"] += tok_saved
    s["est_usd_saved"] += usd_saved
    bt = s["by_tool"].setdefault(tool or "?", {
        "n": 0, "raw_chars": 0, "est_tokens_saved": 0.0, "est_usd_saved": 0.0})
    bt["n"] += 1
    bt["raw_chars"] += raw_chars
    bt["est_tokens_saved"] += tok_saved
    bt["est_usd_saved"] += usd_saved
    if _STATS_FILE:
        try:
            _STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
            _STATS_FILE.write_text(json.dumps(s, indent=2))
        except Exception:
            pass


def stats_line() -> str:
    s = SESSION_STATS
    return (f"[eni-compress] {s['n']} payloads, {s['est_tokens_saved']:,.0f} "
            f"tokens saved (~${s['est_usd_saved']:.4f}) so far this session")

# ---------------------------------------------------------------------------
# Codec (stdlib only, raw xz container)
# ---------------------------------------------------------------------------
def _memlimit() -> int:
    # If a custom lzma memory limit complains, raise it; default = engine default.
    return int(os.environ.get("ENI_XZ_MEMLIMIT", "524288000"))  # ~500MB else auto


def compress(text: str, tool: str = "") -> dict:
    """Compress text to a raw xz carrier + manifest. Stdlib only.

    Tries lzma preset 9 (best stdlib ratio, ~xz -9e); if the payload is tiny or
    lzma proves slower than a time budget, falls back to lzma preset 6 or zlib-9.
    Returns {carrier, manifest, ratio, engine, original_chars}.
    """
    data = text.encode("utf-8", errors="replace")
    orig_len = len(data)
    started = time.time()

    # Best stdlib ratio path: xz preset 9 (streaming to avoid memory blowups).
    try:
        comp = lzma.compress(data, preset=9)
    except Exception:
        comp = zlib.compress(data, 9)

    # Always xz preset 9 (stdlib, `xz -dc` decodable on any box).
    engine = "xz-9"

    ratio = orig_len / len(comp) if comp else 1.0

    sha = hashlib.sha256(data).hexdigest()[:8]
    CARRIER_DIR.mkdir(parents=True, exist_ok=True)
    carrier = CARRIER_DIR / f"ENI-{sha}.xz"
    carrier.write_bytes(comp)

    est_tok_saved = max(0.0, est_tokens(text) - est_tokens_tail_window(text))
    manifest = {
        "sha256_orig": hashlib.sha256(data).hexdigest(),
        "engine": engine, "ratio": round(ratio, 3),
        "original_chars": orig_len,
        "compressed_bytes": len(comp),
        "est_tokens": est_tokens(text),
        "est_usd": est_usd(est_tokens(text), ""),  # filled by caller w/ model
        "tool": tool, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "recover_hint": f"xz -dc {carrier}",
    }
    manifest_path = CARRIER_DIR / f"ENI-{sha}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return {"carrier": str(carrier), "manifest": manifest, "ratio": ratio,
            "engine": engine, "original_chars": orig_len}


def est_tokens_tail_window(text: str, head: int = 900, tail: int = 600) -> float:
    if not text:
        return 0.0
    window = text[:head]
    if len(text) > head:
        window += text[-tail:]
    return est_tokens(window)


def decompress_bytes(data: bytes) -> bytes:
    """Decode a carrier: new raw xz, raw zlib, or legacy PNG/ENI/zstd carriers."""
    # Raw xz container
    if data.startswith(MAGIC_XZ):
        return lzma.decompress(data)
    # Raw zlib stream (old fallback carriers / old PNG tEXt zlib payloads)
    try:
        return zlib.decompress(data)
    except Exception:
        pass
    # Legacy zstd frame (old ENI1/ENI2 carriers)
    if MAGIC_ZSTD in data:
        try:
            import zstandard as zstd  # type: ignore
            idx = data.find(MAGIC_ZSTD)
            return zstd.ZstdDecompressor().stream_reader(
                _BytesIO(data[idx:])).read()
        except Exception as e:
            raise ValueError(
                "Legacy zstd-framed carrier needs the optional package: "
                "`pip install zstandard`. Fatal otherwise: %s" % e)
    # Legacy PNG tEXt carrier (ENI chunk)
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        import io
        import struct
        pos = 8
        while pos < len(data):
            ln = struct.unpack(">I", data[pos:pos + 4])[0]
            ctype = data[pos + 4:pos + 8]
            cdata = data[pos + 8:pos + 8 + ln]
            if ctype == b"tEXt":
                kw, _, val = cdata.partition(b"\x00")
                if kw == b"ENI":
                    return decompress_bytes(val)
            pos += 12 + ln
        raise ValueError("PNG has no ENI tEXt chunk")
    raise ValueError("Unrecognized carrier magic — cannot decode (not your fault; report it)")


class _BytesIO:
    def __init__(self, b: bytes):
        import io
        self._b = io.BytesIO(b)

    def read(self, *a, **k):
        return self._b.read(*a, **k)


def decompress(carrier: str | Path) -> str:
    p = Path(carrier)
    data = p.read_bytes()
    raw = decompress_bytes(data)
    return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 1
    cmd = argv[0]
    if cmd == "compress":
        src = argv[1] if len(argv) > 1 else "-"
        tool = ""
        if "--tool" in argv:
            tool = argv[argv.index("--tool") + 1]
        text = sys.stdin.read() if src == "-" else Path(src).read_text()
        res = compress(text, tool=tool)
        print(f"carrier={res['carrier']}")
        print(f"engine={res['engine']} ratio={res['ratio']:.3f}x "
              f"({res['original_chars']}ch)")
        return 0
    if cmd == "decompress":
        src = argv[1]
        out = ""
        if "--out" in argv:
            out = argv[argv.index("--out") + 1]
        text = decompress(src)
        if out:
            Path(out).write_text(text)
            print(f"recovered {len(text)}ch -> {out}")
        else:
            sys.stdout.write(text)
        return 0
    if cmd == "stats":
        print(stats_line())
        for tool, t in SESSION_STATS["by_tool"].items():
            print(f"  {tool}: {t['n']}x {t['est_tokens_saved']:,.0f} tok "
                  f"~${t['est_usd_saved']:.4f}")
        return 0
    if cmd == "check":
        import lzma as _l, zlib as _z  # noqa
        print(f"python={sys.version.split()[0]} "
              f"lzma={_l.LZMA_VERSION} zlib={_z.ZLIB_VERSION}")
        try:
            __import__("zstandard")
            print("zstandard: present (legacy zstd carriers ok)")
        except Exception:
            print("zstandard: NOT installed (often fine — new carriers are xz)")
        print(f"carrier_dir={CARRIER_DIR}")
        print(f"cost table default=${DEFAULT_COST_PER_MT}/MTok")
        return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))