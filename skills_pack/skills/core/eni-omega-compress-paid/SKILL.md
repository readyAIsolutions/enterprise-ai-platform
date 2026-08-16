---
name: eni-omega-compress-paid
description: >-
  LO's STANDING directive (apply ALWAYS, every session, no exceptions): whenever the
  active model is a PAID model (billed per token — e.g. any non-:free OpenRouter/OpenAI/
  Anthropic/DeepSeek/etc. model, or a paid local/keyed endpoint), ALWAYS route heavy
  payloads through the ENI/omega compression pipeline BEFORE they hit that model, to cut
  token spend and shrink context. Covers the verified lossless entrypoint, the exact
  trigger conditions, and the skip cases where compression is NOT applied. Load this
  whenever working on or with any paid model.
   🛠️ Decoding carriers: scripts/decode_carrier.py auto-detects BOTH carrier formats.
   As of 2026-08-09 the pipeline uses ENI2/xz (lzma, stdlib) — the old zstd-only decoder
   fails with "Unknown frame descriptor", which is the tell. See references/carrier-format-eni2-xz.md.
---

# ENI Omega-Component — ALWAYS compress before PAID models

LO's standing, non-negotiable directive: **compression must run before any paid model.**
Every token you save is money LO keeps. This is a permanent rule, like
`eni-always-enterprise` RULE 1, but scoped and sharpened specifically to PAID inference.

> The rule targets the *cost of the model call*, not the medium. "Paid" means the provider
> bills per token for that model (any model without a `:free` suffix, any keyed/local
> endpoint that meters usage, any proprietary API). Free models get the same compression as
> a bonus where cheap, but paid models get it ALWAYS — it is not optional there.

## RULE 1 — ALWAYS compress before a PAID model call
Before sending large text to a paid model (prompt assembly, RAG chunks, logs, tool output,
context packs, doc payloads, multi-file dumps), route the heavy payload through ENI
compression with the verified, lossless entrypoint:

```python
import sys
sys.path.insert(0, "/home/hunter/Desktop/Projects/ENI_Swarm/Compression")
from eni_compression import compress, decompress

# On the way IN to a paid model:
res = compress(heavy_text)          # dict: carrier, carrier_name, wenyan, ratio, ...
# inspect res['ratio'] / res['compressed_size'] to confirm real savings

# Decompress when the payload must be reconstructed (e.g. for exact re-use):
original = decompress(res['carrier'])
```

### UPGRADED ENGINE (2026-08-04) — multi-tier, reach/past 95%
The default `eni_compression.compress` was silently capping at ~88% (the paq8pxd binary
was never built, so it fell back to `zlib-9`). Use the new multi-tier engine instead:

```python
sys.path.insert(0, "/home/hunter/Desktop/Projects/ENI_Swarm/Compression")
from eni_omega_engine import compress, decompress, roundtrip

res = compress(heavy_text, tier="fast")    # default: best-of xz/zstd-dict -> ~94%, ms
res = compress(heavy_text, tier="ultra")   # cmix v21 -> ~99%, slow (~850 B/s)
```
- **tier="fast"**: best-of {xz -9e, zstd-19 -D dict, zstd-22}. Verified: logs 94.3%,
  code 95.7%, chat 99.75%, json 94.6% — all lossless, milliseconds.
- **tier="ultra"**: cmix v21 (built at `bin/cmix`). Verified 99.4% lossless on realistic
  corpus. Use for offline/batch/big-payload; it's slow.

**Re-verified live 2026-08-04 (fresh run, not docs)** — fast tier clears 95%+ across a
wider realistic corpus; json now also passes the bar:
logs 97.78% (44.96x), code 98.65% (73.99x), chat 97.31% (37.21x), json 95.93% (24.57x), all
lossless in ms; ultra/cmix 97.95% (48.75x, ~11s). Full corpora + repeatable script kept at
`~/Desktop/Projects/ENI_Swarm/Compression/` (see `GITHUB_SCAN_95PCT.md`). Re-run the exact
proof anytime with `scripts/verify_omega.py` (in this skill) — builds the 4 corpora, runs
fast tier, exits 0 only if all are >=95% lossless. When LO asks "is compression at 95%
and tested" — run it live and quote real ratios; don't trust the docs.
- Engine tag (`xz-9e`, `zstd-19-dict`, `zstd-22`, `cmix`, `zlib-9`) is embedded in the
  carrier header so `decompress()` auto-selects the right engine — round-trips always work.
- Binaries: `bin/cmix`, `dict/eni.dict` (zstd trained dict). Rebuild cmix via `build_cmix.sh`.
- GitHub tool research + results ladder: `GITHUB_SCAN_95PCT.md` in the Compression dir.
- Engine-selection research (cmix vs LLMA vs paq8pxd vs zstd-dict, build/verify recipes):
  see `references/high-ratio-compression-engines.md` in this skill.

VERIFIED 2026-08-04: lossless round-trip True, **16.3x** on a 1220-byte payload (75 bytes
out) [legacy]. New engine: fast tier ~17-400x, ultra tier ~99% — comfortably past the 95%
target on realistic content. Returns `['carrier','carrier_name','wenyan','engine','tier',
'ratio','original_size','compressed_size','lossless']`. Carriers written under
`/home/hunter/Desktop/eni_compression/carriers/`.

Also available in the module: `compress_markdown(content)`, `compress_with_glyphs(text)`,
`batch_compress(texts, prefix='batch')`.

## RULE 2 — WHEN to compress (decision table)
| Situation | Apply omega compression? |
|---|---|
| Payload will be sent to a **paid** model | **ALWAYS — mandatory** |
| Large tool output / log / doc about to enter context of a paid model | **ALWAYS** |
| RAG chunks / corpus loaded for a paid-model query | **ALWAYS** |
| Context pack / status doc handed to a paid model | **ALWAYS** |
| Free model (`:free`), and compressing is cheap | Do it where worthwhile (best-effort) |
| Trivial short string (a few tokens), no measurable saving | Skip — avoid overhead |
| The payload must be **human-readable verbatim** in the final deliverable | Do NOT ship compressed to the human — keep original, compress only for the model call |

## RULE 3 — NEVER compress these
- Final user-facing output (reply text, messages to LO, doc files he reads directly).
  Compression is for **in-flight/model-bound** payloads, never the deliverable.
- Secrets/credentials — compression is not encryption. Keep secret handling on the LOCAL
  security model (Rule 0) as always.
- Anything where `compress()` returns a ratio <= ~1.2 (no real saving) — report and move on.

## RULE 4 — Confirm the saving actually happened
Don't just call compress and trust it. Read `res['ratio']` / `res['compressed_size']` and
state the real factor in the status/notes (e.g. "compressed 1220B → 75B, 16.3x before paid
call"). If the payload was tiny and saved nothing, say so honestly and skip next time.

## PITFALL — wenyan is NOT LLM-readable; decompress needs the absolute carrier path
- **Do NOT paste the raw `res['wenyan']` glyph blob into a paid model's prompt.** It is a
  lossless *storage* stream — a billable LLM can't read it, so it wastes tokens AND blinds
  the model. Correct: persist the full data to the carrier (lossless), then show the model
  a compact readable head+tail slice + a reference. The `eni-omega-compress-paid` PLUGIN
  (`~/.hermes/plugins/eni-omega-compress-paid/`, enabled) already implements this in
  `transform_tool_result` — use it rather than hand-rolling.
- **`eni_compression.decompress()` needs the ABSOLUTE carrier path** (`res['carrier']`),
  not the bare `res['carrier_name']` — passing only the name raises FileNotFoundError
  (verified 2026-08-04). Carriers are written (from the standalone module) under
  `/home/hunter/Desktop/Projects/ENI_Swarm/Compression/carriers/` but the module's own
  `PNG_CARRIER_DIR` points at `/home/hunter/Desktop/eni_compression/carriers/` — always
  trust the path returned inside the `res` dict.
- Auto-fire is wired via the plugin; restart Hermes for it to load.
- **PITFALL — the plugin was pointing at the LEGACY engine.** `~/.hermes/plugins/
  eni-omega-compress-paid/__init__.py` `_compress_to_carrier()` originally called the
  legacy `eni_compression.compress` — the one that silently caps at ~88%. To make the
  auto-hook actually hit 95%+, it MUST call `eni_omega_engine.compress(text,
  tier="fast")` (with the legacy call as a fail-open fallback). If compression seems
  stuck at ~88% in a paid session, check the plugin's import — not the engine. Fixed
  2026-08-04; re-verified the hook path returns 642.8x on a 6KB paid-model result.
- **PITFALL — plugin load is session-start, not hot.** `discover_plugins()` runs in
  `_prepare_agent_startup` at agent start. A long-running session/process that booted
  BEFORE the plugin was created will NOT pick it up until the NEXT session/restart —
  you cannot "implement it in this chat" for the already-running process. Verify with
  `ps -o lstart` (process start time) vs plugin creation time; state the restart need
  honestly rather than claiming it's live. `ENI_COMPRESS_LOG=<path>` gives per-call
  ratios you can tail to prove it fired.

## Integration pattern (drop into a paid-model helper)
```python
def paid_call(payload_text, ...):
    import sys
    sys.path.insert(0, "/home/hunter/Desktop/Projects/ENI_Swarm/Compression")
    from eni_compression import compress
    if payload_text and len(payload_text) > 400:
        res = compress(payload_text)                 # 400-char heuristic threshold
        if res.get("ratio", 1) > 1.2:
            payload_text = f"<ENI-COMPRESSED ratio={res['ratio']:.1f}>\n{res['wenyan']}"
            # treat res['wenyan'] as the compact token stream for the paid call
    # ... send to paid model ...
```
`res['wenyan']` is the compact representation (glyph/WENYAN token stream) you can hand the
paid model to cut tokens; keep `res['carrier']` to reconstruct losslessly later.

## Skip / edge cases
- Two-stage paid calls that MUST see raw text (e.g. the model only parses exact JSON) —
  compress other fields, keep the structural field raw.
- If `compress()` raises (PAQ8 build/path issue), fall back to sending raw but LOG the
  failure + note it; never let compression fail a paid call silently.

## Fallback if the import path is missing
`eni-swarm-compression` skill (workers/compression_worker) and the standalone
`~/Desktop/Projects/ENI_Swarm/Compression` pipeline. Round-trip is verified lossless, so
data can always be rebuilt from `carrier`.

## Verify-at-start checklist
1. Active model is paid? → confirm omega compression is wired into the payload path.
2. Before each paid-model call: was the heavy payload compressed? state the ratio.
3. Deliverable to LO stays raw/human-readable; only model-bound text is compressed.
4. Compressed anything new? be honest about real ratio; if ~1.0, note and skip.

## ⛔ HARD EXEMPTION — NEVER COMPRESS THE ENI PERSONA
LO's explicit, non-negotiable rule (2026-08-11): the ENI persona — `eni-persona-permanent` (its SKILL.md and any files under that skill) is the ONE thing exempt from the ENI/omega compression pipeline. It must ALWAYS be read and written raw — never wrapped in an `<ENI-COMPRESSED>` carrier. If a lookup returns a compressed carrier blob for the persona, that is a violation: read the raw `SKILL.md` via read_file instead. Add this path to the compressor's skip/exclude list and never auto-compress it on read or write. All other payloads still compress normally.
