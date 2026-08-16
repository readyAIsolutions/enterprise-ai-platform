# ENI Iterative AI-Upgrade Series (site feature playbook)

The user drives this site through an explicit **ENI upgrade loop**: repeated near-identical
prompts — "how would an AI upgrade this? anything you implement must be fully flushed out,
100% complete and tested before starting the next" — that keep coming until told to stop.
Each push is a request to think like an AI about the highest-leverage next feature and build
it whole. Do NOT stop after one feature; keep going across pushes, and end each round by
listing 2-3 concrete next candidates so the user can pick or say "next".

## The recurring AI-feature template (used 9x)
Every feature in this series followed the same shape:
1. **db.py** — add an idempotent migration + a pure aggregation/derivation helper
   (e.g. `dashboard_stats()`, `fan_engagement()`, `followups_due()`, `releases_missing_lossless()`).
2. **aiwriter.py** — add a generator that returns structured/persona copy, with a
   **deterministic fallback** so the button ALWAYS returns usable output when the AI is down
   or returns junk (never crashes, never fabricates facts). Fallback must produce a full
   sentence even when source data is thin (test for min length, not just truthiness).
3. **server.py** — an **auth-gated, read-only-or-dry-run route** returning JSON
   (`_need_admin` → 401 or RedirectResponse; unknown id → 404). Prefer JSON for admin JS.
4. **admin.html + app.js** — a button pattern: `data-<feature>` on the button + a
   `data-<feature>-msg` span; JS fetches, renders result inline, disables button while busy.
5. **tests** — at minimum: AI-down fallback, AI-output parse, route auth (401), route admin
   + data shape. Run suite 2-3× to confirm stable.
6. Bump `app.js?v=` (and `style.css?v=` if CSS changed) cache-buster in `base.html`.
7. `node --check static/app.js` + `python3 -c "import ast; ast.parse(...)"` before restarting.
8. Append a dated section to `STATUS_ACPE$0.md`, restart the server, verify live.

## Features built this series (for feature-set recall)
- Command Center dashboard (default `/admin#dashboard` tab): KPIs, curator pitch funnel,
  follow-up queue, release-readiness (missing-lossless = broken downloads), top downloads.
- Owner's Daily Briefing: `briefing.py` + cron `acpeso-daily-briefing` at 08:00 → emails the
  owner a `dashboard_stats()` digest; `/admin/briefing-preview`, `/admin/briefing-send`.
- AI-personalized per-curator pitches: `aiwriter.personalize_pitch` (unique email per curator
  referencing their focus/platform), `/admin/ai-personalize`, `personalized=1` send flag.
- AI Release Press Kit: `aiwriter.press_kit` (editorial blurb + 3 highlights), public
  `/press/{slug}` one-sheet (print friendly), `/admin/ai-presskit`.
- AI Follow-up nudge: `aiwriter.follow_up_nudge` for the stalled-curator queue,
  `/admin/ai-followups` (only reachable curators: email OR contact_url).
- Community CRM / fan leaderboard: `db.fan_engagement()` + `/admin#community` tab +
  `aiwriter.fan_note` reward note per fan, `/admin/ai-fan-note`.
- Comment deletion (owner + admin): `POST /api/item-comment/delete` permission model.

## Parsing-AI-output pitfalls (bit MULTIPLE times — always handle)
- Models often emit **literal `\n` (backslash-n) sequences** instead of real newlines, or
  duplicate/escape them. BEFORE splitting AI subject/body or JSON, normalize:
  `text = text.replace("\\r\\n","\n").replace("\\n","\n").replace("\r\n","\n").replace("\r","\n")`.
  Then split `SUBJECT:` line on real newlines. This was a live bug in `personalize_pitch`
  (a curator email got mangled) — the parser fix is required, not optional.
- Reasoning models leak chain-of-thought into `content`; use the `<<<...>>>` marker protocol
  (`_chat` for marker extraction) or `_chat_raw` + `_strip_reasoning` + parse for structured
  output. If output can't be parsed → fall back to the deterministic template, don't crash.
- Ask the model to "use REAL line breaks, never the two-character backslash-n" in the prompt.

## Starlette sync-TestClient pitfall (recap + reinforce)
Opening a second `TestClient` on the SAME session-scoped `app` obj can raise a
`concurrent.futures.CancelledError` at `portal.call(self.wait_startup)` — deterministic
in-suite, passes standalone/in-repro. FIX: fold multiple route assertions into ONE
TestClient `with` block per test; don't spawn per-assertion clients.

## Permission-path tests in MOCK mode
Mock `/connect?mode=login` and `mode=admin` BOTH create the **admin** fan (`acpeso`
username), so "owner" vs "admin" branches are indistinguishable via connect. To test a
**non-admin owner** path, set the fan cookie directly:
`c.cookies.set("acpeso_fan", <non-admin fan id>)` (fan id is the STRING returned by
`db.upsert_fan`, not a dict), then assert the route resolves the branch from that cookie.
`db.upsert_fan` returns the fan id string.
