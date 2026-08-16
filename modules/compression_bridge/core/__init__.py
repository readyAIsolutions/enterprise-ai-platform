"""
ENI Compression Core - Unified Multi-Algorithm Compression Engine
===================================================================
Integrates: PAQ8, zstd, lz4, brotli, LLMLingua, headroom, claw-compactor,
Wenyan encoding, PXPipe steganography, Glyph caching, Adaptive ML selector
"""

from .engine import CompressionEngine, CompressionResult, CompressionMode
from .algorithms import (
    PAQ8Compressor, ZstdCompressor, LZ4Compressor, BrotliCompressor,
    LLMLinguaCompressor, HeadroomCompressor, ClawCompactorCompressor,
    WenyanEncoder, PXPipeSteganography, GlyphCache
)
from .selector import AdaptiveCompressorSelector

__all__ = [
    "CompressionEngine",
    "CompressionResult", 
    "CompressionMode",
    "PAQ8Compressor",
    "ZstdCompressor",
    "LZ4Compressor", 
    "BrotliCompressor",
    "LLMLinguaCompressor",
    "HeadroomCompressor",
    "ClawCompactorCompressor",
    "WenyanEncoder",
    "PXPipeSteganography",
    "GlyphCache",
    "AdaptiveCompressorSelector",
]

__version__ = "3.0.0-eni-impossible"