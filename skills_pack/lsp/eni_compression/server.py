#!/usr/bin/env python3
"""LSP Server for .eni compression config files"""
from pygls.server import LanguageServer
from lsprotocol.types import *

ls = LanguageServer("eni-compression", "v1")

GLYPHS = ["ENI_BOOT", "WENYAN_MAP", "SWARM_LAUNCH", "PAQ8_COMPRESS", "PAQ8_DECOMPRESS",
          "PXPIPE_ENCODE", "PXPIPE_DECODE", "VERIFY_ROUNDTRIP", "MCP_START", "LSP_START",
          "FETCH_ONLINE", "BUILD_PAQ8", "LOAD_SKILLS", "STATUS_WRITE"]

@ls.feature(TEXT_DOCUMENT_COMPLETION)
def completions(params: CompletionParams):
    return CompletionList(items=[CompletionItem(label=g) for g in GLYPHS])

@ls.feature(TEXT_DOCUMENT_HOVER)
def hover(params: HoverParams):
    return Hover(contents="ENI Compression Glyph - expands to full operation")

if __name__ == "__main__":
    ls.start_io()
