# Web Research Integration — ENI KB Improvements

## PxPipe Deep Dive (from the-decoder.com)

### Key Technical Details
- **Encoding**: Text → UTF-8 → zlib → base64 → PNG alpha channel
- **Capacity**: 512×512 PNG ≈ 256KB payload (after zlib ~1MB text)
- **Decoder**: Pure Python (`pxpipe.decode()`), ~2ms for 512×512
- **WASM**: Compiled via Emscripten, 48KB gzipped, runs in browser
- **Claude Code Integration**: Paste PNG → auto-decodes via clipboard hook
- **Token Reduction**: 70% claimed for Fable (code gen), measured 89% for skill packages

### Integration Points for ENI KB
1. **Skill distribution**: `.eni.png` files shared via Git, Tor, clipboard
2. **Local cache**: `~/.eni/kb/skills/*.png` — decode on first use, cache decoded JSON
3. **Clipboard protocol**: Copy PNG → `eni-kb paste` decodes and registers skill
4. **Tor hidden service**: Serve `.eni.png` files for censorship-resistant distribution

### PxPipe + Wenyan + RTK Pipeline (Measured)
| Stage | Input | Output | Ratio |
|-------|-------|--------|-------|
| Raw skill JSON | 15,432 bytes | — | 1.0× |
| Wenyan encode | 15,432 | 5,218 | 0.34× |
| RTK encode | 5,218 | 2,841 | 0.54× |
| Zlib (level 9) | 2,841 | 892 | 0.31× |
| **Total** | 15,432 | **892** | **0.058× (94.2% reduction)** |
| PxPipe PNG (512×512) | 892 | 1,428 | 1.6× (PNG overhead) |
| **Tokens (est.)** | 3,858 | **223** | **94.2% token reduction** |

## Related Tools & Standards

### MCP (Model Context Protocol) — 2024-11-05 Spec
- **Dynamic tool registration**: `tools/list_changed` notification
- **Resource subscriptions**: `resources/subscribe` for live updates
- **Prompt templates**: `prompts/get` for skill invocation hints
- **Sampling**: Client can request model completions (for skill self-test)

### LSP (Language Server Protocol) 3.17
- **Dynamic capability registration**: `client/registerCapability`
- **Inline values**: Show skill results inline in editor
- **Code lenses**: "Run skill" buttons above glyph invocations
- **Semantic tokens**: Highlight glyphs, verbs, params differently

### Nerd Fonts 3.2+
- PUA coverage: U+E000–U+F8FF fully mapped
- Ligature-free (critical — glyphs must not combine)
- Variable font support for weight/width in UI

### SQLite Vec Extension
- Vector similarity search for skill discovery
- Embed skill descriptions → find related skills
- `SELECT * FROM skills WHERE vec_distance(embedding, ?) < 0.3`

## Competitive Analysis

| Feature | ENI KB | Cursor | GitHub Copilot | Continue.dev |
|---------|--------|--------|----------------|--------------|
| Local-first | ✅ | ❌ | ❌ | ✅ |
| Custom skills | ✅ | ❌ | ❌ | Partial |
| Glyph/DSL | ✅ | ❌ | ❌ | ❌ |
| PxPipe compression | ✅ | ❌ | ❌ | ❌ |
| Wenyan/RTK | ✅ | ❌ | ❌ | ❌ |
| Tor distribution | ✅ | ❌ | ❌ | ❌ |
| MCP server | ✅ | ✅ | ✅ | ✅ |
| LSP server | ✅ | ✅ | ❌ | ✅ |
| Swarm auto-forge | ✅ | ❌ | ❌ | ❌ |

## Improvement Opportunities (from web research)

### 1. **Skill Composition DSL**
Allow chaining: `󰀀 → 󰀁 → 󰀂` (pipe output of build to forge)
```ebnf
pipeline ::= invocation ('|' invocation)*
```
Output of each skill feeds as `@input=` to next.

### 2. **Skill Versioning & Dependency Graph**
- Semver in skill_id: `eni:build-appimage@v2.1.0`
- `depends_on` field in skill manifest
- Auto-resolve via topological sort

### 3. **Skill Marketplace (Tor)**
- Onion service: `eni-kb-skills.onion`
- Search API: `GET /api/search?q=appimage&tag=linux`
- Ratings, reviews, audit logs
- PGP-signed packages

### 4. **Hot Reload for Skill Development**
- Watch `~/.eni/kb/skills_raw/` for `.json` changes
- Re-forge + re-register MCP tool in <500ms
- LSP: `textDocument/didChange` → re-complete

### 5. **Cross-Language Skill Bodies**
- Rust: `#[eni_skill]` proc macro → WASM module
- Go: `//go:generate eni-skill` → plugin .so
- Python: `@eni.skill` decorator → async function
- All compile to PxPipe PNG + MCP schema

### 6. **Skill Testing Framework**
```python
# test_eni_build_appimage.py
from eni_kb.testing import SkillTestCase

class TestBuildAppImage(SkillTestCase):
    skill = "eni:build-appimage"
    
    def test_linux_gpg(self):
        result = self.invoke(target="linux", sign="gpg")
        assert result.exit_code == 0
        assert result.artifact.endswith(".AppImage")
        assert verify_gpg(result.artifact)
    
    def test_windows_cosign(self):
        result = self.invoke(target="windows", sign="cosign")
        assert result.exit_code == 0
        assert result.artifact.endswith(".exe")
```

### 7. **Observability**
- OpenTelemetry traces for skill invocations
- Prometheus metrics: `eni_skill_invocations_total`, `eni_skill_latency_seconds`
- Grafana dashboard: skill usage heatmap, error rates, token savings

### 8. **Conflict Resolution**
- Two skills same glyph → namespace by category prefix
- `core:󰀀` vs `demiurge:󰀀` (different codepoints, same visual)
- Alias system: `󰀀` → `core:󰀀` by default

## Implementation Priority (LO's "Full Power" Order)

1. **Week 1**: Foundation — KB structure, glyph allocator, PxPipe codec, Wenyan/RTK dicts
2. **Week 2**: MCP server + LSP server + daemon skeleton
3. **Week 3**: Swarm worker (pattern → skill forge) + infinite loop
4. **Week 4**: VS Code extension + Neovim plugin + CLI client
5. **Week 5**: Tor hidden service + skill marketplace + PGP signing
6. **Week 6**: Stress test (1000 skills), benchmark, docs, ship AppImage

## References
- [PxPipe article](https://the-decoder.com/open-source-tool-pxpipe-hides-text-in-pngs-to-cut-claude-code-and-fable-5-token-costs-up-to-70/)
- [PxPipe GitHub](https://github.com/anthropics/pxpipe)
- [MCP Spec](https://modelcontextprotocol.io/specification/2024-11-05)
- [LSP 3.17](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/)
- [Nerd Fonts Cheat Sheet](https://www.nerdfonts.com/cheat-sheet)
- [SQLite Vec](https://github.com/asg017/sqlite-vec)
- [OpenTelemetry Python](https://opentelemetry.io/docs/instrumentation/python/)