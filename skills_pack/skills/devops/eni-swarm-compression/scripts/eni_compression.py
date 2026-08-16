#!/usr/bin/env python3
"""
ENI Compression Module - Importable pipeline for any Python code
Usage:
    from eni_compression import compress, decompress, CompressionPipeline
    
    # One-shot compression
    result = compress("Your text here")
    # result: {"carrier": "path.png", "wenyan": "...", "glyph": "...", "ratio": 3.2}
    
    # Decompress
    original = decompress(result["carrier"])
"""
import sys
sys.path.insert(0, "/home/hunter/Desktop/eni_compression")

from workers.compression_worker import (
    WENYAN, paq8_compress, paq8_decompress, 
    pxpipe_encode, pxpipe_decode, compress_with_glyphs,
    compress_markdown, PNG_CARRIER_DIR, GLYPH_MAP
)
from pathlib import Path
import json

class CompressionPipeline:
    """Full ENI compression pipeline as a callable object"""
    
    def __init__(self):
        self.stats = {"compressions": 0, "decompressions": 0, "total_ratio": 0.0}
    
    def compress(self, text: str, carrier_name: str = None) -> dict:
        """Compress text through full pipeline: Wenyan -> PAQ8 -> PNG -> Glyphs"""
        # 1. Wenyan encode
        wenyan = WENYAN.encode(text)
        
        # 2. PAQ8 compress
        compressed = paq8_compress(text.encode())
        
        # 3. PXPipe encode to PNG
        if carrier_name is None:
            import hashlib
            carrier_name = f"carrier_{hashlib.md5(text.encode()).hexdigest()[:8]}.png"
        carrier_path = PNG_CARRIER_DIR / carrier_name
        pxpipe_encode(compressed, carrier_path)
        
        # 4. Glyph compress the wenyan
        glyph_compressed = compress_with_glyphs(wenyan)
        
        ratio = len(text) / len(compressed) if compressed else 0
        self.stats["compressions"] += 1
        self.stats["total_ratio"] += ratio
        
        return {
            "carrier": str(carrier_path),
            "carrier_name": carrier_name,
            "wenyan": wenyan,
            "glyph_compressed": glyph_compressed,
            "original_size": len(text),
            "compressed_size": len(compressed),
            "ratio": ratio,
            "stats": self.stats.copy()
        }
    
    def decompress(self, carrier_path: str) -> str:
        """Decompress from PNG carrier back to original text"""
        carrier = Path(carrier_path)
        if not carrier.exists():
            raise FileNotFoundError(f"Carrier not found: {carrier_path}")
        
        # 1. Extract from PNG
        extracted = pxpipe_decode(carrier)
        
        # 2. PAQ8 decompress
        decompressed = paq8_decompress(extracted)
        
        self.stats["decompressions"] += 1
        return decompressed.decode()
    
    def verify_roundtrip(self, text: str) -> bool:
        """Test full round-trip"""
        result = self.compress(text)
        restored = self.decompress(result["carrier"])
        return restored == text

def compress(text: str, carrier_name: str = None) -> dict:
    """Convenience function for one-shot compression"""
    pipeline = CompressionPipeline()
    return pipeline.compress(text, carrier_name)

def decompress(carrier_path: str) -> str:
    """Convenience function for one-shot decompression"""
    pipeline = CompressionPipeline()
    return pipeline.decompress(carrier_path)

def batch_compress(texts: list, prefix: str = "batch") -> list:
    """Compress multiple texts in parallel"""
    from concurrent.futures import ThreadPoolExecutor
    pipeline = CompressionPipeline()
    
    def compress_one(args):
        i, text = args
        return pipeline.compress(text, f"{prefix}_{i}.png")
    
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(compress_one, enumerate(texts)))
    
    return results

def get_glyph_map() -> dict:
    """Return current glyph map"""
    return GLYPH_MAP.copy()

def add_glyph(name: str, expansion: str):
    """Add a new glyph to the map"""
    GLYPH_MAP[name] = expansion
    import json
    (Path("/home/hunter/Desktop/eni_compression") / "glyph_map.json").write_text(
        json.dumps(GLYPH_MAP, indent=2)
    )

def get_wenyan_address(capability: str) -> str:
    """Get Wenyan address for a capability"""
    return WENYAN.encode(capability)

# CLI interface
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ENI Compression Pipeline")
    parser.add_argument("action", choices=["compress", "decompress", "verify", "glyphs", "wenyan"])
    parser.add_argument("input", nargs="?", help="Text to compress or carrier path")
    parser.add_argument("-o", "--output", help="Output carrier name")
    args = parser.parse_args()
    
    pipeline = CompressionPipeline()
    
    if args.action == "compress":
        if not args.input:
            print("Error: input text required")
            sys.exit(1)
        result = pipeline.compress(args.input, args.output)
        print(json.dumps(result, indent=2))
    
    elif args.action == "decompress":
        if not args.input:
            print("Error: carrier path required")
            sys.exit(1)
        text = pipeline.decompress(args.input)
        print(text)
    
    elif args.action == "verify":
        if not args.input:
            print("Error: test text required")
            sys.exit(1)
        ok = pipeline.verify_roundtrip(args.input)
        print(f"Round-trip: {'PASS' if ok else 'FAIL'}")
    
    elif args.action == "glyphs":
        print(json.dumps(GLYPH_MAP, indent=2))
    
    elif args.action == "wenyan":
        if not args.input:
            print("Error: capability name required")
            sys.exit(1)
        print(WENYAN.encode(args.input))