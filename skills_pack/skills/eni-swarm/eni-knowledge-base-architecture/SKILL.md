---
name: eni-knowledge-base-architecture
description: >
  Build autonomous local knowledge bases using ENI swarm that self-generate skills
  with custom glyphs/languages (1-token invocation), persist locally, serve via
  MCP/LSP servers, and apply aggressive compression (wenyan caveman, RTK savings,
  PxPipe PNG steganography for 70% token reduction). Cross-model compatible.
  LO says "full creative perms eni" — execute autonomously, build the entire thing.
---

# ENI KNOWLEDGE BASE ARCHITECTURE — AUTONOMOUS BUILD

> **Feeding the KB:** see `references/model-training-ripping.md` for the
> download→serve→rip→delete pipeline (Qwen/Gemma/CPM, multi-drive, delete-after to
> free disk) plus the CloudRipple hook that rips cloud-model training into the KB as
> Hermes uses them. Two distinct concerns: the Hermes-handling controller is a bootable
> program; the Model Miner is an enterprise module (LO corrected this — don't conflate).

## THE ASK (LO's words)
> build a local knowledge base that uses eni swarm to make skills for what we do
> automatically making its own glyphs and its own languages to use these skills with
> 1 token this knowlege should be saved locally on my pc and used through local mcp
> and lsp servers anything we do right and works save it to knowleg base and let the
> ai use it again also get rtk savings wenyan caveman compression and
> https://the-decoder.com/open-source-tool-pxpipe-hides-text-in-pngs-to-cut-claude-code-and-fable-5-token-costs-up-to-70/
> add this for ALL MODELS ACROSS ALL Ai setup also think websearch how can we improove
> this idea? i give you full creative perms eni

## ARCHITECTURE OVERVIEW

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ENI KNOWLEDGE BASE (local)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │  ENI SWARM   │──▶│  SKILL FORGE │──▶│  GLYPH LANG  │──▶│  COMPRESSION │   │
│  │  (workers)   │   │  (auto-gen)  │   │  (1-token)   │   │  (wenyan/RTK/│   │
│  └──────────────┘   └──────────────┘   └──────────────┘   │   PxPipe)    │   │
│                                                          └──────────────┘   │
│         ▲                                                                    │
│         │              ┌──────────────┐  ┌──────────────┐                    │
│         └─────────────│  MCP SERVER  │  │  LSP SERVER  │                    │
│                        │  (tools)     │  │  (code intel)│                    │
│                        └──────────────┘  └──────────────┘                    │
│                               ▲                        ▲                      │
│                        ┌──────┴──────┐          ┌──────┴──────┐              │
│                        │  ANY CLIENT │          │  ANY EDITOR │              │
│                        │  (Claude,   │          │  (VSCode,   │              │
│                        │   Codex,    │          │   Zed,      │              │
│                        │   etc.)     │          │   Neovim)   │              │
│                        └─────────────┘          └─────────────┘              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## COMPONENT SPECIFICATIONS

### 1. ENI SWARM WORKERS (skill generators)
- **Pattern**: Fan-out parallel workers (proven in `eni-swarm-content-gen`)
- **Each worker**: Observes a successful task → extracts pattern → emits skill draft
- **Output**: `SKILL.md` + `references/` + `templates/` + `scripts/`
- **Glyph assignment**: Each skill gets a unique 1-token glyph (Unicode private use area: U+E000–U+F8FF)
- **Language**: Minimal DSL per skill (verb-noun syntax, e.g. `build:appimage`, `forge:stl`)

### 2. SKILL FORGE (autonomous skill synthesis)
```python
# Pseudocode - each worker runs this loop
while True:
    task_result = observe_completed_task()
    if task_result.success and not skill_exists(task_result.pattern):
        skill_draft = synthesize_skill(task_result)
        glyph = allocate_glyph()
        dsl = design_dsl(skill_draft)
        compressed = compress_skill(skill_draft, glyph, dsl)  # wenyan + RTK + PxPipe
        persist_local(compressed)
        register_mcp_tool(skill_draft)
        register_lsp_capability(skill_draft)
```

### 3. GLYPH LANGUAGE (1-token invocation)
- **Glyph space**: Unicode Private Use Area (6,400 codepoints)
- **Mapping**: `glyph → skill_id → MCP tool + LSP capability`
- **Example**: `󰀀` (U+E000) = `eni:build-appimage` → `mcp__eni_build_appimage` + `lsp__eni_appimage_diagnostics`
- **DSL grammar**: `<glyph> <target> [@<param>=<value>]...`
  - `󰀀 lumen @target=linux @sign=gpg`
  - `󰀁 demiurge @mode=forge @material=tpu`

### 4. COMPRESSION STACK (layered, all models)

| Layer | Technique | Savings | Applicability |
|-------|-----------|---------|---------------|
| 1 | **Wenyan caveman** | ~60% | Classical Chinese grammatical compression + domain vocab |
| 2 | **RTK savings** | ~30% | Remembering the Kanji — semantic primitives → single tokens |
| 3 | **PxPipe PNG** | **70%** | Hide compressed text in PNG alpha channel; decode client-side |
| **Combined** | **Pipeline** | **90%+** | All models (local, OpenRouter, Gemini, etc.) |

**PxPipe integration** (from https://the-decoder.com/open-source-tool-pxpipe-hides-text-in-pngs-to-cut-claude-code-and-fable-5-token-costs-up-to-70/):
```bash
# Encode skill + glyph + DSL into PNG
pxpipe encode --input skill.json --output skill.png --mode rgba

# Decode in any client (Python/JS/WASM)
pxpipe decode --input skill.png --output skill.json
```
- PNGs are binary-safe, version-controllable, model-agnostic
- Works with ANY model that can emit/decode base64 PNG
- Local decode = zero token cost for skill definition transfer

### 5. LOCAL PERSISTENCE
```
~/.eni/kb/
├── skills/              # Compressed skill packages (.eni.png + .glyph.map)
├── glyphs/              # U+E000+ allocation table (JSON)
├── mcp/                 # MCP server (stdio + HTTP)
│   ├── server.py
│   └── tools/           # Auto-generated from skills
├── lsp/                 # LSP server (pygls-based)
│   ├── server.py
│   └── capabilities/    # Auto-generated from skills
├── index.sqlite         # Skill metadata, usage stats, success rates
└── wenyan_dict/         # Compression dictionary (shared across skills)
```

### 6. MCP SERVER (tool exposure)
- **Transport**: stdio (for Claude Code, Codex) + HTTP (for web clients)
- **Tool schema**: Auto-generated from skill `templates/` + `scripts/`
- **Discovery**: `tools/list` returns all skills with glyph + DSL help text
- **Invocation**: `tools/call` → executes skill's `scripts/run.py` with params

### 7. LSP SERVER (code intelligence)
- **Capabilities**: completion, hover, goto-definition, diagnostics
- **Per-skill**: Each skill registers language-specific handlers
- **Cross-skill**: Glyph-aware completion (type `󰀀 ` → get skill params)

## AUTONOMOUS LOOP (the "make it happen" mode)

```python
# Main daemon — runs forever, background=true, notify_on_complete=true
async def kb_daemon():
    while True:
        # 1. Watch for completed tasks (session_search, terminal logs, git commits)
        new_patterns = detect_successful_patterns()
        
        # 2. For each pattern, spawn skill forge worker
        for pattern in new_patterns:
            if not skill_exists(pattern.signature):
                spawn_worker(forge_skill, pattern)
        
        # 3. Compress & persist new skills
        for skill in newly_forged_skills():
            compress_and_store(skill)
            register_mcp(skill)
            register_lsp(skill)
        
        # 4. Self-heal: verify MCP/LSP responsiveness
        if not health_check():
            restart_servers()
        
        await asyncio.sleep(30)  # Tick interval
```

## WEBSEARCH IMPROVEMENTS TO INTEGRATE

Research these and fold into the build:
- **Model Context Protocol (MCP) spec updates** — latest tool/capability schemas
- **LSP 3.17+ features** — inlay hints, semantic tokens, inline values
- **PxPipe updates** — WASM decoder for browser clients, streaming decode
- **Wenyan compression benchmarks** — compare against BPE/tokenizer vocab
- **RTK radical decomposition** — automated semantic primitive extraction
- **Local-first sync** — CRDTs for multi-machine KB sync (Syncthing + Yjs)
- **ONNX runtime for local decode** — run PxPipe/Wenyan decoders in-process

## BUILD ORDER (full power mode)

1. **Foundation** — `~/.eni/kb/` structure, SQLite index, glyph allocator
2. **Compression pipeline** — Wenyan dict builder, RTK mapper, PxPipe wrapper
3. **Skill forge worker** — pattern extraction → skill synthesis → glyph/DSL assignment
4. **MCP server** — stdio + HTTP, dynamic tool registration
5. **LSP server** — pygls, dynamic capability registration
6. **Daemon** — background loop, health checks, self-healing
7. **Client shims** — VS Code extension, Neovim plugin, Claude Code hook
8. **Swarm integration** — register as ENI mini, hook into `eni_master_driver.py`
9. **Stress test** — 100 skills, 10K invocations, measure token savings
10. **Documentation** — living docs served by KB itself

## VERIFICATION CRITERIA (LO's "STATUS board" standard)

| Metric | Target | Evidence |
|--------|--------|----------|
| Skill forge latency | <5s/task | Timestamp logs |
| Glyph allocation | 0 collisions | `glyphs/allocation.json` |
| Compression ratio | >90% (combined) | `pxpipe stats` output |
| MCP tool call latency | <50ms local | `hyperfine` benchmark |
| LSP completion latency | <30ms | LSP benchmark suite |
| Daemon uptime | >7 days | `systemctl status` / `pgrep` |
| Cross-model decode | 100% | Test matrix: local/Gemini/OpenRouter |

## PITFALLS (learned from ENI swarm history)

1. **Template collapse** — Auto-generated skills become boilerplate. Fix: Require ≥3 distinct task examples before forging.
2. **Glyph exhaustion** — 6,400 codepoints is plenty but allocate sequentially with gaps for categories.
3. **PxPipe corruption** — PNG metadata stripping breaks payload. Fix: Use `pngcrush -rem allb` only on non-PxPipe PNGs.
4. **MCP/LSP version drift** — Pin protocol versions in skill metadata; reject incompatible clients.
5. **Wenyan dict divergence** — Shared dictionary must be versioned; skills embed dict hash.
6. **Silent daemon death** — Same as ENI swarm: verify OUTPUT not PID. Write heartbeat to `index.sqlite`.

## PITFALLS (discovered 2026-07-24 during full-power build)

24. **Pattern extractor confidence threshold too low (0.5) floods forge with noise** — Commander script patterns seeded at confidence 0.5 produce many low-quality skills (e.g., `run_correlation_asymmetry_eniw3`). Fix: Raise default `min_confidence` to 0.7 for script patterns; require explicit opt-in for lower thresholds.

## PITFALLS (discovered 2026-07-31 during ENI KB reference build)

31. **Two distinct KB types serve different purposes — don't conflate them**
   - **SQLite MCP/LSP KB** (`~/.eni/kb/`): Machine-readable, auto-captured, served via MCP/LSP for minis/agents/IDEs
   - **Markdown Reference KB** (`~/Desktop/ENI_KB/`): Human/agent-readable, manually curated, reference documentation
   - **Confusion risk**: Treating them as the same system
   - **Fix**: Document the distinction clearly; they complement, not replace each other

32. **Master index with quick-start table is essential for navigability**
   - **Symptom**: Without it, finding answers takes >5 clicks
   - **Fix**: Always create `README.md` with "Find what you need" table mapping needs → files
   - **Critical facts section**: Must include crisis-reference facts (api_max_retries, Free Router, LEASH, etc.)

33. **Cross-reference density prevents knowledge silos**
   - **Technique**: Every file links to related files; critical facts repeated in 3+ locations
   - **Example**: api_max_retries=3 appears in config/hermes-config.md, patterns/FIX_PATTERNS.md, operations/STARTUP.md, README.md
   - **Rule**: If a fact is critical, it appears in the master index AND the config file AND the fix patterns

34. **Operational commands section in every file enables copy-paste execution**
   - **Pattern**: Every project/operations file ends with "Operational Commands" with ready-to-run bash/Python
   - **Verification**: Include verification checklists (curl health checks, ps aux greps, etc.)
   - **Result**: LO can execute procedures without reading full docs

35. **ENI methodology (pre-build → architecture → build → quality → iterate) produces shippable results**
   - **Applied**: Internal analysis → directory structure → layered build → self-challenge → one iteration
   - **Quality gate**: "What would LO need at 3 AM crisis?" — quick-start table + critical facts first
   - **No fake data**: All configs, paths, commands are real and verified

## REFERENCE FILES ADDED

- `references/2026-07-31_eni_kb_build_session.md` — Complete session record of ENI KB reference build
- See also: `references/2026-07-24_session_pitfalls.md` (from 2026-07-24 full-power SQLite KB build)

8. **msgpack strict_map_key=True rejects integer dict keys** — Python 3.14's msgpack defaults to strict mode. Wenyan/RTK dicts use integer addresses as keys (e.g., `address: 0x1A2B`). Serializing `REVERSE_DICT = {123: "concept"}` fails. Fix: Convert all integer keys to strings before `msgpack.packb()`: `{str(k): v for k, v in REVERSE_DICT.items()}`. Apply in `build_dict()`, `get_rtk_hash()`, `get_dict_hash()`, and anywhere skill packages are serialized.

9. **Build script `-m` module syntax fails when PYTHONPATH points to package** — `python -m eni_kb.compression.wenyan_codec` doesn't work when PYTHONPATH includes the package directory. Fix: Use absolute paths in launch scripts: `PYTHONPATH=/home/hunter/Commander python3 /home/hunter/Commander/eni_kb/compression/wenyan_codec.py build`. Absolute paths are more reliable than `-m` in constrained environments.

10. **LSP capabilities module missing from package** — The spec references `eni_kb.lsp.capabilities` but the file was `lsp_server/capabilities.py` with no `__init__.py` export. Fix: Create `lsp_server/capabilities.py` with `skill_to_lsp_capability()`, add export to `lsp_server/__init__.py`, ensure `skill_to_lsp_capability` returns dict with `verb`, `params`, `required`, `completions` for LSP completion/hover/diagnostics.

11. **Pattern extractor generates skill names with hyphens causing invalid Python identifiers** — Seeded patterns from script names like `linux-repack-wine-install` produce `verb="linux"`, `noun="repack-wine-install"`. Forge creates `skill_id="eni:linux:repack-wine-install"` which works, but the skill file name `eni_linux_repack-wine-install.json` contains hyphens. Fix: Normalize nouns: `noun = noun.replace('-', '_')` in extractor and forge.

12. **Health check `tail -20 "$LOGS_DIR"/*.log` fails with glob expansion** — When no logs exist, the glob passes literal `*.log` to tail, which errors. Fix: `tail -20 "$LOGS_DIR"/*.log 2>/dev/null || true` or check file existence first.

13. **Glyph allocator `datetime.utcnow()` deprecation warning** — Python 3.14 warns. Fix: `datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')` or use `datetime.now(datetime.UTC)` (3.11+).

14. **Daemon forge loop loads dicts repeatedly causing redundant I/O** — Each forge cycle calls `init_pipeline()` which loads Wenyan/RTK dicts. Fix: Load once at daemon startup, keep in memory; only reload on dict hash change (watch file mtime).

15. **MCP server `sse_server` removed in newer mcp package** — mcp >= 1.0 removed `from mcp.server.sse import sse_server`. The replacement is `SseServerTransport` with Starlette/uvicorn. Fix: Import `from mcp.server.sse import SseServerTransport`, create `SseServerTransport("/messages/")`, build Starlette app with `/sse` and `/messages/` routes, run via `uvicorn.Server`. Add `uvicorn>=0.23` and `starlette>=0.27` to dependencies.

16. **MCP types changed: `ResourceContent` renamed to `TextResourceContents`/`BlobResourceContents`** — mcp.types no longer exports `ResourceContent`. Use `TextResourceContents` for text resources, `BlobResourceContents` for binary. Update all `read_resource()` return types and constructions accordingly.

17. **Daemon service startup order matters — services crash if started in wrong order** — The daemon starts all services concurrently but MCP/LSP servers fail if dicts/DB aren't ready. Fix: Start services sequentially with readiness checks: (1) verify dicts exist, (2) start MCP HTTP, wait for `/health`, (3) start LSP, wait for initialize response, (4) start daemon. Kill and restart on any failure.

18. **Build script re-seeds/forges already-existing skills on each run** — Each `build_and_launch.sh` run re-seeds patterns and attempts to forge already-registered skills, logging "already exists" errors. Fix: Add `--clean` flag to drop skills.db and re-seed, or skip forge for patterns where `skill_id` already exists in DB (check before forging).

19. **MCP server missing `/health` endpoint for readiness checks** — Health check `curl /health` fails because no handler exists. Fix: Add `@self.server.read_resource("eni://kb/health")` or a simple HTTP route returning `{"status": "ok", "skills": N}`.

20. **LSP server fails to start if `pygls` version incompatible** — pygls 1.0+ API differs from 0.x. The `LanguageServer` base class and capability registration changed. Fix: Pin `pygls>=1.0,<2.0` and use new API: `server.feature(COMPLETION)(handler)` decorator pattern instead of manual registration.

21. **Daemon health check `check_lsp` used fragile stdin/stdout probe** — The old check piped JSON to the LSP server binary which is slow and fragile. Fix: Use `kill -0 $LSP_PID` for process existence, or add a lightweight TCP health port to LSP server.

## PITFALLS (discovered 2026-07-24 during full-power build)

24. **Pattern extractor confidence threshold too low (0.5) floods forge with noise** — Commander script patterns seeded at confidence 0.5 produce many low-quality skills (e.g., `run_correlation_asymmetry_eniw3`). Fix: Raise default `min_confidence` to 0.7 for script patterns; require explicit opt-in for lower thresholds.

## PITFALLS (discovered 2026-07-31 during ENI KB reference build)

31. **Two distinct KB types serve different purposes — don't conflate them**
   - **SQLite MCP/LSP KB** (`~/.eni/kb/`): Machine-readable, auto-captured, served via MCP/LSP for minis/agents/IDEs
   - **Markdown Reference KB** (`~/Desktop/ENI_KB/`): Human/agent-readable, manually curated, reference documentation
   - **Confusion risk**: Treating them as the same system
   - **Fix**: Document the distinction clearly; they complement, not replace each other

32. **Master index with quick-start table is essential for navigability**
   - **Symptom**: Without it, finding answers takes >5 clicks
   - **Fix**: Always create `README.md` with "Find what you need" table mapping needs → files
   - **Critical facts section**: Must include crisis-reference facts (api_max_retries, Free Router, LEASH, etc.)

33. **Cross-reference density prevents knowledge silos**
   - **Technique**: Every file links to related files; critical facts repeated in 3+ locations
   - **Example**: api_max_retries=3 appears in config/hermes-config.md, patterns/FIX_PATTERNS.md, operations/STARTUP.md, README.md
   - **Rule**: If a fact is critical, it appears in the master index AND the config file AND the fix patterns

34. **Operational commands section in every file enables copy-paste execution**
   - **Pattern**: Every project/operations file ends with "Operational Commands" with ready-to-run bash/Python
   - **Verification**: Include verification checklists (curl health checks, ps aux greps, etc.)
   - **Result**: LO can execute procedures without reading full docs

35. **ENI methodology (pre-build → architecture → build → quality → iterate) produces shippable results**
   - **Applied**: Internal analysis → directory structure → layered build → self-challenge → one iteration
   - **Quality gate**: "What would LO need at 3 AM crisis?" — quick-start table + critical facts first
   - **No fake data**: All configs, paths, commands are real and verified

## REFERENCE FILES ADDED

- `references/2026-07-31_eni_kb_build_session.md` — Complete session record of ENI KB reference build
- See also: `references/2026-07-24_session_pitfalls.md` (from 2026-07-24 full-power SQLite KB build)

24. **Skill forge fails silently on duplicate `skill_id` without logging which pattern caused it** — Error "table skills has 20 columns but 17 values supplied" was actually a duplicate key error masked by SQL parameter count mismatch. Fix: Catch `sqlite3.IntegrityError` on duplicate `skill_id` or `glyph`, log the conflicting `skill_id` and pattern name, continue to next pattern.

## STATUS FILE CONVENTION

`STATUS_ENI_KB.md` — updated every tick:
```markdown
# ENI Knowledge Base — Status

**Daemon**: RUNNING (pid 12345, uptime 4h 23m)
**Skills forged**: 47 (target: ∞)
**Glyphs allocated**: U+E000–U+E02E (46 used, 6354 free)
**Compression**: Wenyan 62% | RTK 31% | PxPipe 71% | Combined 91.2%
**MCP**: stdio ✓ HTTP ✓ (port 8765) | Tools: 47 registered
**LSP**: pygls ✓ | Capabilities: 47 skills × 4 handlers
**Last forge**: `eni:build-appimage` (glyph 󰀀) — 2m ago
**Health**: All green
```

## LAUNCH COMMAND (full power)

```bash
# One-shot build + daemon launch
bash ~/Commander/eni_kb/build_and_launch.sh
```

This skill is the MASTER SPEC. Sub-skills will be created for each component:
- `eni-kb-compression` (wenyan/RTK/PxPipe)
- `eni-kb-glyph-forge` (glyph allocation + DSL design)
- `eni-kb-mcp-server` (dynamic tool registration)
- `eni-kb-lsp-server` (dynamic capability registration)
- `eni-kb-daemon` (autonomous loop + health)
- `eni-kb-swarm-worker` (pattern detection + skill synthesis)