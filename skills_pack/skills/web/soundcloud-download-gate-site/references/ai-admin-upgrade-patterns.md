# AI / Admin Upgrades — durable patterns (AC PE$0 class)

## 1. AI-router output parsing: normalize escaped newlines BEFORE splitting
The local free-router (`aiwriter._chat_raw`) is a reasoning model that often
returns literal two-char `\n` (backslash-n) sequences instead of real newlines,
especially when the prompt itself used `\n\n`. If you try to split a structured
reply on `\n` you get one giant line and the parse fails.

FIX (in any parser that reads an AI reply with an expected shape):
```python
text = (text or "").replace("\\r\\n", "\n").replace("\\n", "\n")
text = text.replace("\r\n", "\n").replace("\r", "\n")
```
Then split subject/body on *real* newlines: subject = first line after a
`SUBJECT:` header; body = everything after that header, `.lstrip("\n")`.

Prompt hygiene helps too: tell the model explicitly "use REAL line breaks,
never the two-character backslash-n sequence". This is the same class of
robustness as the `<<<...>>>` marker protocol already documented — always assume
the model will mangle format and make parsing defensive + fallback-ready.

## 2. AI-personalized per-curator pitch (beats blasting one template)
Blasting the SAME templated body to every curator is what gets playlist emails
ignored. The upgrade: one unique AI email per curator referencing their actual
focus/platform/location.

- `aiwriter.personalize_pitch(curator_dict, release, settings)` → (subject, body).
- Build a DETERMINISTIC fallback first (`curator.compose_pitch`) and return it if
  the AI is down or returns < ~40 usable chars. The button must ALWAYS return a
  usable, on-brand pitch — never surface an AI error to the user for this.
- Detect fallback at the caller by re-composing the template and comparing
  (subject==fb_subj and body==fb_body) → flag `fallback=true` for the UI.
- Only generate for curators WITH an email on file; skip (not fail) the rest.
- Wire a `personalized=1` flag into the send path so the unique bodies actually
  go out, with the template as a one-checkbox fallback.

## 3. Self-sending daily digest ("Owner's Daily Briefing")
Pattern for a self-contained morning email that watches the operation:
- `briefing.py` with `build_briefing()` (deterministic plain+html from
  `db.dashboard_stats()`), `send_briefing(dry_run=…)`, CLI: `python3 briefing.py`
  (dry-run preview) / `--send` / `--to x` / `--no-ai`.
- Reuses the existing email stack (`curator.send_email` handles Gmail-API + SMTP
  and appends the artist signature) — zero new deps.
- Auth-gated preview route (`GET /admin/briefing-preview`) returns JSON and NEVER
  sends; a `POST /admin/briefing-send?dry_run=1` preview path.
- Schedule with a cron: `cd "~/Desktop/ac pe$0" && python3 briefing.py --send`.
  THE CRON RUNS HEADLESS — it must be pure CLI (no admin cookie needed), and the
  recipient comes from a `owner_email` setting (default the Gmail `from` address).

## 4. Dashboard "command center" stats aggregation
Turn scattered raw rows into one decision-oriented dict suitable for the admin
landing tab:
- One `dashboard_stats()` in the db layer that returns: downloads, fans (real
  count — NOT `len(fan_completed_releases("x"))`, that classic bug returns 0),
  subscribers, releases total/featured, curators total + with-email, pitch
  funnel (all four buckets always present: not_pitched/pitched/followed_up/responded),
  follow-ups-due list, missing-lossless list, top downloads.
- Surface ACTIONABLE gaps, not just numbers: "these releases 404 because no
  lossless file", "these curators pitched > N days ago need a nudge".
- Follow-up queue: `pitch_status IN ('pitched','followed_up') AND last_pitched_at
  < now - N days` — only those, never already-advanced (responded) curators.
- Make the follow-up window a tunable setting (`followup_days`, default 7).

## 5. Make a new admin tab trivially
The admin tab nav is generic: a nav `<a href="#x" data-tab="x">` + a section
`id="x" data-ttab="x"`. app.js `activateTab`/`currentFromHash` is hash-driven.
To add a default landing tab, add `if (h === 'x' || h === '') return 'x'` and
change the final `|| 'releases'` fallback to your new tab. Inline status
dropdowns reuse `document.querySelectorAll('[data-status-curator]')` — any new
table's selects are auto-bound, no new JS needed.

## 6. Starlette sync TestClient portal-contention pitfall (testing)
Symptom: a brand-new HTTP test fails intermittently/deterministically with
`concurrent.futures._base.CancelledError` at `portal.call(self.wait_startup)`
when opening a `TestClient(app)` — while the exact same request works standalone
and via a plain Python repro process.

Root cause: this test module uses a **session-scoped `client` fixture** that
holds an open `TestClient` on the shared session `app`. Opening a SECOND
`TestClient` on the SAME app object contends on the anyio portal / asyncio loop
startup, which gets cancelled.

FIX: don't spawn many `TestClient(app)` blocks in one module that also keeps a
long-lived session client on the same app. Consolidate multiple HTTP assertions
that use the same app into ONE `with TestClient(app) as c:` block rather than
one TestClient per test. (If the failure is ordering/flaky, merging the block is
the robust fix — don't just re-run and hope.)

