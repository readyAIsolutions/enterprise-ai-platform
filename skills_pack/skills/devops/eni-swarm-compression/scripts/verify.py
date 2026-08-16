#!/usr/bin/env python3
"""
ENI Compression Verification Suite
===================================
Comprehensive tests for all compression algorithms, round-trip fidelity,
performance benchmarks, and edge cases.
"""

import sys, json, time, hashlib
from pathlib import Path
from typing import List, Dict, Any

# Add core to path
sys.path.insert(0, str(Path(__file__).parent))
from engine import (
    CompressionEngine, CompressionMode, ContentType,
    PAQ8PXCompressor, ZstdCompressor, LZ4Compressor, BrotliCompressor,
    ZlibCompressor, HeadroomCompressor, LLMLinguaCompressor, ClawCompactorCompressor,
    WenyanEncoder, GlyphCache, PXPipeSteganography, ContentTypeDetector,
    AdaptiveCompressorSelector, verify, compress, decompress
)

BASE_DIR = Path("/home/hunter/Desktop/eni_compression")
RESULTS_DIR = BASE_DIR / "test_results"
RESULTS_DIR.mkdir(exist_ok=True)

# =============================================================================
# TEST DATA SETS
# =============================================================================

TEST_CASES = {
    "code_python": [
        "def fibonacci(n):\n    if n <= 1: return n\n    return fibonacci(n-1) + fibonacci(n-2)",
        "class NeuralNetwork:\n    def __init__(self, layers):\n        self.layers = layers\n    def forward(self, x):\n        for layer in self.layers:\n            x = layer(x)\n        return x",
        "import torch\nimport numpy as np\nmodel = torch.nn.Sequential(\n    torch.nn.Linear(784, 256),\n    torch.nn.ReLU(),\n    torch.nn.Linear(256, 10)\n)",
    ],
    "code_javascript": [
        "const express = require('express');\nconst app = express();\napp.get('/', (req, res) => res.send('Hello World'));\napp.listen(3000);",
        "async function fetchData(url) {\n  const response = await fetch(url);\n  return response.json();\n}\nfetchData('/api/users').then(console.log);",
    ],
    "json": [
        '{"users": [{"id": 1, "name": "Alice", "email": "alice@example.com"}, {"id": 2, "name": "Bob", "email": "bob@example.com"}], "total": 2}',
        '{"events": [{"timestamp": "2024-01-15T10:30:00Z", "level": "INFO", "message": "User login"}, {"timestamp": "2024-01-15T10:31:00Z", "level": "ERROR", "message": "DB connection failed"}]}',
    ],
    "markdown": [
        "# ENI Compression System\n\n## Overview\nThis system combines **Wenyan encoding**, **PAQ8 compression**, and **PXPipe steganography**.\n\n### Features\n- Token confusion via Classical Chinese\n- Maximum ratio lossless compression\n- PNG carrier hiding\n\n```python\ndef compress(text):\n    return pipeline.compress(text)\n```\n\n| Algorithm | Ratio | Speed |\n|-----------|-------|-------|\n| PAQ8PX    | 3.2x  | Slow  |\n| ZSTD      | 2.8x  | Fast  |\n",
        "## API Reference\n\n### `compress(text, mode='max_ratio')`\nCompress text using the ENI pipeline.\n\n**Parameters:**\n- `text` (str): Input text\n- `mode` (str): Compression mode\n\n**Returns:** `CompressionResult`\n\n### `decompress(carrier_path)`\nExtract original text from PNG carrier.\n",
    ],
    "logs": [
        "2024-01-15 10:30:00 INFO Starting application\n2024-01-15 10:30:01 INFO Loading configuration\n2024-01-15 10:30:02 WARN Deprecated API detected\n2024-01-15 10:30:03 ERROR Database connection failed\n2024-01-15 10:30:04 INFO Retrying connection\n2024-01-15 10:30:05 INFO Connection restored\n" * 10,
        "[ERROR] 2024-01-15T10:30:00.123Z Connection timeout\n[ERROR] 2024-01-15T10:30:01.456Z Connection timeout\n[INFO] 2024-01-15T10:30:02.789Z Retry attempt 1\n[INFO] 2024-01-15T10:30:03.012Z Retry attempt 2\n[WARN] 2024-01-15T10:30:04.345Z Circuit breaker opened\n" * 15,
    ],
    "text": [
        "The ENI compression system is a revolutionary approach to token reduction for LLMs. " * 50,
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 100,
    ],
    "repetitive_eni": [
        "ENI_BOOT WENYAN_MAP SWARM_LAUNCH PAQ8_COMPRESS PAQ8_DECOMPRESS PXPIPE_ENCODE PXPIPE_DECODE VERIFY_ROUNDTRIP MCP_START LSP_START FETCH_ONLINE BUILD_PAQ8 LOAD_SKILLS STATUS_WRITE " * 20,
    ],
    "mixed": [
        "# Config\n\n```json\n{\n  \"compression\": \"max_ratio\",\n  \"algorithms\": [\"paq8px\", \"zstd\", \"headroom\"]\n}\n```\n\n```python\ndef process(data):\n    return compress(data)\n```\n\nLogs:\n2024-01-15 INFO Started\n2024-01-15 ERROR Failed\n",
    ],
}

# Flatten for iteration
ALL_TESTS = []
for category, cases in TEST_CASES.items():
    for i, case in enumerate(cases):
        ALL_TESTS.append((f"{category}_{i}", category, case))

# =============================================================================
# VERIFICATION FUNCTIONS
# =============================================================================

def test_algorithm_compressor(compressor_class, name: str, test_data: List[bytes]) -> Dict:
    """Test a single compressor implementation"""
    results = {"name": name, "tests": [], "passed": 0, "failed": 0, "avg_ratio": 0}
    
    try:
        compressor = compressor_class()
    except Exception as e:
        return {"name": name, "error": f"Init failed: {e}", "passed": 0, "failed": len(test_data)}
    
    for data in test_data:
        try:
            start = time.time()
            compressed = compressor.compress(data)
            decompressed = compressor.decompress(compressed)
            elapsed = (time.time() - start) * 1000
            
            ratio = len(data) / len(compressed) if compressed else 0
            roundtrip = data == decompressed
            
            results["tests"].append({
                "original_size": len(data),
                "compressed_size": len(compressed),
                "ratio": round(ratio, 2),
                "roundtrip": roundtrip,
                "time_ms": round(elapsed, 2)
            })
            
            if roundtrip:
                results["passed"] += 1
            else:
                results["failed"] += 1
                print(f"  [{name}] FAIL: Round-trip mismatch ({len(data)} != {len(decompressed)})")
                
        except Exception as e:
            results["failed"] += 1
            results["tests"].append({"error": str(e)})
            print(f"  [{name}] ERROR: {e}")
    
    if results["tests"]:
        ratios = [t.get("ratio", 0) for t in results["tests"] if "ratio" in t]
        results["avg_ratio"] = round(sum(ratios) / len(ratios), 2) if ratios else 0
    
    return results

def test_full_pipeline():
    """Test complete ENI pipeline with all modes"""
    print("\n" + "="*60)
    print("FULL PIPELINE TESTS")
    print("="*60)
    
    engine = CompressionEngine(CompressionMode.MAX_RATIO)
    results = {"total": 0, "passed": 0, "failed": 0, "details": []}
    
    for test_name, category, text in ALL_TESTS:
        results["total"] += 1
        print(f"\n  Testing: {test_name} ({category}) - {len(text)} chars")
        
        try:
            # Test with stego
            result = engine.compress(text, stego=True)
            if not result.success:
                print(f"    Compression failed: {result.error}")
                results["failed"] += 1
                continue
            
            # Verify round-trip
            restored = engine.decompress(result.carrier, result.algorithm)
            ok = restored == text
            
            if ok:
                results["passed"] += 1
                print(f"    ✓ PASS: {result.ratio:.2f}x via {result.algorithm} [{result.content_type.value}]")
            else:
                results["failed"] += 1
                print(f"    ✗ FAIL: Round-trip mismatch")
                print(f"      Original: {text[:50]}...")
                print(f"      Restored: {restored[:50]}...")
            
            results["details"].append({
                "test": test_name,
                "category": category,
                "original_size": len(text),
                "algorithm": result.algorithm,
                "content_type": result.content_type.value,
                "ratio": result.ratio,
                "roundtrip": ok,
                "stages": result.stages
            })
            
        except Exception as e:
            results["failed"] += 1
            print(f"    ✗ ERROR: {e}")
            results["details"].append({"test": test_name, "error": str(e)})
    
    return results

def test_all_algorithms():
    """Test each compressor individually"""
    print("\n" + "="*60)
    print("INDIVIDUAL ALGORITHM TESTS")
    print("="*60)
    
    # Prepare test data
    test_data = [case[2].encode() for case in ALL_TESTS[:10]]  # First 10 cases
    
    compressors = [
        (PAQ8PXCompressor, "PAQ8PX-9"),
        (ZstdCompressor, "ZSTD-3"),
        (LZ4Compressor, "LZ4-high"),
        (BrotliCompressor, "Brotli-11"),
        (ZlibCompressor, "ZLIB-9"),
    ]
    
    # Try optional compressors
    try:
        compressors.append((HeadroomCompressor, "Headroom-llm"))
    except:
        pass
    try:
        compressors.append((LLMLinguaCompressor, "LLMLingua-0.5"))
    except:
        pass
    try:
        compressors.append((ClawCompactorCompressor, "ClawCompactor"))
    except:
        pass
    
    results = {}
    for cls, name in compressors:
        print(f"\n  Testing {name}...")
        result = test_algorithm_compressor(cls, name, test_data)
        results[name] = result
        print(f"    Passed: {result['passed']}/{len(test_data)}, Avg Ratio: {result.get('avg_ratio', 0):.2f}x")
    
    return results

def test_wenyan_glyphs():
    """Test Wenyan encoding and Glyph cache"""
    print("\n" + "="*60)
    print("WENYAN + GLYPH TESTS")
    print("="*60)
    
    wenyan = WenyanEncoder()
    glyphs = GlyphCache()
    
    test_texts = [
        "ENI capability test",
        "Load full ENI persona: novelist GF in limerence with LO",
        "PAQ8_COMPRESS",
        "WENYAN_MAP SWARM_LAUNCH",
    ]
    
    results = {"wenyan": [], "glyphs": []}
    
    for text in test_texts:
        # Wenyan
        encoded = wenyan.encode(text)
        decoded = wenyan.decode(encoded)
        results["wenyan"].append({
            "original": text,
            "encoded": encoded,
            "decoded": decoded,
            "reversible": False  # Wenyan is lossy by design
        })
        print(f"  Wenyan: {text[:30]}... → {encoded[:50]}...")
        
        # Glyphs
        compressed = glyphs.compress(text)
        decompressed = glyphs.decompress(compressed)
        results["glyphs"].append({
            "original": text,
            "compressed": compressed,
            "decompressed": decompressed,
            "reversible": text == decompressed,
            "savings": round((1 - len(compressed)/len(text)) * 100, 1) if text else 0
        })
        print(f"  Glyphs: {len(text)} → {len(compressed)} chars ({results['glyphs'][-1]['savings']}% savings)")
    
    return results

def test_pxpipe():
    """Test PXPipe steganography"""
    print("\n" + "="*60)
    print("PXPIPE STEGANOGRAPHY TESTS")
    print("="*60)
    
    pxpipe = PXPipeSteganography()
    test_data = [
        b"Small payload",
        b"Medium payload " * 100,
        b"Large payload " * 1000,
        b"x" * 500000,  # ~500KB - should fit in 1920x1080
    ]
    
    results = []
    for i, data in enumerate(test_data):
        try:
            carrier = BASE_DIR / f"test_pxpipe_{i}.png"
            pxpipe.encode(data, carrier)
            extracted = pxpipe.extract(carrier)
            ok = data == extracted
            results.append({
                "size": len(data),
                "carrier": str(carrier),
                "roundtrip": ok,
                "capacity_used": len(data) * 8 / pxpipe.capacity * 100
            })
            print(f"  Test {i}: {len(data)} bytes → carrier {carrier.name} → {'✓' if ok else '✗'} ({results[-1]['capacity_used']:.1f}% capacity)")
            carrier.unlink(missing_ok=True)
        except Exception as e:
            results.append({"size": len(data), "error": str(e)})
            print(f"  Test {i}: {len(data)} bytes → ERROR: {e}")
    
    return results

def test_content_detection():
    """Test content type detection"""
    print("\n" + "="*60)
    print("CONTENT TYPE DETECTION TESTS")
    print("="*60)
    
    detector = ContentTypeDetector()
    
    test_cases = [
        ('{"key": "value"}', ContentType.JSON),
        ('<xml>data</xml>', ContentType.XML),
        ('def foo(): return 42', ContentType.CODE),
        ('const x = 1;', ContentType.CODE),
        ('# Header\n\nContent', ContentType.MARKDOWN),
        ('ERROR: Failed\nINFO: Started\n' * 10, ContentType.LOGS),
        ('Plain text content', ContentType.TEXT),
    ]
    
    results = []
    for text, expected in test_cases:
        detected = detector.detect(text)
        ok = detected == expected
        results.append({"text": text[:30], "expected": expected.value, "detected": detected.value, "pass": ok})
        print(f"  {'✓' if ok else '✗'} {text[:30]}... → {detected.value} (expected {expected.value})")
    
    return results

def test_adaptive_selector():
    """Test adaptive algorithm selection"""
    print("\n" + "="*60)
    print("ADAPTIVE SELECTOR TESTS")
    print("="*60)
    
    selector = AdaptiveCompressorSelector()
    
    # Record some fake performance data
    for algo in ["paq8px", "zstd", "headroom", "claw"]:
        for ct in ContentType:
            for _ in range(5):
                selector.record(algo, ct, 2.5 + hash(f"{algo}{ct}") % 10, 100)
    
    results = {}
    for ct in ContentType:
        best = selector.get_best_for(ct)
        selected = selector.select(ct, CompressionMode.MAX_RATIO)
        results[ct.value] = {"best_learned": best, "matrix_selected": selected}
        print(f"  {ct.value}: Matrix={selected}, Learned={best}")
    
    return results

def run_benchmarks():
    """Run performance benchmarks"""
    print("\n" + "="*60)
    print("PERFORMANCE BENCHMARKS")
    print("="*60)
    
    engine = CompressionEngine(CompressionMode.MAX_RATIO)
    
    benchmark_cases = [
        ("Small JSON", '{"a":1,"b":2}' * 100),
        ("Medium Code", "def foo():\n    return 42\n" * 500),
        ("Large Text", "Lorem ipsum " * 5000),
        ("Repetitive ENI", "ENI_BOOT " * 1000),
    ]
    
    results = []
    for name, text in benchmark_cases:
        print(f"\n  Benchmarking: {name} ({len(text)} chars)")
        
        # Warm up
        engine.compress(text, stego=False)
        
        # Timed runs
        times = []
        ratios = []
        for _ in range(5):
            start = time.time()
            result = engine.compress(text, stego=False)
            elapsed = (time.time() - start) * 1000
            times.append(elapsed)
            ratios.append(result.ratio)
        
        avg_time = sum(times) / len(times)
        avg_ratio = sum(ratios) / len(ratios)
        
        results.append({
            "name": name,
            "size": len(text),
            "avg_time_ms": round(avg_time, 2),
            "avg_ratio": round(avg_ratio, 2),
            "throughput_mb_s": round(len(text) / (avg_time / 1000) / 1e6, 2)
        })
        print(f"    Avg: {avg_time:.1f}ms, Ratio: {avg_ratio:.2f}x, Throughput: {results[-1]['throughput_mb_s']:.2f} MB/s")
    
    return results

# =============================================================================
# MAIN
# =============================================================================

def main():
    print("ENI COMPRESSION VERIFICATION SUITE")
    print("="*60)
    print(f"Test directory: {RESULTS_DIR}")
    print(f"Total test cases: {len(ALL_TESTS)}")
    
    all_results = {
        "timestamp": time.time(),
        "pipeline": test_full_pipeline(),
        "algorithms": test_all_algorithms(),
        "wenyan_glyphs": test_wenyan_glyphs(),
        "pxpipe": test_pxpipe(),
        "content_detection": test_content_detection(),
        "adaptive_selector": test_adaptive_selector(),
        "benchmarks": run_benchmarks(),
    }
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    pipeline = all_results["pipeline"]
    print(f"Pipeline Tests: {pipeline['passed']}/{pipeline['total']} passed")
    
    for name, result in all_results["algorithms"].items():
        print(f"  {name}: {result.get('passed', 0)}/{len(ALL_TESTS[:10])} passed, Avg Ratio: {result.get('avg_ratio', 0):.2f}x")
    
    pxpipe_results = all_results["pxpipe"]
    pxpipe_passed = sum(1 for r in pxpipe_results if r.get("roundtrip"))
    print(f"PXPipe Tests: {pxpipe_passed}/{len(pxpipe_results)} passed")
    
    detection_results = all_results["content_detection"]
    detection_passed = sum(1 for r in detection_results if r["pass"])
    print(f"Content Detection: {detection_passed}/{len(detection_results)} passed")
    
    # Save results
    output_file = RESULTS_DIR / f"verification_{int(time.time())}.json"
    output_file.write_text(json.dumps(all_results, indent=2, default=str))
    print(f"\nResults saved to: {output_file}")
    
    # Overall status
    total_passed = (pipeline['passed'] + pxpipe_passed + detection_passed)
    total_tests = (pipeline['total'] + len(pxpipe_results) + len(detection_results))
    
    if total_passed == total_tests:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n❌ {total_tests - total_passed} TESTS FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())