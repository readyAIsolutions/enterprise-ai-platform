# STATUS — Paper Feeds Module v2.0 (REBUILT)
Date: 2026-08-16  |  Module: `modules/paper_feeds`  |  Target: daily research digest

## Rebuild intent
Original v1 was a bare title-scraper (regex over HTML). v2.0 is a structured
research-intel engine — rebuilt *better*, not just bumped.

## What changed (v1 -> v2.0)
- Structured `Paper` dataclass (id, title, abstract, authors, url, source,
  published, tags, relevance) instead of bare title strings.
- Primary ingestion via the **arXiv Atom API** (ElementTree), robust parse;
  HTML regex kept only as offline fallback.
- **Change detection**: persisted `index.json` of seen ids; daily digests mark
  & separate *new* papers so client docs only surface fresh research.
- **Relevance tagging** into enterprise buckets (agents, multiplayer, rag,
  finetune, local, security, video, robotics, eval, embed).
- **Machine-readable export**: markdown digest + JSON + CSV per feed.
- WiFi-safe: per-feed pacing, timeout + retry/backoff, no video floods.

## PASS / FAIL board (real evidence)
| Check | Result | Evidence |
|-------|--------|----------|
| Unit tests (network-free)      | **PASS** | `pytest modules/paper_feeds/tests` → 9 passed, 0 failed |
| Regex-free Atom parser         | **PASS** | 40 real papers parsed, titled, authored, abstracted |
| Live end-to-end arXiv pull     | **PASS** | 1st run got=40 new=40 (all fetched via Atom API) |
| Change detection / dedup       | **PASS** | 2nd run got=40 **new=0**, index count=40 |
| Machine-readable JSON+CSV      | **PASS** | `arxiv.json`/`arxiv.csv` written & validated in tests |
| Relevance tagging              | **PASS** | e.g. Marionette → [agents, rag, video, robotics] |
| Platform registration          | **PASS** | `paper_feeds in _MODULE_REGISTRY` = True |
| Sibling modules unbroken       | **PASS** | context_routing + shared_workspace = 12 passed |
| Daily cron scheduled           | **PASS** | job 0f77f7774fd7, daily 06:00, runner verified standalone |
| HF / PwC / AlphaXiv live feeds | **FAIL** | 0 papers (bot-blocked non-browser UA; best-effort) |

## What adds R / what to drop
- **Adds R:** arXiv structured research (the real value) + dedup + tagging +
  machine-readable export = directly citable, queryable research intel for
  client docs and downstream modules (context_routing).
- **Keep:** Atom API primary path; fallback HTML; JSON/CSV export.
- **Drop (or fix later):** HF/PwC/AlphaXiv live fetch currently yields 0 due to
  bot protection — keep as best-effort, do NOT block the digest on it.

## UNVALIDATED
- Whether HF / PwC / AlphaXiv can be fetched at all from this network (Cloudflare
  / JS-render); would need a real browser UA + JS render to conclude.
- Real cron delivery formatting in the chat channel (job runs tomorrow 06:00).
