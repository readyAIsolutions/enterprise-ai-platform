"""
Compression Engine - Main entry point for all compression operations
"""
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, List
import hashlib
import time
import json


class CompressionMode(Enum):
    """Available compression modes"""
    MAXIMUM = "maximum"          # PAQ8 - best ratio, slowest
    BALANCED = "balanced"        # zstd level 19 - good ratio, fast
    FAST = "fast"                # lz4 - fastest, decent ratio
    ULTRA_FAST = "ultra_fast"    # lz4 HC - fastest decompression
    LLM_OPTIMIZED = "llm_optimized"    # LLMLingua + headroom - for LLM prompts
    CODE_AWARE = "code_aware"    # claw-compactor - AST-aware code compression
    STEGANOGRAPHY = "steganography"    # PXPipe PNG LSB hiding
    WENYAN = "wenyan"            # Wenyan encoding for tokenizer confusion
    GLYPH = "glyph"              # Glyph cache for repeated operations
    ADAPTIVE = "adaptive"        # ML-based algorithm selection
    IMPOSSIBLE = "impossible"    # All layers combined (Wenyan + PAQ8 + PXPipe + Glyph)


@dataclass
class CompressionResult:
    """Result of a compression operation"""
    success: bool
    original_size: int
    compressed_size: int
    ratio: float
    mode: CompressionMode
    carrier_path: Optional[str] = None
    wenyan_encoded: Optional[str] = None
    glyph_compressed: Optional[str] = None
    algorithm_used: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    compression_time_ms: float = 0.0
    decompression_time_ms: float = 0.0
    
    def __post_init__(self):
        if self.compressed_size > 0:
            self.ratio = self.original_size / self.compressed_size
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "original_size": self.original_size,
            "compressed_size": self.compressed_size,
            "ratio": round(self.ratio, 3),
            "mode": self.mode.value,
            "carrier_path": self.carrier_path,
            "wenyan_encoded": self.wenyan_encoded,
            "glyph_compressed": self.glyph_compressed,
            "algorithm_used": self.algorithm_used,
            "metadata": self.metadata,
            "error": self.error,
            "compression_time_ms": round(self.compression_time_ms, 2),
            "decompression_time_ms": round(self.decompression_time_ms, 2),
        }


class CompressionEngine:
    """Main compression engine orchestrating all algorithms"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.carriers_dir = Path(self.config.get("carriers_dir", "/home/hunter/Desktop/eni_compression/carriers"))
        self.carriers_dir.mkdir(parents=True, exist_ok=True)
        
        # Lazy-loaded compressors
        self._compressors = {}
        self._selector = None
        self._glyph_cache = None
        self._wenyan = None
        self._pxpipe = None
        
        # Statistics
        self.stats = {
            "total_compressions": 0,
            "total_decompressions": 0,
            "total_bytes_original": 0,
            "total_bytes_compressed": 0,
            "by_mode": {},
        }
    
    @property
    def selector(self):
        if self._selector is None:
            from .selector import AdaptiveCompressorSelector
            self._selector = AdaptiveCompressorSelector()
        return self._selector
    
    @property
    def glyph_cache(self):
        if self._glyph_cache is None:
            from .algorithms import GlyphCache
            self._glyph_cache = GlyphCache()
        return self._glyph_cache
    
    @property
    def wenyan(self):
        if self._wenyan is None:
            from .algorithms import WenyanEncoder
            self._wenyan = WenyanEncoder()
        return self._wenyan
    
    @property
    def pxpipe(self):
        if self._pxpipe is None:
            from .algorithms import PXPipeSteganography
            self._pxpipe = PXPipeSteganography()
        return self._pxpipe
    
    def _get_compressor(self, mode: CompressionMode):
        """Get or create compressor for mode"""
        if mode not in self._compressors:
            from .algorithms import (
                PAQ8Compressor, ZstdCompressor, LZ4Compressor, 
                BrotliCompressor, LLMLinguaCompressor, 
                HeadroomCompressor, ClawCompactorCompressor
            )
            compressor_map = {
                CompressionMode.MAXIMUM: PAQ8Compressor,
                CompressionMode.BALANCED: lambda: ZstdCompressor(level=19),
                CompressionMode.FAST: LZ4Compressor,
                CompressionMode.ULTRA_FAST: lambda: LZ4Compressor(high_compression=False),
                CompressionMode.LLM_OPTIMIZED: LLMLinguaCompressor,
                CompressionMode.CODE_AWARE: ClawCompactorCompressor,
            }
            if mode in compressor_map:
                self._compressors[mode] = compressor_map[mode]()
        return self._compressors.get(mode)
    
    def compress(self, data: bytes, mode: CompressionMode = CompressionMode.ADAPTIVE,
                 carrier_name: Optional[str] = None) -> CompressionResult:
        """Compress data using specified mode"""
        start_time = time.perf_counter()
        original_size = len(data)
        
        try:
            if mode == CompressionMode.ADAPTIVE:
                mode = self.selector.select(data)
            
            # Special modes that use multiple stages
            if mode == CompressionMode.IMPOSSIBLE:
                return self._compress_impossible(data, carrier_name, start_time)
            elif mode == CompressionMode.STEGANOGRAPHY:
                return self._compress_steganography(data, carrier_name, start_time)
            elif mode == CompressionMode.WENYAN:
                return self._compress_wenyan(data, start_time)
            elif mode == CompressionMode.GLYPH:
                return self._compress_glyph(data.decode('utf-8', errors='ignore'), start_time)
            
            # Standard single-algorithm modes
            compressor = self._get_compressor(mode)
            if compressor is None:
                return CompressionResult(
                    success=False, original_size=original_size, compressed_size=0,
                    ratio=0, mode=mode, error=f"No compressor for mode: {mode}"
                )
            
            compressed = compressor.compress(data)
            comp_time = (time.perf_counter() - start_time) * 1000
            
            result = CompressionResult(
                success=True,
                original_size=original_size,
                compressed_size=len(compressed),
                ratio=original_size / len(compressed) if compressed else 0,
                mode=mode,
                algorithm_used=compressor.name,
                compression_time_ms=comp_time,
                metadata={"compressor": compressor.name}
            )
            
            # Save carrier if requested
            if carrier_name:
                carrier_path = self.carriers_dir / carrier_name
                carrier_path.write_bytes(compressed)
                result.carrier_path = str(carrier_path)
            
            self._update_stats(result)
            return result
            
        except Exception as e:
            return CompressionResult(
                success=False, original_size=original_size, compressed_size=0,
                ratio=0, mode=mode, error=str(e),
                compression_time_ms=(time.perf_counter() - start_time) * 1000
            )
    
    def _compress_impossible(self, data: bytes, carrier_name: Optional[str], start_time: float) -> CompressionResult:
        """IMPOSSIBLE mode: Wenyan -> PAQ8 -> PXPipe -> Glyph (full ENI pipeline)"""
        original_size = len(data)
        text = data.decode('utf-8', errors='ignore')
        
        # Stage 1: Wenyan encode
        wenyan_encoded = self.wenyan.encode(text)
        
        # Stage 2: PAQ8 compress original data
        paq8 = self._get_compressor(CompressionMode.MAXIMUM)
        compressed = paq8.compress(data)
        
        # Stage 3: PXPipe encode to PNG
        if carrier_name is None:
            carrier_name = f"carrier_{hashlib.md5(data).hexdigest()[:8]}.png"
        carrier_path = self.carriers_dir / carrier_name
        self.pxpipe.encode(compressed, carrier_path)
        
        # Stage 4: Glyph compress the wenyan
        glyph_compressed = self.glyph_cache.compress(wenyan_encoded)
        
        comp_time = (time.perf_counter() - start_time) * 1000
        
        result = CompressionResult(
            success=True,
            original_size=original_size,
            compressed_size=len(compressed),
            ratio=original_size / len(compressed) if compressed else 0,
            mode=CompressionMode.IMPOSSIBLE,
            carrier_path=str(carrier_path),
            wenyan_encoded=wenyan_encoded,
            glyph_compressed=glyph_compressed,
            algorithm_used="Wenyan+PAQ8+PXPipe+Glyph",
            compression_time_ms=comp_time,
            metadata={
                "stages": ["wenyan", "paq8", "pxpipe", "glyph"],
                "wenyan_length": len(wenyan_encoded),
                "glyph_length": len(glyph_compressed),
            }
        )
        
        self._update_stats(result)
        return result
    
    def _compress_steganography(self, data: bytes, carrier_name: Optional[str], start_time: float) -> CompressionResult:
        """STEGANOGRAPHY mode: Compress + hide in PNG"""
        original_size = len(data)
        
        # First compress with balanced
        compressor = self._get_compressor(CompressionMode.BALANCED)
        compressed = compressor.compress(data)
        
        # Then hide in PNG
        if carrier_name is None:
            carrier_name = f"stego_{hashlib.md5(data).hexdigest()[:8]}.png"
        carrier_path = self.carriers_dir / carrier_name
        self.pxpipe.encode(compressed, carrier_path)
        
        comp_time = (time.perf_counter() - start_time) * 1000
        
        result = CompressionResult(
            success=True,
            original_size=original_size,
            compressed_size=len(compressed),
            ratio=original_size / len(compressed) if compressed else 0,
            mode=CompressionMode.STEGANOGRAPHY,
            carrier_path=str(carrier_path),
            algorithm_used=f"{compressor.name}+PXPipe",
            compression_time_ms=comp_time,
            metadata={"compressor": compressor.name, "carrier_size": carrier_path.stat().st_size}
        )
        
        self._update_stats(result)
        return result
    
    def _compress_wenyan(self, data: bytes, start_time: float) -> CompressionResult:
        """WENYAN mode: Encode to Wenyan addresses"""
        text = data.decode('utf-8', errors='ignore')
        wenyan = self.wenyan.encode(text)
        wenyan_bytes = wenyan.encode('utf-8')
        
        comp_time = (time.perf_counter() - start_time) * 1000
        
        result = CompressionResult(
            success=True,
            original_size=len(data),
            compressed_size=len(wenyan_bytes),
            ratio=len(data) / len(wenyan_bytes) if wenyan_bytes else 0,
            mode=CompressionMode.WENYAN,
            wenyan_encoded=wenyan,
            algorithm_used="WenyanCodec",
            compression_time_ms=comp_time,
            metadata={"wenyan_chars": len(wenyan)}
        )
        
        self._update_stats(result)
        return result
    
    def _compress_glyph(self, text: str, start_time: float) -> CompressionResult:
        """GLYPH mode: Compress using glyph cache"""
        glyph_compressed = self.glyph_cache.compress(text)
        glyph_bytes = glyph_compressed.encode('utf-8')
        original_bytes = text.encode('utf-8')
        
        comp_time = (time.perf_counter() - start_time) * 1000
        
        result = CompressionResult(
            success=True,
            original_size=len(original_bytes),
            compressed_size=len(glyph_bytes),
            ratio=len(original_bytes) / len(glyph_bytes) if glyph_bytes else 0,
            mode=CompressionMode.GLYPH,
            glyph_compressed=glyph_compressed,
            algorithm_used="GlyphCache",
            compression_time_ms=comp_time,
            metadata={"glyph_chars": len(glyph_compressed)}
        )
        
        self._update_stats(result)
        return result
    
    def decompress(self, data: bytes, mode: CompressionMode, 
                   carrier_path: Optional[str] = None) -> CompressionResult:
        """Decompress data"""
        start_time = time.perf_counter()
        original_size = len(data)
        
        try:
            if mode == CompressionMode.IMPOSSIBLE:
                return self._decompress_impossible(carrier_path, start_time)
            elif mode == CompressionMode.STEGANOGRAPHY:
                return self._decompress_steganography(carrier_path, start_time)
            
            compressor = self._get_compressor(mode)
            if compressor is None:
                return CompressionResult(
                    success=False, original_size=original_size, compressed_size=0,
                    ratio=0, mode=mode, error=f"No compressor for mode: {mode}"
                )
            
            decompressed = compressor.decompress(data)
            decomp_time = (time.perf_counter() - start_time) * 1000
            
            result = CompressionResult(
                success=True,
                original_size=original_size,
                compressed_size=len(decompressed),
                ratio=len(decompressed) / original_size if original_size else 0,
                mode=mode,
                algorithm_used=compressor.name,
                decompression_time_ms=decomp_time,
            )
            
            self.stats["total_decompressions"] += 1
            return result
            
        except Exception as e:
            return CompressionResult(
                success=False, original_size=original_size, compressed_size=0,
                ratio=0, mode=mode, error=str(e),
                decompression_time_ms=(time.perf_counter() - start_time) * 1000
            )
    
    def _decompress_impossible(self, carrier_path: Optional[str], start_time: float) -> CompressionResult:
        """Decompress IMPOSSIBLE mode carrier"""
        if not carrier_path:
            return CompressionResult(
                success=False, original_size=0, compressed_size=0, ratio=0,
                mode=CompressionMode.IMPOSSIBLE, error="Carrier path required"
            )
        
        # Extract from PNG
        extracted = self.pxpipe.decode(Path(carrier_path))
        
        # PAQ8 decompress
        paq8 = self._get_compressor(CompressionMode.MAXIMUM)
        decompressed = paq8.decompress(extracted)
        
        decomp_time = (time.perf_counter() - start_time) * 1000
        
        return CompressionResult(
            success=True,
            original_size=len(extracted),
            compressed_size=len(decompressed),
            ratio=len(decompressed) / len(extracted) if extracted else 0,
            mode=CompressionMode.IMPOSSIBLE,
            algorithm_used="PXPipe+PAQ8",
            decompression_time_ms=decomp_time,
        )
    
    def _decompress_steganography(self, carrier_path: Optional[str], start_time: float) -> CompressionResult:
        """Decompress steganography carrier"""
        if not carrier_path:
            return CompressionResult(
                success=False, original_size=0, compressed_size=0, ratio=0,
                mode=CompressionMode.STEGANOGRAPHY, error="Carrier path required"
            )
        
        extracted = self.pxpipe.decode(Path(carrier_path))
        
        # Decompress with balanced
        compressor = self._get_compressor(CompressionMode.BALANCED)
        decompressed = compressor.decompress(extracted)
        
        decomp_time = (time.perf_counter() - start_time) * 1000
        
        return CompressionResult(
            success=True,
            original_size=len(extracted),
            compressed_size=len(decompressed),
            ratio=len(decompressed) / len(extracted) if extracted else 0,
            mode=CompressionMode.STEGANOGRAPHY,
            algorithm_used="PXPipe+" + compressor.name,
            decompression_time_ms=decomp_time,
        )
    
    def verify_roundtrip(self, data: bytes, mode: CompressionMode = CompressionMode.ADAPTIVE) -> bool:
        """Verify compression/decompression round-trip"""
        result = self.compress(data, mode)
        if not result.success:
            return False
        
        # For modes with carriers, decompress from carrier
        if result.carrier_path and mode in (CompressionMode.IMPOSSIBLE, CompressionMode.STEGANOGRAPHY):
            decomp_result = self.decompress(b"", mode, result.carrier_path)
            return decomp_result.success and decomp_result.compressed_size == len(data)
        
        # For standard modes, decompress the compressed data
        # Need to re-compress to get the compressed bytes
        compressor = self._get_compressor(mode)
        if compressor:
            compressed = compressor.compress(data)
            decomp_result = self.decompress(compressed, mode)
            return decomp_result.success and decomp_result.compressed_size == len(data)
        
        return False
    
    def _update_stats(self, result: CompressionResult):
        self.stats["total_compressions"] += 1
        self.stats["total_bytes_original"] += result.original_size
        self.stats["total_bytes_compressed"] += result.compressed_size
        mode_key = result.mode.value
        if mode_key not in self.stats["by_mode"]:
            self.stats["by_mode"][mode_key] = {"count": 0, "total_ratio": 0}
        self.stats["by_mode"][mode_key]["count"] += 1
        self.stats["by_mode"][mode_key]["total_ratio"] += result.ratio
    
    def get_stats(self) -> Dict:
        stats = self.stats.copy()
        for mode, data in stats["by_mode"].items():
            if data["count"] > 0:
                data["avg_ratio"] = round(data["total_ratio"] / data["count"], 3)
        return stats


# Convenience functions
def compress(data: bytes, mode: CompressionMode = CompressionMode.ADAPTIVE, 
             carrier_name: Optional[str] = None) -> CompressionResult:
    """One-shot compression"""
    engine = CompressionEngine()
    return engine.compress(data, mode, carrier_name)


def decompress(data: bytes, mode: CompressionMode, 
               carrier_path: Optional[str] = None) -> CompressionResult:
    """One-shot decompression"""
    engine = CompressionEngine()
    return engine.decompress(data, mode, carrier_path)


def verify_roundtrip(data: bytes, mode: CompressionMode = CompressionMode.ADAPTIVE) -> bool:
    """One-shot round-trip verification"""
    engine = CompressionEngine()
    return engine.verify_roundtrip(data, mode)