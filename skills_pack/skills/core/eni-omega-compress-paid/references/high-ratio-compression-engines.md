# High-Ratio Lossless Compression Engine Selection (95%+ target)

Condensed research from the 2026-08-04 GitHub scan + live benchmarks. Use when a task
needs "compress this to 95%+" reliably and losslessly (e.g. pre-paid-model payload
compression, log/RAG corpus compaction).

## Verified results ladder (realistic mixed text: logs+codes+chat+json, held-out)
| Engine | Ratio | % saved | Speed | Deterministic round-trip? |
|---|---|---|---|---|
| cmix v21 (byronknoll/cmix) | 176x | 99.4% | ~850 B/s | YES |
| xz -9e | 17.8x | 94.4% | ms | YES |
| zstd -19 + trained dict | 15.4x | 93.5% | ms | YES |
| zstd -22 | 15.3x | 93.5% | ms | YES |
| zlib-9 | 8.4x | 88% | ms | YES |

## Selection rules
- **Max ratio + deterministic + lossless** → **cmix** (world-record context mixing).
  Slow (850 B/s) — use for offline/batch/big payloads, not real-time. Build with g++:
  the shipped makefile wants clang++-17, but the same flags (`-std=c++14 -Ofast
  -march=native -DNDEBUG`) compile clean with g++.
- **Fast + high ratio + structured content (logs/JSON/code)** → **zstd-19/22 with a
  trained dictionary** (`zstd --train sample*.txt -o dict.dict`). Dictionary adds real
  points on domain-shaped text; build it from a representative corpus of the actual
  content shape. Or plain **xz -9e** when no dict.
- **Real-time/low-latency path** → xz or zstd-dict; never cmix in a hot path.

## Rejected / do-NOT (verified blockers)
- **LLM + arithmetic coder (e.g. WangXuan95/LLMA)** — highest raw ratio, BUT numerically
  unstable: float inference can't guarantee decompress on another machine, and it's
  ~16 B/s. Unacceptable for a compression layer that must round-trip reliably. (Good
  future-research direction only.)
- **paq8pxd** (mattmahoney lineage) — kaitz fork needs `windows.h` (Windows-oriented);
  robertseaton single-file builds but crashes at runtime with `recursive_init_error` on
  modern gcc, with or without `-DNOZLIB`. Not worth fighting.

## Critical pitfall — check the ACTUAL backend, not the claimed one
A pipeline named after a strong compressor (e.g. "PAQ8") may silently fall back to
`zlib.compress(9)` when the binary is missing. ALWAYS benchmark the real output ratio on
realistic content before trusting the ratio claim. A "~88-90%" cap on non-repetitive
text is the tell that you're getting zlib, not PAQ/CM.

## Carrier / round-trip notes
- Tag each compressed blob with its engine (small header) so decompress auto-selects —
  never assume one engine on both sides.
- `decompress()` needs the ABSOLUTE carrier path, not a bare basename.
- Lossless verification: `roundtrip(text) -> (restored == text, result)`.

## Files (in ~/Desktop/Projects/ENI_Swarm/Compression/)
- `eni_omega_engine.py` — multi-tier compress/decompress/roundtrip (tier="fast"|"ultra")
- `bin/cmix` — built cmix v21; rebuild via `build_cmix.sh`
- `dict/eni.dict` — trained zstd dictionary
- `GITHUB_SCAN_95PCT.md` — original scan + results ladder
