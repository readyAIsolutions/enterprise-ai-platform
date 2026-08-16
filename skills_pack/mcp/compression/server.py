#!/usr/bin/env python3
"""MCP Compression Server - Exposes compression pipeline as tools"""
import json, sys
sys.path.insert(0, "/home/hunter/Desktop/eni_compression")
from workers.compression_worker import compress_markdown, WENYAN, paq8_compress, pxpipe_encode

def compress_text(text: str):
    return compress_markdown(text)

def encode_wenyan(text: str):
    return {"wenyan": WENYAN.encode(text)}

if __name__ == "__main__":
    print(json.dumps({"tools": ["compress_text", "encode_wenyan", "paq8_compress", "pxpipe_encode"]}))
