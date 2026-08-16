#!/usr/bin/env python3
"""
LSP Server for .eni compression config files
Provides completions, hover, diagnostics for glyph names, Wenyan addresses, pipeline stages
Run: python3 -m lsp_servers.eni_compression
"""
import sys
sys.path.insert(0, "/home/hunter/Desktop/eni_compression")

from pygls.server import LanguageServer
from lsprotocol.types import (
    TEXT_DOCUMENT_COMPLETION, TEXT_DOCUMENT_HOVER, TEXT_DOCUMENT_DID_CHANGE,
    TEXT_DOCUMENT_DID_OPEN, TEXT_DOCUMENT_DID_CLOSE, TEXT_DOCUMENT_DEFINITION,
    CompletionItem, CompletionList, CompletionParams, Hover, HoverParams,
    DidChangeTextDocumentParams, DidOpenTextDocumentParams, DidCloseTextDocumentParams,
    DefinitionParams, Location, Position, Range, Diagnostic, DiagnosticSeverity
)
from pygls.workspace import TextDocument

from scripts.compression_worker import GLYPH_MAP, WENYAN

ls = LanguageServer("eni-compression-lsp", "v1")

# All known glyphs for completion
GLYPH_NAMES = list(GLYPH_MAP.keys())

# Pipeline stages for .eni config files
PIPELINE_STAGES = [
    "wenyan_encode", "paq8_compress", "pxpipe_encode", "glyph_compress",
    "wenyan_decode", "paq8_decompress", "pxpipe_decode", "glyph_expand"
]

# Config sections
CONFIG_SECTIONS = ["pipeline", "carrier", "glyphs", "wenyan", "mcp", "lsp", "verify", "output"]

@ls.feature(TEXT_DOCUMENT_COMPLETION)
def completions(params: CompletionParams) -> CompletionList:
    doc = ls.workspace.get_text_document(params.text_document.uri)
    line = doc.lines[params.position.line] if params.position.line < len(doc.lines) else ""
    prefix = line[:params.position.character]
    
    items = []
    
    # Glyph completions (triggered by ⟪ or @)
    if "⟪" in prefix or "@" in prefix:
        for glyph in GLYPH_NAMES:
            items.append(CompletionItem(
                label=glyph,
                detail=f"Glyph: {GLYPH_MAP[glyph][:60]}...",
                documentation=f"Expands to: {GLYPH_MAP[glyph]}"
            ))
    
    # Pipeline stage completions
    if "pipeline:" in line.lower() or "stage:" in line.lower():
        for stage in PIPELINE_STAGES:
            items.append(CompletionItem(label=stage, detail=f"Pipeline stage: {stage}"))
    
    # Config section completions
    if line.strip().endswith(":") and not any(c in line for c in "⟪@"):
        for section in CONFIG_SECTIONS:
            items.append(CompletionItem(label=section, detail=f"Config section: {section}"))
    
    # Wenyan address completions (triggered by 第)
    if "第" in prefix:
        for i in range(0, 19500, 1000):
            addr = f"第{i:04d}址"
            items.append(CompletionItem(label=addr, detail=f"Wenyan address {addr}"))
    
    return CompletionList(is_incomplete=False, items=items)

@ls.feature(TEXT_DOCUMENT_HOVER)
def hover(params: HoverParams) -> Hover:
    doc = ls.workspace.get_text_document(params.text_document.uri)
    line = doc.lines[params.position.line] if params.position.line < len(doc.lines) else ""
    
    # Find word at position
    word = ""
    for i, ch in enumerate(line):
        if i >= params.position.character:
            break
        if ch.isalnum() or ch in "_-⟪第址":
            word += ch
        else:
            word = ""
    # Check next chars
    for ch in line[params.position.character:]:
        if ch.isalnum() or ch in "_-":
            word += ch
        else:
            break
    
    # Glyph hover
    for glyph in GLYPH_NAMES:
        if glyph in word or word in glyph:
            return Hover(contents=f"**Glyph: {glyph}**\n\nExpands to:\n```\n{GLYPH_MAP[glyph]}\n```\n\nToken cost: ~1 (vs {len(GLYPH_MAP[glyph])} chars)")
    
    # Wenyan address hover
    if "第" in word and "址" in word:
        return Hover(contents=f"**Wenyan Address: {word}**\n\nFilter-evasion address. Maps to a capability module.\nNemotron 3 Ultra holds all 19,500 in-context.")
    
    # Pipeline stage hover
    for stage in PIPELINE_STAGES:
        if stage in word:
            descriptions = {
                "wenyan_encode": "Encode text to Classical Chinese (文言文) - confuses tokenizers/filters",
                "paq8_compress": "Maximum-ratio context-mixing compression (PAQ8PXD)",
                "pxpipe_encode": "Hide compressed binary in PNG LSBs - 70% token reduction",
                "glyph_compress": "Replace repeated expansions with 1-token glyphs",
                "wenyan_decode": "Reverse Wenyan encoding",
                "paq8_decompress": "Lossless PAQ8 decompression",
                "pxpipe_decode": "Extract binary from PNG carrier",
                "glyph_expand": "Restore glyph tokens to full expansions",
            }
            return Hover(contents=f"**Pipeline Stage: {stage}**\n\n{descriptions.get(stage, '')}")
    
    return Hover(contents="")

@ls.feature(TEXT_DOCUMENT_DID_CHANGE)
def did_change(params: DidChangeTextDocumentParams):
    """Validate .eni config on change"""
    doc = ls.workspace.get_text_document(params.text_document.uri)
    diagnostics = validate_eni_config(doc)
    ls.publish_diagnostics(doc.uri, diagnostics)

@ls.feature(TEXT_DOCUMENT_DID_OPEN)
def did_open(params: DidOpenTextDocumentParams):
    doc = ls.workspace.get_text_document(params.text_document.uri)
    diagnostics = validate_eni_config(doc)
    ls.publish_diagnostics(doc.uri, diagnostics)

def validate_eni_config(doc: TextDocument) -> List[Diagnostic]:
    """Validate .eni config file for common issues"""
    diagnostics = []
    content = doc.source
    
    # Check for undefined glyphs
    import re
    glyph_refs = re.findall(r"⟪([A-Z_]+)⟫", content)
    for glyph in glyph_refs:
        if glyph not in GLYPH_MAP:
            # Find line
            for i, line in enumerate(doc.lines):
                if f"⟪{glyph}⟫" in line:
                    diagnostics.append(Diagnostic(
                        range=Range(
                            start=Position(line=i, character=line.index(f"⟪{glyph}⟫")),
                            end=Position(line=i, character=line.index(f"⟪{glyph}⟫") + len(glyph) + 4)
                        ),
                        message=f"Undefined glyph: {glyph}",
                        severity=DiagnosticSeverity.Warning
                    ))
    
    # Check for pipeline stages
    if "pipeline:" in content.lower():
        has_stages = any(stage in content for stage in PIPELINE_STAGES)
        if not has_stages:
            diagnostics.append(Diagnostic(
                range=Range(start=Position(line=0, character=0), end=Position(line=0, character=10)),
                message="Pipeline defined but no stages found",
                severity=DiagnosticSeverity.Warning
            ))
    
    # Check carrier config
    if "carrier:" in content.lower():
        if "png" not in content.lower():
            diagnostics.append(Diagnostic(
                range=Range(start=Position(line=0, character=0), end=Position(line=0, character=10)),
                message="Carrier should specify PNG format",
                severity=DiagnosticSeverity.Information
            ))
    
    return diagnostics

@ls.feature(TEXT_DOCUMENT_DEFINITION)
def definition(params: DefinitionParams):
    """Go to definition for glyphs"""
    doc = ls.workspace.get_text_document(params.text_document.uri)
    line = doc.lines[params.position.line] if params.position.line < len(doc.lines) else ""
    
    # Find glyph at position
    import re
    for match in re.finditer(r"⟪([A-Z_]+)⟫", line):
        start, end = match.span(1)
        if start <= params.position.character <= end:
            glyph = match.group(1)
            if glyph in GLYPH_MAP:
                # Return location of glyph definition (glyph_map.json)
                return Location(
                    uri="file:///home/hunter/Desktop/eni_compression/glyph_map.json",
                    range=Range(
                        start=Position(line=0, character=0),
                        end=Position(line=1, character=0)
                    )
                )
    
    return None

if __name__ == "__main__":
    ls.start_io()