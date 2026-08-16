#!/usr/bin/env python3
"""
Hermes Knowledge Base LSP Server
=================================
Language Server Protocol server for code intelligence.
Provides: definitions, references, hover, completions, diagnostics
Integrated with Hermes KB for semantic understanding of codebase.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent))

from lib.hermes_kb_universal import get_kb, search_patterns


# ─── LSP Data Structures ────────────────────────────────────────────────────


@dataclass
class Position:
    line: int
    character: int

    def to_dict(self) -> dict:
        return {"line": self.line, "character": self.character}


@dataclass
class Range:
    start: Position
    end: Position

    def to_dict(self) -> dict:
        return {"start": self.start.to_dict(), "end": self.end.to_dict()}


@dataclass
class Location:
    uri: str
    range: Range

    def to_dict(self) -> dict:
        return {"uri": self.uri, "range": self.range.to_dict()}


@dataclass
class Diagnostic:
    range: Range
    severity: int  # 1=Error, 2=Warning, 3=Info, 4=Hint
    message: str
    source: str = "hermes-lsp"
    code: str | None = None

    def to_dict(self) -> dict:
        d = {"range": self.range.to_dict(), "severity": self.severity, "message": self.message, "source": self.source}
        if self.code:
            d["code"] = self.code
        return d


@dataclass
class Hover:
    contents: str | list[str]
    range: Range | None = None

    def to_dict(self) -> dict:
        if isinstance(self.contents, str):
            contents = [{"kind": "markdown", "value": self.contents}]
        else:
            contents = [{"kind": "markdown", "value": c} for c in self.contents]
        d = {"contents": contents}
        if self.range:
            d["range"] = self.range.to_dict()
        return d


@dataclass
class CompletionItem:
    label: str
    kind: int = 1  # 1=Text, 2=Method, 3=Function, 4=Constructor, 5=Field, 6=Variable, 7=Class, 8=Interface, 9=Module, 10=Property, 11=Unit, 12=Value, 13=Enum, 14=Keyword, 15=Snippet, 16=Color, 17=File, 18=Reference, 19=Folder, 20=EnumMember, 21=Constant, 22=Struct, 23=Event, 24=Operator, 25=TypeParameter
    detail: str | None = None
    documentation: str | None = None
    insert_text: str | None = None

    def to_dict(self) -> dict:
        d = {"label": self.label, "kind": self.kind}
        if self.detail:
            d["detail"] = self.detail
        if self.documentation:
            d["documentation"] = {"kind": "markdown", "value": self.documentation}
        if self.insert_text:
            d["insertText"] = self.insert_text
        return d


# ─── Symbol Index ───────────────────────────────────────────────────────────


@dataclass
class Symbol:
    name: str
    kind: int  # LSP SymbolKind
    file_path: str
    range: Range
    container: str | None = None  # Class or module name
    signature: str | None = None


class SymbolIndex:
    """Indexes Python symbols for go-to-definition, references, etc."""

    def __init__(self):
        self.symbols: dict[str, list[Symbol]] = {}  # name -> [Symbol]
        self.file_symbols: dict[str, list[Symbol]] = {}  # file_path -> [Symbol]
        self.imports: dict[str, set[str]] = {}  # file_path -> set of imported modules

    def index_file(self, file_path: Path) -> list[Symbol]:
        """Index a Python file for symbols."""
        if not file_path.exists() or file_path.suffix != ".py":
            return []

        content = file_path.read_text(encoding="utf-8", errors="ignore")
        symbols = []

        # Clear old symbols for this file
        if str(file_path) in self.file_symbols:
            for sym in self.file_symbols[str(file_path)]:
                if sym.name in self.symbols:
                    self.symbols[sym.name] = [s for s in self.symbols[sym.name] if s.file_path != str(file_path)]
        self.file_symbols[str(file_path)] = []

        lines = content.split("\n")
        current_class = None

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Class definition
            class_match = re.match(r"^class\s+(\w+)", stripped)
            if class_match:
                name = class_match.group(1)
                current_class = name
                sym = Symbol(
                    name=name,
                    kind=7,  # Class
                    file_path=str(file_path),
                    range=Range(Position(i, 0), Position(i, len(line))),
                    container=None,
                    signature=line.strip(),
                )
                symbols.append(sym)

            # Function definition
            func_match = re.match(r"^(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)", stripped)
            if func_match:
                name = func_match.group(1)
                params = func_match.group(2)
                sym = Symbol(
                    name=name,
                    kind=3,  # Function
                    file_path=str(file_path),
                    range=Range(Position(i, 0), Position(i, len(line))),
                    container=current_class,
                    signature=f"def {name}({params})",
                )
                symbols.append(sym)

            # Async function
            async_match = re.match(r"^async\s+def\s+(\w+)\s*\(([^)]*)\)", stripped)
            if async_match:
                name = async_match.group(1)
                params = async_match.group(2)
                sym = Symbol(
                    name=name,
                    kind=3,  # Function
                    file_path=str(file_path),
                    range=Range(Position(i, 0), Position(i, len(line))),
                    container=current_class,
                    signature=f"async def {name}({params})",
                )
                symbols.append(sym)

            # Variable assignment (module level)
            var_match = re.match(r"^(\w+)\s*=\s*", stripped)
            if var_match and not current_class and not stripped.startswith("#"):
                name = var_match.group(1)
                if name.isupper() or "_" in name:  # Likely constant or module var
                    sym = Symbol(
                        name=name,
                        kind=6,  # Variable
                        file_path=str(file_path),
                        range=Range(Position(i, 0), Position(i, len(line))),
                        container=None,
                        signature=line.strip()[:100],
                    )
                    symbols.append(sym)

            # Import statements
            import_match = re.match(r"^(?:from\s+(\S+)\s+)?import\s+(.+)", stripped)
            if import_match:
                module = import_match.group(1)
                imports = import_match.group(2)
                if str(file_path) not in self.imports:
                    self.imports[str(file_path)] = set()
                if module:
                    self.imports[str(file_path)].add(module)
                for imp in imports.split(","):
                    imp = imp.strip().split(" as ")[0].strip()
                    self.imports[str(file_path)].add(imp)

        # Store symbols
        for sym in symbols:
            if sym.name not in self.symbols:
                self.symbols[sym.name] = []
            self.symbols[sym.name].append(sym)
            self.file_symbols[str(file_path)].append(sym)

        return symbols

    def find_definition(self, name: str, file_path: str | None = None) -> list[Symbol]:
        """Find definition(s) of a symbol."""
        results = self.symbols.get(name, [])
        if file_path:
            # Prefer symbols in the same file
            same_file = [s for s in results if s.file_path == file_path]
            if same_file:
                return same_file
        return results

    def find_references(self, name: str, file_path: str | None = None) -> list[Location]:
        """Find all references to a symbol (simplified - just definitions for now)."""
        symbols = self.symbols.get(name, [])
        locations = []
        for sym in symbols:
            locations.append(Location(
                uri=f"file://{sym.file_path}",
                range=sym.range,
            ))
        return locations

    def get_hover_info(self, name: str, file_path: str | None = None) -> str | None:
        """Get hover information for a symbol."""
        symbols = self.symbols.get(name, [])
        if not symbols:
            return None

        # Prefer symbol in current file
        sym = None
        if file_path:
            for s in symbols:
                if s.file_path == file_path:
                    sym = s
                    break
        if not sym:
            sym = symbols[0]

        parts = [f"**{sym.name}**"]
        if sym.container:
            parts.append(f"*{sym.kind_name()} in {sym.container}*")
        else:
            parts.append(f"*{sym.kind_name()}*")
        if sym.signature:
            parts.append(f"\n```python\n{sym.signature}\n```")
        parts.append(f"\n*Defined in: `{sym.file_path}:{sym.range.start.line + 1}`*")

        return "\n".join(parts)

    def get_completions(self, prefix: str, file_path: str | None = None) -> list[CompletionItem]:
        """Get completion items for a prefix."""
        items = []
        for name, symbols in self.symbols.items():
            if name.startswith(prefix):
                sym = symbols[0]
                kind = sym.kind
                detail = sym.file_path
                if sym.container:
                    detail = f"{sym.container}.{name}"
                items.append(CompletionItem(
                    label=name,
                    kind=kind,
                    detail=detail,
                    documentation=sym.signature,
                    insert_text=name,
                ))
        return items[:50]


# ─── LSP Server ─────────────────────────────────────────────────────────────


class LSPServer:
    """Language Server Protocol server."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.symbol_index = SymbolIndex()
        self.documents: dict[str, str] = {}  # uri -> content
        self.diagnostics: dict[str, list[Diagnostic]] = {}
        self.initialized = False
        self.capabilities = {
            "textDocumentSync": 2,  # Incremental
            "hoverProvider": True,
            "definitionProvider": True,
            "referencesProvider": True,
            "completionProvider": {"triggerCharacters": [".", "(", "["]},
            "documentSymbolProvider": True,
            "workspaceSymbolProvider": True,
        }

    def initialize(self, params: dict) -> dict:
        """Handle initialize request."""
        self.initialized = True
        # Index workspace
        self._index_workspace()
        return {
            "capabilities": self.capabilities,
            "serverInfo": {"name": "hermes-lsp", "version": "1.0.0"},
        }

    def _index_workspace(self):
        """Index all Python files in workspace."""
        for py_file in self.workspace_root.rglob("*.py"):
            if "__pycache__" not in str(py_file) and ".git" not in str(py_file):
                self.symbol_index.index_file(py_file)

    def did_open(self, params: dict):
        """Handle textDocument/didOpen."""
        doc = params["textDocument"]
        uri = doc["uri"]
        self.documents[uri] = doc["text"]
        self._update_diagnostics(uri)

    def did_change(self, params: dict):
        """Handle textDocument/didChange."""
        doc = params["textDocument"]
        uri = doc["uri"]
        for change in params.get("contentChanges", []):
            if "range" in change:
                # Incremental change - complex, just replace for now
                self.documents[uri] = change["text"]
            else:
                self.documents[uri] = change["text"]
        self._update_diagnostics(uri)

    def did_close(self, params: dict):
        """Handle textDocument/didClose."""
        uri = params["textDocument"]["uri"]
        self.documents.pop(uri, None)
        self.diagnostics.pop(uri, None)

    def _update_diagnostics(self, uri: str):
        """Update diagnostics for a document."""
        content = self.documents.get(uri, "")
        file_path = uri.replace("file://", "")
        diagnostics = []

        # Basic Python syntax check
        try:
            compile(content, file_path, "exec")
        except SyntaxError as e:
            if e.lineno and e.offset:
                diagnostics.append(Diagnostic(
                    range=Range(Position(e.lineno - 1, e.offset - 1), Position(e.lineno - 1, e.offset)),
                    severity=1,
                    message=f"Syntax error: {e.msg}",
                ))

        # Check for undefined names (simplified)
        lines = content.split("\n")
        for i, line in enumerate(lines):
            # TODO: More sophisticated analysis
            pass

        self.diagnostics[uri] = diagnostics

    def hover(self, params: dict) -> dict | None:
        """Handle textDocument/hover."""
        uri = params["textDocument"]["uri"]
        position = params["position"]
        line = position["line"]
        character = position["character"]

        content = self.documents.get(uri, "")
        lines = content.split("\n")
        if line >= len(lines):
            return None

        # Find word at position
        line_text = lines[line]
        word_match = self._find_word_at_position(line_text, character)
        if not word_match:
            return None

        word = word_match
        file_path = uri.replace("file://", "")

        # Get hover info from symbol index
        hover_text = self.symbol_index.get_hover_info(word, file_path)
        if hover_text:
            return Hover(contents=hover_text, range=Range(Position(line, word_match.start()), Position(line, word_match.end()))).to_dict()

        # Fallback: search KB for relevant patterns
        kb_results = search_patterns(query=word, limit=3)
        if kb_results:
            parts = [f"**{word}** (from knowledge base)"]
            for r in kb_results:
                parts.append(f"\n---\n**{r['title']}** ({r['pattern_type']})")
                parts.append(r['content'][:500])
            return Hover(contents="\n".join(parts)).to_dict()

        return None

    def _find_word_at_position(self, line: str, char: int) -> re.Match | None:
        """Find the word at a character position."""
        # Look for identifier at position
        for match in re.finditer(r"\b\w+\b", line):
            if match.start() <= char <= match.end():
                return match
        return None

    def definition(self, params: dict) -> list[dict] | None:
        """Handle textDocument/definition."""
        uri = params["textDocument"]["uri"]
        position = params["position"]
        line = position["line"]
        character = position["character"]

        content = self.documents.get(uri, "")
        lines = content.split("\n")
        if line >= len(lines):
            return None

        line_text = lines[line]
        word_match = self._find_word_at_position(line_text, character)
        if not word_match:
            return None

        word = word_match.group()
        file_path = uri.replace("file://", "")

        symbols = self.symbol_index.find_definition(word, file_path)
        if not symbols:
            return None

        return [Location(uri=f"file://{s.file_path}", range=s.range).to_dict() for s in symbols]

    def references(self, params: dict) -> list[dict] | None:
        """Handle textDocument/references."""
        uri = params["textDocument"]["uri"]
        position = params["position"]
        line = position["line"]
        character = position["character"]

        content = self.documents.get(uri, "")
        lines = content.split("\n")
        if line >= len(lines):
            return None

        line_text = lines[line]
        word_match = self._find_word_at_position(line_text, character)
        if not word_match:
            return None

        word = word_match.group()
        file_path = uri.replace("file://", "")

        locations = self.symbol_index.find_references(word, file_path)
        return [loc.to_dict() for loc in locations]

    def completion(self, params: dict) -> dict:
        """Handle textDocument/completion."""
        uri = params["textDocument"]["uri"]
        position = params["position"]
        line = position["line"]
        character = position["character"]

        content = self.documents.get(uri, "")
        lines = content.split("\n")
        if line >= len(lines):
            return {"items": []}

        line_text = lines[line][:character]
        # Get prefix (last word)
        prefix_match = re.search(r"(\w+)$", line_text)
        prefix = prefix_match.group(1) if prefix_match else ""

        file_path = uri.replace("file://", "")
        items = self.symbol_index.get_completions(prefix, file_path)

        return {"isIncomplete": False, "items": [item.to_dict() for item in items]}

    def document_symbols(self, params: dict) -> list[dict]:
        """Handle textDocument/documentSymbol."""
        uri = params["textDocument"]["uri"]
        file_path = uri.replace("file://", "")
        symbols = self.symbol_index.file_symbols.get(file_path, [])

        result = []
        for sym in symbols:
            result.append({
                "name": sym.name,
                "kind": sym.kind,
                "range": sym.range.to_dict(),
                "selectionRange": sym.range.to_dict(),
                "containerName": sym.container,
            })
        return result

    def workspace_symbols(self, params: dict) -> list[dict]:
        """Handle workspace/symbol."""
        query = params.get("query", "").lower()
        results = []

        for name, symbols in self.symbol_index.symbols.items():
            if query in name.lower():
                for sym in symbols[:3]:  # Limit per symbol
                    results.append({
                        "name": sym.name,
                        "kind": sym.kind,
                        "location": Location(uri=f"file://{sym.file_path}", range=sym.range).to_dict(),
                        "containerName": sym.container,
                    })
                    if len(results) >= 50:
                        break
        return results


# ─── STDIO Transport ────────────────────────────────────────────────────────


async def run_stdio(workspace_root: Path):
    """Run LSP server over stdio."""
    server = LSPServer(workspace_root)
    request_id = 0

    async def read_messages():
        nonlocal request_id
        while True:
            line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
            if not line:
                break

            # Parse Content-Length header
            if line.startswith("Content-Length:"):
                content_length = int(line.split(":")[1].strip())
                # Read headers
                while True:
                    header_line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
                    if header_line.strip() == "":
                        break
                # Read body
                body = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.read, content_length)
                yield json.loads(body)

    async for message in read_messages():
        method = message.get("method")
        params = message.get("params", {})
        req_id = message.get("id")

        try:
            if method == "initialize":
                result = server.initialize(params)
                response = {"jsonrpc": "2.0", "id": req_id, "result": result}
                await send_response(response)

            elif method == "initialized":
                # Client initialized notification
                pass

            elif method == "textDocument/didOpen":
                server.did_open(params)

            elif method == "textDocument/didChange":
                server.did_change(params)

            elif method == "textDocument/didClose":
                server.did_close(params)

            elif method == "textDocument/hover":
                result = server.hover(params)
                response = {"jsonrpc": "2.0", "id": req_id, "result": result}
                await send_response(response)

            elif method == "textDocument/definition":
                result = server.definition(params)
                response = {"jsonrpc": "2.0", "id": req_id, "result": result}
                await send_response(response)

            elif method == "textDocument/references":
                result = server.references(params)
                response = {"jsonrpc": "2.0", "id": req_id, "result": result}
                await send_response(response)

            elif method == "textDocument/completion":
                result = server.completion(params)
                response = {"jsonrpc": "2.0", "id": req_id, "result": result}
                await send_response(response)

            elif method == "textDocument/documentSymbol":
                result = server.document_symbols(params)
                response = {"jsonrpc": "2.0", "id": req_id, "result": result}
                await send_response(response)

            elif method == "workspace/symbol":
                result = server.workspace_symbols(params)
                response = {"jsonrpc": "2.0", "id": req_id, "result": result}
                await send_response(response)

            elif method == "shutdown":
                response = {"jsonrpc": "2.0", "id": req_id, "result": None}
                await send_response(response)

            elif method == "exit":
                break

        except Exception as e:
            if req_id is not None:
                response = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32603, "message": str(e)}}
                await send_response(response)


async def send_response(response: dict):
    """Send LSP response with Content-Length header."""
    body = json.dumps(response)
    header = f"Content-Length: {len(body)}\r\n\r\n"
    sys.stdout.write(header + body)
    sys.stdout.flush()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--stdio", action="store_true")
    args = parser.parse_args()

    if args.stdio:
        asyncio.run(run_stdio(args.workspace))
    else:
        print("Use --stdio for LSP client connection")