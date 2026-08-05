"""
codecs — Pluggable compression codec registry + ratio negotiation for the
Enterprise compression_bridge module.

This module is deliberately PURE STDLIB (lzma / gzip / bz2 / json) so it can be
imported and tested in isolation without touching the heavier ENI core engine.
It provides:

    Codec            — ABC every codec implements (encode/decode/ratio/name/mime)
    XZCodec          — stdlib lzma (best ratio, slow)
    GzipCodec        — stdlib gzip (good ratio, fast)
    Bz2Codec         — stdlib bz2 (good ratio, medium)
    JsonCodec        — stdlib json (structured data: dict/list/str/num)
    NOOPCodec        — identity passthrough (for incompressible / random payloads)
    CodecRegistry    — register / get / list / best_codec (deterministic)
    negotiate_ratio  — pick the best codec for a payload, return savings

Selection semantics
-------------------
``CodecRegistry.best_codec(payload)`` runs every registered codec over a bounded
sample of the payload and returns the codec that achieves the smallest encoded
size (highest compression ratio). Ties are broken deterministically by codec
name (lexicographically smallest). Codecs that raise on a payload type (e.g. a
binary codec given a dict, or a JSON codec given opaque bytes) are skipped, so
structured payloads naturally negotiate toward JsonCodec while opaque bytes
negotiate toward the best binary codec (or NOOP for incompressible data).
"""

from __future__ import annotations

import bz2
import gzip
import json
import lzma
from abc import ABC, abstractmethod
from typing import Any

__all__ = [
    "Codec",
    "XZCodec",
    "GzipCodec",
    "Bz2Codec",
    "JsonCodec",
    "NOOPCodec",
    "CodecRegistry",
    "negotiate_ratio",
    "DEFAULT_CODECS",
]

# Bounded sample window used by ratio negotiation. Negotiating on a sample keeps
# best_codec() fast (O(1) memory) even for very large payloads.
SAMPLE_BYTES = 8192


class Codec(ABC):
    """Abstract base class for a compression codec.

    Implementations must provide an identifier, a MIME type, and lossless
    ``encode``/``decode`` round-trip plus a ``ratio`` estimate.
    """

    name: str = ""
    mime: str = "application/octet-stream"

    @abstractmethod
    def encode(self, data: Any) -> bytes:  # noqa: ANN401
        """Return the compressed representation of *data*."""

    @abstractmethod
    def decode(self, data: bytes) -> Any:  # noqa: ANN401
        """Return the original object from a compressed representation."""

    def ratio(self, data: Any) -> float:  # noqa: ANN401
        """Compression ratio achieved on *data* (original / encoded size)."""
        encoded = self.encode(data)
        original_len = _measure(data)
        if original_len == 0:
            return 1.0
        return original_len / max(len(encoded), 1)

    def compress(self, data: Any) -> bytes:  # noqa: ANN401
        """Alias for encode() — mirrors the bridge vocabulary."""
        return self.encode(data)

    def decompress(self, data: bytes) -> Any:  # noqa: ANN401
        """Alias for decode() — mirrors the bridge vocabulary."""
        return self.decode(data)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<{type(self).__name__} name={self.name!r} mime={self.mime!r}>"


def _measure(data: Any) -> int:  # noqa: ANN401
    """Return the logical byte size of *data* regardless of type."""
    if isinstance(data, bytes):
        return len(data)
    if isinstance(data, (bytearray, memoryview)):
        return len(data)
    if isinstance(data, str):
        return len(data.encode("utf-8"))
    # dict/list/number → serialize to measure
    return len(json.dumps(data).encode("utf-8"))


class XZCodec(Codec):
    """LZMA/XZ compression — best ratio of the stdlib family, slowest."""

    name = "xz"
    mime = "application/x-xz"

    def encode(self, data: Any) -> bytes:  # noqa: ANN401
        return lzma.compress(_as_bytes(data), preset=6)

    def decode(self, data: bytes) -> bytes:
        return lzma.decompress(data)


class GzipCodec(Codec):
    """gzip compression — good ratio, fast."""

    name = "gzip"
    mime = "application/gzip"

    def encode(self, data: Any) -> bytes:  # noqa: ANN401
        return gzip.compress(_as_bytes(data), compresslevel=9)

    def decode(self, data: bytes) -> bytes:
        return gzip.decompress(data)


class Bz2Codec(Codec):
    """bzip2 compression — good ratio, medium speed."""

    name = "bz2"
    mime = "application/x-bzip2"

    def encode(self, data: Any) -> bytes:  # noqa: ANN401
        return bz2.compress(_as_bytes(data), compresslevel=9)

    def decode(self, data: bytes) -> bytes:
        return bz2.decompress(data)


class JsonCodec(Codec):
    """JSON codec — lossless round-trip for structured Python objects."""

    name = "json"
    mime = "application/json"

    def encode(self, data: Any) -> bytes:  # noqa: ANN401
        return json.dumps(data, separators=(",", ":")).encode("utf-8")

    def decode(self, data: bytes) -> Any:  # noqa: ANN401
        return json.loads(data.decode("utf-8"))


class NOOPCodec(Codec):
    """Identity passthrough — used when a payload is already incompressible."""

    name = "noop"
    mime = "application/octet-stream"

    def encode(self, data: Any) -> bytes:  # noqa: ANN401
        return _as_bytes(data)

    def decode(self, data: bytes) -> bytes:
        return bytes(data)


def _as_bytes(data: Any) -> bytes:  # noqa: ANN401
    """Normalise *data* to bytes for binary codecs."""
    if isinstance(data, bytes):
        return data
    if isinstance(data, bytearray):
        return bytes(data)
    if isinstance(data, memoryview):
        return data.tobytes()
    if isinstance(data, str):
        return data.encode("utf-8")
    # structured objects → JSON bytes
    return json.dumps(data).encode("utf-8")


# ── Built-in registry defaults ──────────────────────────────────────────────

DEFAULT_CODECS: tuple[type[Codec], ...] = (
    XZCodec,
    GzipCodec,
    Bz2Codec,
    JsonCodec,
    NOOPCodec,
)


class CodecRegistry:
    """A pluggable, deterministic codec registry.

    Responsibilities:
      - register_codec(codec)      — add a codec (instance or class); duplicate
                                     name raises ValueError
      - get(name)                 — fetch a codec by name
      - list()                    — all registered codecs
      - best_codec(payload)       — negotiate: pick the best codec for payload
    """

    def __init__(self, codecs: list[Codec] | tuple[type[Codec], ...] | None = None) -> None:
        self._codecs: dict[str, Codec] = {}
        builtins = DEFAULT_CODECS if codecs is None else codecs
        for entry in builtins:
            self.register_codec(entry)

    # ── Registry API ───────────────────────────────────────────────────────

    def register_codec(self, codec: Codec | type[Codec]) -> Codec:
        """Register a codec instance or class.

        Duplicate names raise ``ValueError`` to keep the registry unambiguous.

        Args:
            codec: A Codec instance or a Codec subclass to instantiate.

        Returns:
            The registered (instantiated) Codec.
        """
        instance = codec() if isinstance(codec, type) else codec
        if not isinstance(instance, Codec):
            msg = f"{codec!r} is not a Codec instance or subclass"
            raise TypeError(msg)
        name = instance.name
        if not name:
            msg = "Cannot register a codec without a non-empty name"
            raise ValueError(msg)
        if name in self._codecs:
            msg = f"Codec {name!r} is already registered"
            raise ValueError(msg)
        self._codecs[name] = instance
        return instance

    def get(self, name: str) -> Codec:
        """Fetch a codec by name. Raises ``KeyError`` if unknown."""
        if name not in self._codecs:
            msg = f"No codec named {name!r}; registered: {sorted(self._codecs)}"
            raise KeyError(msg)
        return self._codecs[name]

    def list(self) -> list[Codec]:
        """Return all registered codecs (sorted by name for determinism)."""
        return [self._codecs[n] for n in sorted(self._codecs)]

    def __len__(self) -> int:
        return len(self._codecs)

    def __contains__(self, name: str) -> bool:
        return name in self._codecs

    # ── Negotiation ────────────────────────────────────────────────────────

    def best_codec(self, payload: Any) -> Codec:  # noqa: ANN401
        """Negotiate the best codec for *payload*.

        Each codec runs over a bounded sample of the payload; the one achieving
        the smallest encoded size wins. Ties broken by lexicographically
        smallest name. Codecs that cannot handle the payload type are skipped.
        """
        sample = _sample(payload)
        best: Codec | None = None
        best_ratio = -1.0
        # Deterministic order regardless of registration order.
        for codec in self.list():
            try:
                ratio = codec.ratio(sample)
            except Exception:
                # Codec cannot represent this payload type — skip it.
                continue
            if ratio > best_ratio + 1e-9:
                best = codec
                best_ratio = ratio
            # Equal ratio → keep the lexicographically-smaller-name codec
            # (self.list() is already name-sorted, so no extra work needed).
        if best is None:
            # Nothing succeeded (should be impossible: NOOP always works).
            return NOOPCodec()
        return best


def _sample(payload: Any) -> Any:  # noqa: ANN401
    """Return a bounded sample of *payload* for cheap negotiation."""
    if isinstance(payload, bytes):
        return payload[:SAMPLE_BYTES]
    if isinstance(payload, str):
        return payload[:SAMPLE_BYTES]
    if isinstance(payload, (list, tuple)):
        sampled = payload[: max(1, SAMPLE_BYTES // 64)]
        return sampled[0] if len(sampled) == 1 else sampled
    return payload  # dicts / scalars pass through whole


def negotiate_ratio(source_payload: Any) -> dict[str, Any]:  # noqa: ANN401
    """Negotiate the best codec and measure the achievable savings.

    Args:
        source_payload: The raw payload (bytes, str, dict, list, ...).

    Returns:
        A dict::

            {
                "codec": codec.name,
                "mime": codec.mime,
                "ratio": float,  # original_size / compressed_size
                "original_size": int,
                "compressed_size": int,
                "saved_bytes": int,  # original_size - compressed_size
                "lossless": bool,
            }
    """
    registry = CodecRegistry()
    codec = registry.best_codec(source_payload)
    encoded = codec.encode(source_payload)
    original_size = _measure(source_payload)
    compressed_size = len(encoded)
    saved_bytes = original_size - compressed_size
    ratio = (original_size / max(compressed_size, 1)) if original_size else 1.0
    return {
        "codec": codec.name,
        "mime": codec.mime,
        "ratio": round(ratio, 4),
        "original_size": original_size,
        "compressed_size": compressed_size,
        "saved_bytes": saved_bytes,
        "lossless": True,
    }
