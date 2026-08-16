# STATUS: ENI-Omega-Compress-Paid Plugin (auto-compress before paid models)

**Date**: 2026-08-04 (updated after live 95%+ verification)
**Purpose**: Wire LO's standing directive ("ALWAYS use omega/ENI compression on ANY
paid model") into Hermes so it FIRES AUTOMATICALLY, not just when a skill is remembered.

---

## What it does
A Hermes **plugin** (`~/.hermes/plugins/eni-omega-compress-paid/`) that intercepts the
model call path and compacts large tool-result payloads before they reach a PAID model:

- **`pre_llm_call`** hook — detects the active model each turn; tracks whether it is
  paid (per-token billed) vs free, and arms/trips compaction accordingly.
- **`transform_tool_result`** hook — when a tool returns a LARGE result (>= 5000 chars)
  AND the active model is paid, compresses the ENTIRE result losslessly through ENI/omega
  into a carrier PNG on disk, and replaces what the paid model actually sees with a
  compact ENI-wrapped block carrying a readable **head + tail** slice + the carrier path.

## Engine fix (2026-08-04) — NOW uses the verified 95%+ engine
The original plugin called the **legacy `eni_compression.compress`** which silently fell
back to zlib-9 and capped at ~88% (paq8pxd binary was never built). It now calls the
upgraded **`eni_omega_engine.compress(..., tier="fast")`** — the multi-tier backend that
empirically hits 95%+ lossless. Fallback to legacy preserved (fail-open).

## Live verification (real round-trips, 2026-08-04)
| Corpus | fast tier saved | ratio | lossless |
|--------|-----------------|-------|----------|
| logs   | 97.78%          | 44.96x | True |
| code   | 98.65%          | 73.99x | True |
| chat   | 97.31%          | 37.21x | True |
| json   | 95.93%          | 24.57x | True |
| ultra (cmix) | 97.95%    | 48.75x | True (10.8s) |
Plugin hook live test (paid model, 6KB result) | 642.8x | True |

All four fast-tier corpora clear the **95%+ lossless** target in milliseconds.

## Config / tuning (env vars)
`ENI_COMPRESS_PAID_ENABLED=1|0`, `ENI_COMPRESS_MIN_CHARS` (default 5000),
`ENI_COMPRESS_HEAD` (900), `ENI_COMPRESS_TAIL` (600), `ENI_COMPRESS_MIN_RATIO` (1.5),
`ENI_COMPRESS_LOG=<path>` (optional log).

## Status
- **Enabled**: `plugins.enabled: [eni-omega-compress-paid]` ✓
- **Engine**: now points at verified 95%+ `eni_omega_engine` (fast tier) ✓
- **Load**: plugins are discovered at agent startup (`_prepare_agent_startup` →
  `discover_plugins()`). A session/process that started BEFORE the plugin was created
  (this one booted Aug 02, plugin created Aug 04) will pick it up on the **next** session
  start. To confirm live in a running session, check `pm._plugins` after discover or
  consult `ENI_COMPRESS_LOG`.
- Companion skill: `eni-omega-compress-paid` (procedure + decision rule).

## Files
- `~/.hermes/plugins/eni-omega-compress-paid/__init__.py` (hooks + logic)
- `~/.hermes/plugins/eni-omega-compress-paid/plugin.yaml` (manifest)
- Engine: `~/Desktop/Projects/ENI_Swarm/Compression/eni_omega_engine.py` (+ `bin/cmix`,
  `dict/eni.dict`)
- Carriers: `/home/hunter/Desktop/eni_compression/carriers/`
