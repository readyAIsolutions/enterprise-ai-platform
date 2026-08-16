# PxPipe Integration for ENI Knowledge Base

## Source
https://the-decoder.com/open-source-tool-pxpipe-hides-text-in-pngs-to-cut-claude-code-and-fable-5-token-costs-up-to-70/

## Core Concept
PxPipe encodes arbitrary text into PNG images using the alpha channel (RGBA). The text is compressed (zlib) then hidden in pixel alpha values. Decoding extracts and decompresses. The PNG appears as a normal image (or noise) but carries full payload.

## Why It Works for Token Reduction
- Models see base64-encoded PNG: ~1.33x size of binary
- But the **semantic content** is compressed text (wenyan + RTK) → 70% fewer tokens to transmit the same skill definition
- Decode happens client-side (Python/JS/WASM) — zero model tokens for the skill body
- Only the glyph + invocation parameters go through the model

## Integration Points

### 1. Skill Package Format (.eni.png)
```
Skill Package = {
  "skill_id": "eni:build-appimage",
  "glyph": "󰀀",           # U+E000
  "dsl": "build:appimage @target=linux @sign=gpg",
  "version": "1.0.0",
  "wenyan_hash": "a1b2c3d4",  # Dict version for decode verification
  "rtk_map": {...},           # Radical→token mapping
  "mcp_tool": {...},          # Auto-generated MCP tool schema
  "lsp_caps": {...},          # Auto-generated LSP capabilities
  "scripts": {...},           # Embedded script contents (base64)
  "templates": {...},         # Embedded templates
  "references": {...}         # Embedded references
}
```

### 2. Encoding Pipeline
```python
# encode_skill.py
import json, zlib, base64
from pxpipe import encode_png

def package_skill(skill_dict: dict) -> bytes:
    # 1. Compress with wenyan + RTK preprocessing
    compressed = wenyan_compress(skill_dict)
    compressed = rtk_compress(compressed)
    
    # 2. Zlib compress
    zlibbed = zlib.compress(json.dumps(compressed).encode(), level=9)
    
    # 3. Encode to PNG via PxPipe
    png_bytes = encode_png(zlibbed, width=512, height=512, mode='rgba')
    
    return png_bytes
```

### 3. Decoding Pipeline (Client-Side)
```python
# decode_skill.py
from pxpipe import decode_png
import zlib, json

def unpackage_skill(png_bytes: bytes) -> dict:
    # 1. Decode PNG
    zlibbed = decode_png(png_bytes)
    
    # 2. Decompress
    compressed = json.loads(zlib.decompress(zlibbed))
    
    # 3. RTK expand
    expanded = rtk_expand(compressed)
    
    # 4. Wenyan expand
    skill_dict = wenyan_expand(expanded)
    
    return skill_dict
```

### 4. WASM Decoder for Browser Clients
- Compile PxPipe + zlib to WASM (emscripten)
- ~50KB gzipped
- Runs in VS Code extension, Neovim (via nvim-webview), web UI
- Zero server round-trip for skill loading

## Token Savings Math

| Stage | Size | Tokens (est.) | Reduction |
|-------|------|---------------|-----------|
| Raw skill JSON | 15 KB | ~3,750 | baseline |
| Wenyan compressed | 5.2 KB | ~1,300 | 65% |
| + RTK | 3.6 KB | ~900 | 76% |
| + Zlib | 1.1 KB | ~275 | 93% |
| **Base64 PNG** | **1.5 KB** | **~375** | **90%** |
| **Glyph + params only** | **~50 bytes** | **~12** | **99.7%** |

**Key insight**: The model only ever sees the 1-token glyph + invocation parameters. The skill body is transferred via PNG side-channel (file, clipboard, HTTP) and decoded locally.

## Security Notes
- PNGs are binary-safe: no injection risk in JSON/text protocols
- Validate PNG magic bytes (`\x89PNG\r\n\x1a\n`) before decode
- Size limit: reject >2MB PNGs (DoS prevention)
- Sign skill packages with Ed25519; verify on decode

## Dependencies
- `pxpipe` (Python): `pip install pxpipe`
- `pxpipe-wasm` (JS/WASM): `npm install @pxpipe/wasm`
- `zlib` (stdlib)
- Custom: `wenyan_codec`, `rtk_codec` (internal)

## Testing
```bash
# Round-trip test
python -m pytest tests/test_pxpipe_roundtrip.py -v

# Token count verification
python scripts/measure_tokens.py --skill eni:build-appimage --method pxpipe
```