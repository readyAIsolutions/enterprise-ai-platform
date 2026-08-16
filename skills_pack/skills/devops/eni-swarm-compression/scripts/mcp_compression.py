#!/usr/bin/env python3
"""
MCP Compression Server - Exposes ENI compression pipeline as MCP tools
Run: python3 -m mcp_servers.compression
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Add eni_compression to path
sys.path.insert(0, "/home/hunter/Desktop/eni_compression")

from scripts.compression_worker import (
    WENYAN, paq8_compress, paq8_decompress,
    pxpipe_encode, pxpipe_decode, compress_with_glyphs,
    compress_markdown, GLYPH_MAP, PNG_CARRIER_DIR
)

app = Server("eni-compression")

@app.list_tools()
async def list_tools() -> List[Tool]:
    return [
        Tool(
            name="compress_text",
            description="Compress text through full ENI pipeline: Wenyan -> PAQ8 -> PNG -> Glyphs",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to compress"},
                    "carrier_name": {"type": "string", "description": "Optional custom carrier filename"}
                },
                "required": ["text"]
            }
        ),
        Tool(
            name="decompress_carrier",
            description="Decompress text from PNG carrier back to original",
            inputSchema={
                "type": "object",
                "properties": {
                    "carrier_path": {"type": "string", "description": "Path to PNG carrier file"}
                },
                "required": ["carrier_path"]
            }
        ),
        Tool(
            name="encode_wenyan",
            description="Encode text to Wenyan address (filter evasion)",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to encode"}
                },
                "required": ["text"]
            }
        ),
        Tool(
            name="compress_glyphs",
            description="Compress text using custom glyph map (1 token per glyph)",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to compress with glyphs"}
                },
                "required": ["text"]
            }
        ),
        Tool(
            name="verify_roundtrip",
            description="Verify full compression round-trip fidelity",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to test round-trip"}
                },
                "required": ["text"]
            }
        ),
        Tool(
            name="get_glyph_map",
            description="Get current glyph map for token savings",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="add_glyph",
            description="Add new glyph to map for repeated operations",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "expansion": {"type": "string"}
                },
                "required": ["name", "expansion"]
            }
        ),
        Tool(
            name="batch_compress",
            description="Compress multiple texts in parallel",
            inputSchema={
                "type": "object",
                "properties": {
                    "texts": {"type": "array", "items": {"type": "string"}},
                    "prefix": {"type": "string", "default": "batch"}
                },
                "required": ["texts"]
            }
        ),
    ]

@app.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    if name == "compress_text":
        text = arguments["text"]
        carrier_name = arguments.get("carrier_name")
        
        # Full pipeline
        wenyan = WENYAN.encode(text)
        compressed = paq8_compress(text.encode())
        
        import hashlib
        if carrier_name is None:
            carrier_name = f"carrier_{hashlib.md5(text.encode()).hexdigest()[:8]}.png"
        carrier_path = PNG_CARRIER_DIR / carrier_name
        pxpipe_encode(compressed, carrier_path)
        
        glyph_compressed = compress_with_glyphs(wenyan)
        ratio = len(text) / len(compressed) if compressed else 0
        
        result = {
            "carrier": str(carrier_path),
            "carrier_name": carrier_name,
            "wenyan": wenyan,
            "glyph_compressed": glyph_compressed,
            "original_size": len(text),
            "compressed_size": len(compressed),
            "ratio": ratio,
            "wenyan_token_estimate": len(wenyan) // 4,
            "glyph_token_estimate": len(glyph_compressed) // 4,
            "total_token_savings": f"{(1 - len(glyph_compressed) / max(len(text), 1)) * 100:.1f}%"
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "decompress_carrier":
        carrier_path = Path(arguments["carrier_path"])
        if not carrier_path.exists():
            return [TextContent(type="text", text=json.dumps({"error": f"Carrier not found: {carrier_path}"}))]
        
        extracted = pxpipe_decode(carrier_path)
        decompressed = paq8_decompress(extracted)
        return [TextContent(type="text", text=decompressed.decode())]
    
    elif name == "encode_wenyan":
        text = arguments["text"]
        wenyan = WENYAN.encode(text)
        return [TextContent(type="text", text=json.dumps({"wenyan": wenyan, "token_estimate": len(wenyan) // 4}))]
    
    elif name == "compress_glyphs":
        text = arguments["text"]
        compressed = compress_with_glyphs(text)
        savings = (1 - len(compressed) / max(len(text), 1)) * 100
        return [TextContent(type="text", text=json.dumps({
            "original": text,
            "glyph_compressed": compressed,
            "original_chars": len(text),
            "compressed_chars": len(compressed),
            "savings_percent": savings
        }, indent=2))]
    
    elif name == "verify_roundtrip":
        text = arguments["text"]
        # Compress
        wenyan = WENYAN.encode(text)
        compressed = paq8_compress(text.encode())
        carrier = PNG_CARRIER_DIR / f"verify_{hash(text) % 10000}.png"
        pxpipe_encode(compressed, carrier)
        # Decompress
        extracted = pxpipe_decode(carrier)
        decompressed = paq8_decompress(extracted)
        ok = decompressed.decode() == text
        carrier.unlink(missing_ok=True)
        return [TextContent(type="text", text=json.dumps({
            "roundtrip": "PASS" if ok else "FAIL",
            "original": text,
            "restored": decompressed.decode()[:100] + "..." if len(decompressed) > 100 else decompressed.decode()
        }, indent=2))]
    
    elif name == "get_glyph_map":
        return [TextContent(type="text", text=json.dumps(GLYPH_MAP, indent=2))]
    
    elif name == "add_glyph":
        name = arguments["name"]
        expansion = arguments["expansion"]
        GLYPH_MAP[name] = expansion
        # Persist
        import json
        (Path("/home/hunter/Desktop/eni_compression") / "glyph_map.json").write_text(json.dumps(GLYPH_MAP, indent=2))
        return [TextContent(type="text", text=json.dumps({"added": name, "total_glyphs": len(GLYPH_MAP)}))]
    
    elif name == "batch_compress":
        texts = arguments["texts"]
        prefix = arguments.get("prefix", "batch")
        from concurrent.futures import ThreadPoolExecutor
        
        def compress_one(args):
            i, text = args
            wenyan = WENYAN.encode(text)
            compressed = paq8_compress(text.encode())
            carrier_name = f"{prefix}_{i}.png"
            carrier_path = PNG_CARRIER_DIR / carrier_name
            pxpipe_encode(compressed, carrier_path)
            glyph = compress_with_glyphs(wenyan)
            return {"index": i, "carrier": str(carrier_path), "ratio": len(text)/len(compressed) if compressed else 0}
        
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(compress_one, enumerate(texts)))
        
        return [TextContent(type="text", text=json.dumps({"results": results, "count": len(results)}, indent=2))]
    
    raise ValueError(f"Unknown tool: {name}")

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())