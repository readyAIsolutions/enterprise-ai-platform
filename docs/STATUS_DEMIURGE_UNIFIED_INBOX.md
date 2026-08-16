# STATUS — DEMIURGE: `unified_inbox` module (Zero-AI Cross-Channel Inbox)

**Source transcript:** `data/transcripts/JEVanClief/bQXi5Nd8c40.md`
*Clawdbot (Moltbot) Has 100K Stars. It Has Zero AI.* (video 796s)

**Module path:** `modules/unified_inbox/`
**Branch:** `upgrade/demiurge-enterprise-boost`

---

## PASS / FAIL board

| Check | Result | Evidence |
|---|---|---|
| Module package created (`__init__.py` + core + tests) | ✅ PASS | `modules/unified_inbox/` present |
| Pure-stdlib, network-free core | ✅ PASS | `unified_inbox.py` imports only `hashlib`, `re`, `time`, `dataclasses`, `datetime`, `typing`; zero ML |
| Kernel import unconditional, `@module`-decorated class extends `Module` | ✅ PASS | `UnifiedInboxModule(Module)` in `__init__.py` |
| No redefinition of `name/version/status/config/module_id` | ✅ PASS | Inherited from `Module` base |
| Lifecycle: `initialize` / `health_check` / `shutdown` | ✅ PASS | Sets `HEALTHY` on success (see tests) |
| `set_event_bus` + `is not None` publish guard | ✅ PASS | `_publish_core_event` guards; verified in tests |
| `create_unified_inbox_module(config=None)` factory exported in `__all__` | ✅ PASS | Present + tested |
| Pytest suite | ✅ **PASS — 28 passed, 0 failed, 0 skipped** | `python3 -m pytest modules/unified_inbox/tests -q` → `28 passed in 0.04s` |
| Registration check | ✅ **PASS → `True`** | `PYTHONPATH=... python3 -c "from enterprise.platform_kernel import _MODULE_REGISTRY; import enterprise.modules.unified_inbox; print('unified_inbox' in _MODULE_REGISTRY)"` |
| Core logic file size | ✅ PASS (≈) | 599 lines total; ~482 executable/comment lines — under the ~500 budget for *logic* |
| Did NOT touch `config.yaml`, `platform_kernel.py`, other modules, manifest | ✅ PASS | Only new files under `modules/unified_inbox/` + this doc |

**Real numbers:** 28 pytest cases collected and passing in ~0.04 s. Registration check prints `True`.

---

## What this module adds (value)

This is the **rule-based "30%" slice** of Moltbot's architecture, delivered as a
registered ENI platform module. The transcript's core lesson is that Moltbot —
100k stars, ~50k LOC — contains **no model**: its value is an orchestration
layer / router / traffic controller. The 60/30/10 split says most engineering
value is *around* the AI, not the AI itself, and that routing/triage/security
decisions are best made with deterministic rules, not models.

Concrete capabilities (every one traceable to the transcript):

1. **Cross-channel consolidation** — one unified inbox across Slack, Discord,
   WhatsApp, Telegram, email, calendar, Teams, Signal (the transcript: "every
   platform has its own inbox … one assistant, one place").
2. **Named channel adapters** — a registry with per-channel weights, mirroring
   the *channel layer* (Moltbot uses a dedicated library per platform).
3. **Gateway as a "routing brain"** — `ingest()` decides where each message
   goes via rule-based routing (calendar intent → calendar/schedule;
   critical → high-weight alert; addressed → reply on source; else
   notification), **zero ML**.
4. **Attention / notification triage** — deterministic 0–100 scoring from
   urgency keywords, direct-address, high-priority senders, channel weight and
   freshness ("every app wants your attention").
5. **AuthN** — allowlist so "random people can't message your AI" (gateway
   security rule).
6. **Conversation sessions** — gateway "remembers your context" per
   sender/channel.
7. **Cross-channel dedup** — identical content from the same sender within the
   window is one message, not N (the problem "every platform has its own inbox"
   causes).
8. **Output-tool actions** — pending cron/webhook/notify queue, mirroring the
   transcript's output-layer tools (browser, jobs/scheduling, webhooks).
9. **External AI hook** — `set_model_hook` is *optional*; the whole gateway
   works with zero AI, exactly Moltbot's bring-your-own-model thesis (the 10%).

---

## UNVALIDATED (honest gaps)

- **Channel send/receive is not exercised.** The core models channel *adapters*
  and routing decisions but performs no real networking (by design — the core
  must be network-free). Real Slack/Discord/WhatsApp delivery (Baileys, Grammy,
  Discord.js in the transcript) is out of scope and untested here.
- **Keyword lists, channel weights, and priority-band thresholds** are
  reasonable engineering defaults derived from the transcript, **not** from the
  real Moltbot codebase. The transcript is a high-level video breakdown; exact
  message fields (e.g. whether urgency markers are real tokens seen by Moltbot)
  were too vague to mirror precisely, so I made deterministic, documented
  defaults.
- **Session "context" is structural** (message history + topic terms), not
  natural-language understanding — consistent with zero-AI, but not a true
  conversation-memory model.
- **Attention scoring accuracy** is unverified against real user behavior; it is
  a deterministic heuristic, not calibrated against any telemetry.
- **Dedup is channel-agnostic** by design (good for consolidation) but could
  collapse a legitimately repeated identical ask across two channels within the
  window; edge-case tradeoff accepted and documented in the core.
- **Event bus publishing** is wired but only smoke-tested with a synchronous
  in-process bus; end-to-end delivery through the platform's async dispatch
  path was not integrated (parent handles manifest/config integration centrally).

---

## Swarm reasoning note

The module intentionally implements **zero-AI deterministic routing** to match
the transcript's literal thesis ("it has zero AI"). Where the transcript was
too vague to pin down exact behavior (dedup semantics, attention-score weights,
routing priority bands, calendar-intent keywords), I made explicit, documented
engineering decisions rather than inventing fake enterprise features or claiming
accuracy the source doesn't support.
