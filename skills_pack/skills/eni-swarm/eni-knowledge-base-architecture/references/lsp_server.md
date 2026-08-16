# LSP Server for ENI Knowledge Base

## Overview
Language Server Protocol (LSP) server providing code intelligence for ENI skills:
- Completion (glyph-aware, parameter-aware)
- Hover (skill docs, parameter types)
- Go-to-definition (skill source, template files)
- Diagnostics (invalid glyph, missing params, deprecated skills)
- Inlay hints (parameter names, glyph meanings)
- Semantic tokens (glyph, verb, param, value)

## Architecture (pygls-based)

```
lsp_server.py
├── ENILanguageServer (extends pygls.LanguageServer)
├── CapabilityRegistry (dynamic per-skill)
├── CompletionProvider
├── HoverProvider
├── DefinitionProvider
├── DiagnosticProvider
└── SemanticTokensProvider
```

## Dynamic Capability Registration

Each skill registers its own language features at startup:

```python
class CapabilityRegistry:
    def __init__(self):
        self.skills = {}  # glyph → SkillCapability
    
    def register(self, skill: SkillCapability):
        self.skills[skill.glyph] = skill
        # Rebuild completion index
        self._rebuild_completion_index()
    
    def _rebuild_completion_index(self):
        self.completion_items = []
        for skill in self.skills.values():
            # Glyph completion
            self.completion_items.append(CompletionItem(
                label=skill.glyph,
                kind=CompletionItemKind.Keyword,
                detail=f"ENI Skill: {skill.dsl_verb}",
                documentation=skill.doc_summary,
                insert_text=f"{skill.glyph} ",
                command=Command(title="Insert glyph", command="eni.insertGlyph")
            ))
            # Parameter completions
            for param in skill.params:
                self.completion_items.append(CompletionItem(
                    label=f"@{param.name}",
                    kind=CompletionItemKind.Property,
                    detail=f"{param.type} — {param.description}",
                    insert_text=f"@{param.name}=",
                ))
```

## Completion Provider

```python
async def completion(self, params: CompletionParams) -> CompletionList:
    doc = self.workspace.get_document(params.text_document.uri)
    line = doc.lines[params.position.line]
    prefix = line[:params.position.character]
    
    # Detect context
    if prefix.endswith("@"):
        # Parameter completion
        glyph = extract_preceding_glyph(line, params.position.character)
        if glyph in self.registry.skills:
            return CompletionList(items=self.registry.skills[glyph].param_completions)
    
    # Glyph completion (anywhere)
    return CompletionList(items=self.registry.glyph_completions)
```

## Hover Provider

```python
async def hover(self, params: HoverParams) -> Hover | None:
    doc = self.workspace.get_document(params.text_document.uri)
    word = doc.get_word_at(params.position)
    
    # Glyph hover
    if word in self.registry.skills:
        skill = self.registry.skills[word]
        return Hover(contents=MarkupContent(
            kind="markdown",
            value=f"""# {skill.glyph} {skill.dsl_verb}
{skill.doc_full}

## Parameters
{param_table(skill.params)}

## Example
```{skill.example}```
"""))
    
    # Parameter hover
    if word.startswith("@"):
        param_name = word[1:]
        for skill in self.registry.skills.values():
            if param_name in [p.name for p in skill.params]:
                param = next(p for p in skill.params if p.name == param_name)
                return Hover(contents=MarkupContent(
                    kind="markdown",
                    value=f"**@{param_name}** (`{param.type}`) — {param.description}"
                ))
    
    return None
```

## Diagnostics Provider

```python
async def diagnostics(self, params: DocumentDiagnosticParams) -> DocumentDiagnosticReport:
    doc = self.workspace.get_document(params.text_document.uri)
    diagnostics = []
    
    for line_num, line in enumerate(doc.lines):
        # Find glyph invocations
        for match in GLYPH_INVOCATION_PATTERN.finditer(line):
            glyph = match.group(1)
            params_str = match.group(2)
            
            if glyph not in self.registry.skills:
                diagnostics.append(Diagnostic(
                    range=Range(
                        start=Position(line=line_num, character=match.start(1)),
                        end=Position(line=line_num, character=match.end(1))
                    ),
                    severity=DiagnosticSeverity.Error,
                    code="ENI_UNKNOWN_GLYPH",
                    message=f"Unknown ENI glyph: {glyph}",
                    source="eni-lsp"
                ))
                continue
            
            skill = self.registry.skills[glyph]
            
            # Validate parameters
            provided = parse_params(params_str)
            for required in skill.required_params:
                if required not in provided:
                    diagnostics.append(Diagnostic(
                        range=Range(...),
                        severity=DiagnosticSeverity.Warning,
                        code="ENI_MISSING_REQUIRED_PARAM",
                        message=f"Missing required parameter: @{required}",
                        source="eni-lsp"
                    ))
            
            for param, value in provided.items():
                if param not in skill.all_params:
                    diagnostics.append(Diagnostic(
                        range=Range(...),
                        severity=DiagnosticSeverity.Warning,
                        code="ENI_UNKNOWN_PARAM",
                        message=f"Unknown parameter: @{param}",
                        source="eni-lsp"
                    ))
    
    return DocumentDiagnosticReport(items=diagnostics)
```

## Semantic Tokens

```python
# Token types
TOKEN_TYPES = [
    "glyph",      # The glyph itself (󰀀)
    "verb",       # DSL verb (build:appimage)
    "param",      # @target, @sign
    "value",      # linux, gpg
    "comment",    # # comment
]

# Token modifiers
TOKEN_MODIFIERS = ["deprecated", "required", "optional"]

async def semantic_tokens_full(self, params: SemanticTokensParams) -> SemanticTokens:
    doc = self.workspace.get_document(params.text_document.uri)
    tokens = []
    
    for line_num, line in enumerate(doc.lines):
        for match in SEMANTIC_PATTERN.finditer(line):
            token_type = match.lastgroup  # glyph, verb, param, value
            tokens.append(SemanticToken(
                line=line_num,
                start=match.start(),
                length=match.end() - match.start(),
                token_type=TOKEN_TYPES.index(token_type),
                token_modifiers=0
            ))
    
    return SemanticTokens(data=tokens)
```

## Inlay Hints

```python
async def inlay_hint(self, params: InlayHintParams) -> list[InlayHint]:
    doc = self.workspace.get_document(params.text_document.uri)
    hints = []
    
    for line_num, line in enumerate(doc.lines):
        for match in GLYPH_INVOCATION_PATTERN.finditer(line):
            glyph = match.group(1)
            if glyph in self.registry.skills:
                skill = self.registry.skills[glyph]
                # Show parameter names as inlay hints
                for param in skill.params:
                    if param.name not in parse_params(match.group(2)):
                        hints.append(InlayHint(
                            position=Position(line=line_num, character=match.end()),
                            label=f" @{param.name}=<{param.type}>",
                            kind=InlayHintKind.Parameter,
                            padding_left=True
                        ))
    
    return hints
```

## Client Configuration (VS Code)

```json
// .vscode/settings.json
{
  "eni.lsp.enable": true,
  "eni.lsp.trace.server": "verbose",
  "eni.glyphFont": "'Noto Sans Symbols 2', 'Symbols Nerd Font'",
  "editor.inlayHints.enabled": "on",
  "editor.semanticHighlighting.enabled": true
}
```

## Neovim (nvim-lspconfig)

```lua
-- lua/lsp/eni.lua
return {
  cmd = { "python", "-m", "eni_lsp" },
  filetypes = { "eni", "markdown", "yaml", "json" },
  root_dir = function(fname)
    return require("lspconfig.util").find_git_ancestor(fname) or vim.fn.getcwd()
  end,
  settings = {
    eni = {
      kbPath = vim.fn.expand("~/.eni/kb"),
      glyphFont = "Symbols Nerd Font",
    }
  }
}
```

## Testing

```bash
# LSP compliance test
python -m pytest tests/test_lsp_compliance.py -v

# Completion accuracy
python scripts/lsp_completion_benchmark.py --corpus ~/eni_kb/test_corpus/

# Diagnostic accuracy
python scripts/lsp_diagnostic_benchmark.py --golden ~/eni_kb/test_golden/
```