"""
Tests for the pluggable codec registry + ratio negotiation
(modules/compression_bridge/codecs.py) and its integration into the
CompressionBridge.

Covers:
  - every built-in codec round-trips (decode(encode(x)) == x), incl. dicts
  - registry register / get / list / duplicate-error / unknown-key
  - best_codec negotiates a lossless codec for repetitive text and NOOP for
    incompressible / random payloads (deterministic tie-break)
  - negotiate_ratio reports saved_bytes and ratio
  - bridge integration + lifecycle (initialize / shutdown / factory)
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Coroutine

import pytest

# Make modules/ importable (same trick as the existing test_compression.py).
_MODULE_PARENT = Path(__file__).resolve().parent.parent.parent
if str(_MODULE_PARENT) not in sys.path:
    sys.path.insert(0, str(_MODULE_PARENT))

from compression_bridge import (  # noqa: E402
    Bz2Codec,
    CodecRegistry,
    CompressionBridge,
    GzipCodec,
    JsonCodec,
    NOOPCodec,
    XZCodec,
    negotiate_ratio,
)
from compression_bridge.codecs import Codec  # noqa: E402

REPETITIVE = b"the quick brown fox jumps over the lazy dog. " * 300
RANDOM = os.urandom(12000)
STRUCTURED = {
    "name": "compression_bridge",
    "version": "3.1.0",
    "tags": ["enterprise", "codec", "negotiation"],
    "nested": {"ok": True, "count": 42, "items": [1, 2, 3]},
}
TEXT = "Enterprise compression codec negotiation master class."

_BINARY_CODECS = [XZCodec(), GzipCodec(), Bz2Codec(), NOOPCodec()]


def _run(coro: Coroutine[Any, Any, Any]) -> object:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ── 1. Round-trips ─────────────────────────────────────────────────────────


def test_binary_codecs_round_trip_bytes() -> None:
    for codec in _BINARY_CODECS:
        assert codec.decode(codec.encode(REPETITIVE)) == REPETITIVE
        assert codec.decode(codec.encode(b"")) == b""
        assert codec.ratio(b"") == 1.0
    assert XZCodec().ratio(REPETITIVE) > 1.0


def test_binary_codecs_round_trip_str() -> None:
    for codec in _BINARY_CODECS:
        assert codec.decode(codec.encode(TEXT)) == TEXT.encode("utf-8")


def test_noop_is_identity() -> None:
    noop = NOOPCodec()
    assert noop.decode(noop.encode(RANDOM)) == RANDOM
    assert len(noop.encode(RANDOM)) == len(RANDOM)
    assert noop.ratio(RANDOM) == pytest.approx(1.0)


def test_json_codec_round_trip_structured() -> None:
    jc = JsonCodec()
    assert jc.decode(jc.encode(STRUCTURED)) == STRUCTURED
    assert jc.decode(jc.encode([1, 2, "three"])) == [1, 2, "three"]
    assert jc.decode(jc.encode(TEXT)) == TEXT


# ── 2. Codec metadata & ABC ────────────────────────────────────────────────


def test_codec_names_and_mimes() -> None:
    assert {"xz", "gzip", "bz2", "json", "noop"} == {
        XZCodec().name,
        GzipCodec().name,
        Bz2Codec().name,
        JsonCodec().name,
        NOOPCodec().name,
    }
    assert XZCodec().mime == "application/x-xz"
    assert GzipCodec().mime == "application/gzip"
    assert NOOPCodec().mime == "application/octet-stream"


def test_codec_abc_abstract_not_instantiable() -> None:
    with pytest.raises(TypeError):
        Codec()


# ── 3. Registry API ────────────────────────────────────────────────────────


def test_registry_default_builtins() -> None:
    reg = CodecRegistry()
    assert {c.name for c in reg.list()} == {"xz", "gzip", "bz2", "json", "noop"}
    assert len(reg) == 5


def test_registry_get_and_unknown_keyerror() -> None:
    reg = CodecRegistry()
    assert reg.get("xz").name == "xz"
    with pytest.raises(KeyError):
        reg.get("nope")


def test_registry_register_custom_and_forms() -> None:
    class UpperCodec(Codec):
        name = "upper"
        mime = "text/plain"

        def encode(self, data: object) -> bytes:
            return str(data).upper().encode("utf-8")

        def decode(self, data: bytes) -> str:
            return data.decode("utf-8").lower()

    reg = CodecRegistry(codecs=[])
    inst_class = reg.register_codec(XZCodec)  # class form → instantiated
    assert isinstance(inst_class, XZCodec)
    reg.register_codec(UpperCodec())  # instance form
    assert "upper" in reg
    assert reg.get("upper").name == "upper"
    assert len(reg) == 2


def test_registry_duplicate_name_raises_valueerror() -> None:
    reg = CodecRegistry()
    with pytest.raises(ValueError, match="already registered"):
        reg.register_codec(XZCodec())  # "xz" already registered


# ── 4. best_codec negotiation ──────────────────────────────────────────────


def test_best_codec_lossless_for_repetitive_and_deterministic() -> None:
    reg = CodecRegistry()
    best = reg.best_codec(REPETITIVE)
    assert best.name in {"xz", "gzip", "bz2"}  # a real compressor, NOT noop
    # Deterministic: repeatedly and across fresh registries.
    assert reg.best_codec(REPETITIVE).name == best.name
    assert CodecRegistry().best_codec(REPETITIVE).name == best.name


def test_best_codec_noop_for_random() -> None:
    reg = CodecRegistry()
    assert reg.best_codec(RANDOM).name == "noop"


def test_best_codec_structured_not_noop() -> None:
    # Negotiation is size-based; JSON text is highly compressible so a real
    # compressor (NOT noop) is selected. JsonCodec is the type-preserving
    # fallback and is covered separately.
    reg = CodecRegistry()
    assert reg.best_codec(STRUCTURED).name != "noop"


# ── 5. negotiate_ratio ─────────────────────────────────────────────────────


def test_negotiate_ratio_reports_saved_bytes() -> None:
    result = negotiate_ratio(REPETITIVE)
    assert set(result) >= {
        "codec",
        "mime",
        "ratio",
        "original_size",
        "compressed_size",
        "saved_bytes",
    }
    assert result["saved_bytes"] == result["original_size"] - result["compressed_size"]
    assert result["saved_bytes"] > 0
    assert result["ratio"] > 1.0
    assert result["lossless"] is True


def test_negotiate_ratio_noop_for_random() -> None:
    result = negotiate_ratio(RANDOM)
    assert result["codec"] == "noop"
    assert result["saved_bytes"] <= 0


# ── 6. Bridge integration ──────────────────────────────────────────────────


def test_bridge_registry_and_compress_auto_best() -> None:
    bridge = CompressionBridge()
    assert isinstance(bridge.codec_registry, CodecRegistry)
    assert len(bridge.codec_registry) == 5

    result = bridge.compress(REPETITIVE, codec="auto")
    assert result.success is True
    assert result.metadata["codec"] in {"xz", "gzip", "bz2"}
    assert result.metadata["lossless"] is True
    assert result.algorithm_used == f"codec:{result.metadata['codec']}"
    assert result.compressed_size < result.original_size

    best = bridge.compress_best(REPETITIVE)
    assert best.success is True
    assert best.metadata["codec"] != "noop"


def test_bridge_explicit_codec_and_select_unknown() -> None:
    bridge = CompressionBridge()
    result = bridge.compress(TEXT.encode(), codec="xz")
    assert result.success is True
    assert result.metadata["codec"] == "xz"
    # Round-trips back through the registry codec.
    decoded = bridge.codec_registry.get("xz").decode(
        bridge.codec_registry.get("xz").encode(TEXT.encode())
    )
    assert decoded == TEXT.encode()

    assert bridge.select_codec(REPETITIVE) == bridge.codec_registry.best_codec(REPETITIVE).name
    assert bridge.select_codec(RANDOM) == "noop"
    assert bridge.select_codec(TEXT, codec="gzip") == "gzip"
    with pytest.raises(KeyError):
        bridge.select_codec(TEXT, codec="bogus")


def test_bridge_codec_lifecycle_and_factory() -> None:
    import compression_bridge

    bridge = CompressionBridge()
    _run(bridge.initialize())
    assert len(bridge.codec_registry) == 5
    assert bridge.compress_best(REPETITIVE).success is True
    assert (
        bridge.negotiate_ratio(REPETITIVE)["saved_bytes"]
        == negotiate_ratio(REPETITIVE)["saved_bytes"]
    )
    _run(bridge.shutdown())

    assert compression_bridge.__version__
    mod = compression_bridge.create_compression_bridge_module(config={})
    assert mod is not None
    assert mod.bridge is None
