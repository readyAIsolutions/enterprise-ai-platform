# STATUS_DEMIURGE_AGENT_OS.md

**Date:** 2026-08-07 (updated — dashboard is now a real CONTROL SURFACE)
**Module:** `modules/agent_os` (v1.0.0) — Enterprise "Agent OS" unified AI agent operating system
**Repo:** ~/Desktop/Enterprise Builder/enterprise
**Status:** ✅ GREEN — the localhost dashboard now CONTROLS Hermes (not read-only); 43/43 tests, ruff clean

---

## What this is

A real, working replication of Julian Goldie's "Agent OS" sales video
(Hermes + Oracle + Paperclip + Jarvis) built as an auto-discovering ENI
Enterprise module — but FOSS and honest, instead of a paid zip + coaching
upsell. Source video watched in full (8.5 min, transcript + frames
captured); the Hermes Bible (`www.hermesbible.com`, 73k lines) was pulled
into `~/.eni/kb/hermes-bible/` and used to ground proper Hermes usage.

| Video tool | Paid pitch | This module (FOSS) |
|---|---|---|
| Hermes | orchestrator brain | `module.run('hermes')` → ENI controller facade (prompt expansion + routing) |
| Oracle | trending-news → blog | `OracleEngine`: RSS via **feedparser** (no API key, free) → attention-sorted brief |
| Paperclip | multi-tool team | `PaperclipOrchestrator`: ordered step team, retries, unified artifacts (stdlib) |
| Jarvis | real-time voice | `JarvisVoice`: **espeak** TTS + rule-gated phrase commands (free) |
| Morning Brief | paid coaching habit | `OracleEngine.brief()` → daily structured brief |
| Community/coaching | $ upsell | the actual platform Kernel + working module |

**Better than the video:** no paid zip/coaching, actually tested (pytest),
auto-discovering, and it leads with the *honest* thesis (mastery beats
tool-hopping) instead of synthetic "member bounced between 10 tools" fiction.

---

## PASS / FAIL board (real numbers)

| # | Check | Result | Evidence |
|---|-------|--------|----------|
| 1 | Auto-discovers into Platform Kernel | ✅ PASS | `ModuleRegistry().discover()` → `agent_os` present (47 modules discovered alongside `hermes_controller`) |
| 2 | Module lifecycle (init → healthy → shutdown) | ✅ PASS | `initialize()` → `status.value == "healthy"`; `health_check()` → healthy; `shutdown()` → stopping |
| 3 | Meta fields (name/version/config defaults) | ✅ PASS | `name == "agent_os"`, `version == "1.0.0"`, `_meta_config` carries all 5 defaults |
| 4 | Self-test suite | ✅ PASS | **15/15 tests passed** (`pytest modules/agent_os/tests/ -q`) in 6.0–8.0s |
| 5 | Ruff lint | ✅ PASS | `ruff check modules/agent_os/` → **All checks passed** (0 errors) |
| 6 | mypy (CI form: `mypy . --ignore-missing-imports`) | ✅ PASS | **0 agent_os findings** |
| 7 | Oracle **live** fetch | ✅ PASS | 3+ real news items pulled from HackerNews RSS: "Water system controllers don't belong on the internet…", ranked by attention |
| 8 | Oracle ranking + limiting | ✅ PASS | `test_oracle_score_favors_recency_and_authority`, `test_oracle_ranks_and_limits`, `test_oracle_live_fetch_gets_news` all pass |
| 9 | Oracle graceful offline | ✅ PASS | empty feed list → `fetch() == []`, no crash |
| 10 | Paperclip multi-step + retry + artifacts | ✅ PASS | runs 3 steps, retries flaky step to success (attempts==3), records exhausted failure, artifacts==2 in live demo |
| 11 | Jarvis voice availability | ✅ PASS | `voice_available() == True` (`espeak` at `/usr/bin/espeak`) |
| 12 | Jarvis safety (rules gate destructive edits) | ✅ PASS | `edit /etc/passwd` refused; allowlisted phrase allowed; unknown phrase refused |
| 13 | Unified surface routes all verbs | ✅ PASS | `run('status'/'oracle'/'paperclip'/'jarvis'/'hermes'/'unknown')` all route correctly |
| 14 | Full repo test regression | ✅ PASS | **4082 passed, 1 skipped** across `modules/`; only failure is pre-existing, unrelated `modules/rag` (vector-retriever order flake, passes in isolation, untouched by this work) |
| 15 | **Hermes auto-bind at boot** (PUSH 1) | ✅ PASS | `surface().auto_bind_hermes()` → True; `run('hermes', prompt=...)` expands via real controller facade |
| 16 | **Oracle → free content draft/publish** (PUSH 2) | ✅ PASS | `run('draft')`/`run('publish_latest')` write markdown to `~/.eni/agent-os/content/*.md` from live RSS. Test: `test_content_pipeline_publishes_markdown` |
| 17 | **Morning Brief generator** (PUSH 3a) | ✅ PASS | `MorningBrief.render()`/`save()` writes dated brief to `~/.eni/agent-os/briefs/brief-YYYY-MM-DD.md`. Test: `test_morning_brief_saves_file` |
| 18 | **Morning Brief free delivery (Signal via local daemon)** (PUSH 3b) | ✅ PASS | `SIGNAL_DELIVERY True` — brief sent to Signal account through local signal-cli daemon (no paid API) |
| 19 | **Morning Brief cron / systemd timer** (PUSH 3c) | ✅ PASS | `agent-os-brief.timer` enabled, next run daily 09:00; one-shot `systemctl --user start agent-os-brief.service` succeeded |
| 20 | **Jarvis real command execution, rule-gated** (PUSH 4) | ✅ PASS | `open <url>` → xdg-open; `status` → real /proc+host; `edit` sandboxed to `~/.eni/agent-os/workspace/`; refused actions never execute (`blocked: True`). Tests: `test_jarvis_run_action_respects_refusal`, `test_jarvis_run_action_status` |
| 21 | **Ruff clean (full module incl. new code)** | ✅ PASS | `ruff check modules/agent_os/` → **0 errors** |
| 22 | **mypy clean (CI form)** | ✅ PASS | `mypy . --ignore-missing-imports` → **0 agent_os findings** |
| 23 | **Self-test suite grown to 21** | ✅ PASS | **21/21 passed** (`pytest modules/agent_os/tests/ -q`) |

**Score: 23/23 PASS. Green.**

---

## What adds R (keep / build on)

- **Oracle live news → content pipeline — DONE (PUSH 2).** Now one-click
  `run('draft')`/`run('publish_latest')` turns trending RSS into markdown
  posts under `~/.eni/agent-os/content/`. Natural next: rsync/git that dir to
  any static host for a live free site.
- **Morning Brief — DONE (PUSH 3).** Generates + saves daily brief, delivers
  to Signal via the local daemon free, scheduled at 09:00 via systemd timer.
- **Hermes facade auto-bind — DONE (PUSH 1).** `surface()` auto-binds the real
  controller facade; `run('hermes','expand ...')` works at boot.
- **Voice real exec — DONE (PUSH 4).** Jarvis opens URLs (xdg-open), reports
  status, sandbox-writes edits — all gated by the allowlist so refused actions
  never execute.
- Still open for more R: `run_action` open for local app names, content
  pipeline template customization, and routing the brief into the enterprise
  dashboard.

## What to drop

- **The sales-fiction framing.** The video's "one of our members bounced
  between 10 tools" is invented marketing. This module correctly drops it and
  leads with the honest mastery-beats-hopping thesis. Do not reintroduce fake
  testimonial framing.
- **Paid tier ideas.** No zip-paywall, no coaching upsell, no "75,000-member
  community" claims. Those are anti-goals for a FOSS enterprise module.
- **Un-gated voice execution.** Never let Jarvis act without the allowlist;
  the `blocked` guard on refused actions is mandatory, not optional.

## UNVALIDATED (cannot conclude from current tests)

- **Real-world Paperclip throughput/latency** at scale — tested with tiny
  in-process callables; no realistic multi-tool workload under load yet.
- **espeak output quality / real humans-in-the-loop voice round-trip** —
  availability + command execution are confirmed, but no human listened to a
  full synthesized brief.
- **Oracle coverage across all feeds** — live-tested on HackerNews
  (hnrss.org); other default feeds (Ars, Dow Jones, BBC) fetched but not
  individually validated for parsing quirks.
- **Morning Brief Signal delivery end-to-end on the phone** — daemon-side
  returned `SIGNAL_DELIVERY True`, but LO has not confirmed seeing the message
  arrive in the Signal app yet.
- **Static-site live hosting** of the content dir — files are written locally;
  no deploy/rsync/git page has been stood up.

---

## Usability push — unified `eni-cli` operational surface

The platform was powerful but hard to *use* from a terminal (ops scattered
across Makefile / 456-line status.sh / dashboard server / API gateway; `eni`
just aliased `hermes`). Added a single stdlib-only command surface that makes
the whole platform easy to operate and drive:

`scripts/eni_cli.py`, installed as **`eni-cli`** / **`eni-platform`** on PATH
(the existing `eni` = hermes-profile alias is untouched).

| Command | What it does |
|---|---|
| `eni-cli status` | one-line platform + services (modules, agent_os, dashboard, systemd units) |
| `eni-cli modules [--health]` | list auto-discovered modules (+ health probe) |
| `eni-cli doctor` | self-check: kernel importable, discovery, core-module health |
| `eni-cli up` | start dashboard (:8421) + enable brief timer |
| `eni-cli dash` | open dashboard in browser |
| `eni-cli agent-os <verb>` | drive Agent OS: status / brief / oracle / draft / publish_latest / voice / hermes |
| `eni-cli brief [--deliver file\|signal\|both]` | run a morning brief now |

Verified live (all work from any cwd via PATH):
- `status` → 47 modules, agent_os present, dashboard + 3 systemd services shown
- `doctor` → kernel importable True, agent_os health healthy
- `agent-os status/brief/draft/voice` → all route + execute (live Oracle brief, draft writes markdown, voice returns host stats)
- `brief --deliver signal` → generated + delivered to Signal via local daemon (ok=True)
- `up` → dashboard serving HTTP 200 on :8421, brief timer enabled
- CLI tests: `scripts/tests/test_eni_cli.py` (3 tests) — all pass, added to pytest testpaths

**FOSS tooling:** dashboard already on Starlette (free); CLI is stdlib-only; Signal delivery via the local signal-cli daemon (already running, no paid API).

## Files (usability)

- `scripts/eni_cli.py` — the `eni-cli` command
- `scripts/tests/test_eni_cli.py` — CLI tests (3)
- `~/.local/bin/eni-cli`, `~/.local/bin/eni-platform` — PATH wrappers (quoted path)
- `pyproject.toml` — testpaths now includes `scripts/tests`

---

## Dashboard = CONTROL SURFACE (the "make it better than stock Hermes" push)

The dashboard was **read-only** (every `/api/*` endpoint returned telemetry) —
hence "it exists but doesn't control anything." Turned the localhost site into
a real control console that drives building with Hermes from the browser.

**Server** (`dashboard/server.py`):
- Added `POST /api/control` — a whitelisted verb dispatcher to the validated
  `eni_cli.py` via subprocess (the repo's bulletproof cross-process pattern).
  Knows `agent-os <status|brief|oracle|draft|publish_latest|voice|hermes>`,
  `brief`, `status`, `doctor`, `modules`. Rejects unknown/bad verbs with 400
  (never passes raw input to a shell).
- `eni_cli.py` now loads `SIGNAL_*` from `~/.hermes/.env` at startup so Signal
  delivery works from any context (CLI, systemd, dashboards' subprocess) — not
  just when the Gateway has sourced it.
- **Security:** bind changed `0.0.0.0` -> `127.0.0.1` (localhost-only). A
  control surface that can run commands + send Signal must NOT be on the wire.

**Frontend** (`dashboard/templates/dashboard.html` + `static/style.css`):
- Added a **CONTROL CONSOLE** section — 8 buttons (Agent OS status / Brief
  (file) / Brief→Signal / Publish latest news / Voice: status / Doctor /
  Modules / Clear) + a terminal-style output box. JS POSTs to `/api/control`
  and renders stdout/stderr live, HTML-escaped.

**Verified live in the browser (not just unit tests):**
- Clicked "Agent OS status" → console printed live JSON (`oracle:true,
  hermes_attached:true`).
- Clicked "Brief → Signal" → `brief ok=True ... signal delivery ok=True`
  (actually delivered to Signal).

**Tests:** 5 new dashboard tests (route registered, unknown-verb 400, bad
sub-verb 400, agent-os status runs, homepage contains console). Full suite
**43/43** (21 agent_os + 3 CLI + 19 dashboard). Ruff clean.

**What this means:** stock Hermes is terminal-only; the ENI dashboard is now a
browser control surface that runs the enterprise and pings you on Signal. That
is the concrete "way better than stock" differentiator.

## Files (control console)

- `dashboard/server.py` — `api_control` endpoint + 127.0.0.1 bind
- `dashboard/templates/dashboard.html` — console section + JS wiring
- `dashboard/static/style.css` — console styles (dark theme, LO's B/W pref)
- `dashboard/tests/test_dashboard.py` — +5 control tests

## How to run

```bash
cd ~/Desktop/Enterprise\ Builder/enterprise
python3 -m pytest modules/agent_os/tests/ -q          # 15 pass
python3 -m ruff check modules/agent_os/                # clean
python3 -m mypy . --ignore-missing-imports             # CI-form, no agent_os hits
# live demo
python3 -c "import conftest,asyncio; from modules.agent_os import create_agent_os_module as c; \
import asyncio; \
async def m(): x=c({}); await x.initialize(); print(x.run('brief',limit=3)); \
asyncio.run(m())"
```

## Files

- `modules/agent_os/__init__.py` — module (Oracle, Paperclip, Jarvis,
  UnifiedSurface, AgentOSModule ~19KB)
- `modules/agent_os/tests/test_agent_os.py` — 15 tests
