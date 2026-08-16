#!/usr/bin/env python3
"""
ENI LSP Server for .eni Compression Config Files
=================================================
Provides completions, hover, diagnostics for .eni files.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from pygls.server import LanguageServer
from lsprotocol.types import *

# Add compression module to path
sys.path.insert(0, "/home/hunter/Desktop/eni_compression")

try:
    from eni_compression_pipeline import GLYPH_MAP
    GLYPHS = list(GLYPH_MAP.keys())
except ImportError:
    GLYPHS = [
        "ENI_BOOT", "WENYAN_MAP", "SWARM_LAUNCH", "PAQ8_COMPRESS", "PAQ8_DECOMPRESS",
        "PXPIPE_ENCODE", "PXPIPE_DECODE", "VERIFY_ROUNDTRIP", "MCP_START", "LSP_START",
        "FETCH_ONLINE", "BUILD_PAQ8", "LOAD_SKILLS", "STATUS_WRITE",
    ]


ls = LanguageServer("eni-compression", "v1.0")


@ls.feature(TEXT_DOCUMENT_COMPLETION)
async def completions(params: CompletionParams) -> CompletionList:
    items = [
        CompletionItem(
            label=g,
            kind=CompletionItemKind.Snippet,
            detail=f"ENI Glyph: {g}",
            insertText=f"⟪{g}⟫",
        )
        for g in GLYPHS
    ]
    return CompletionList(isIncomplete=False, items=items)


@ls.feature(TEXT_DOCUMENT_HOVER)
async def hover(params: HoverParams) -> Optional[Hover]:
    # Get word at position
    doc = ls.workspace.get_text_document(params.text_document.uri)
    word = doc.get_word_at_position(params.position)
    if word and word in GLYPH_MAP:
        expansion = GLYPH_MAP[word]
        return Hover(contents=f"**{word}**\n\n{expansion}")
    return None


@ls.feature(TEXT_DOCUMENT_DID_CHANGE)
async def did_change(params: DidChangeTextDocumentParams):
    # Could add diagnostics here
    pass


@ls.feature(TEXT_DOCUMENT_DID_OPEN)
async def did_open(params: DidOpenTextDocumentParams):
    pass


if __name__ == "__main__":
    ls.start_io()