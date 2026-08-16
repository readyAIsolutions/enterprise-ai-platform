# AI-generated public artifacts + pytest/TestClient gotchas (AC PE$0 pattern)

Durable patterns from the Command Center / Daily Briefing / AI-personalized
pitches / Press Kit upgrade line (upgrades #4–#7).

## 1. AI-generated public/storable artifact pattern (e.g. Release Press Kit)
The reusable shape for "AI writes a promotional artifact, it gets saved, then a
public page renders it":

- `aiwriter.<fn>(release, settings=None)` returns plain dict copy (e.g.
  `{blurb, highlights:[..3]}`). NEVER fabricates facts — builds only from real
  release fields (artist/genre/bpm/key/notes/collab).
- **Deterministic fallback is mandatory and must ALWAYS be usable.** When the AI
  is down or returns junk, fall back to a full constructed sentence, never just
  echo a one-word source field (a short `description` like "dark banger" must
  not produce an 11-char press blurb). Leaf helper pattern: compute fallback
  first, `_chat_raw` in try/except, parse, return fallback if parse fails.
- Persist to the row via `db.update_release_fields` after adding idempotent
  `ALTER TABLE ... ADD COLUMN` migrations in `_migrate()` and adding the keys to
  the function's `allowed` set.
- Admin route: `POST /admin/ai-<x>` (auth-gated `_need_admin`) → generate, save,
  return `{ok, slug, fields}` so JS can show a "see it: /press/{slug}" message.
- Public route: `GET /press/{slug}` → `_render("press_kit.html", ...)`; unknown
  slug → 303 redirect to /releases (never 500).
- Template: print-friendly CSS via a `@media print` block; reuses existing
  `blocks` (`content`, `scripts` for inline `<style>`). Add a public link on the
  canonical page (e.g. release.html) and an admin "⚡ <name>" button.

## 2. AI reply robustness (beyond JSON parsing)
- **Models emit literal backslash-n (`\n` strings) instead of real newlines.** When
  the response must be split into `SUBJECT:` header + body, NORMALIZE FIRST:
  `text.replace("\\r\\n","\n").replace("\\n","\n")` then real CRLF, THEN split on
  the first real newline. Otherwise the subject bleeds into the body.
- Also prompt the model explicitly: "use REAL line breaks, never the two-character
  sequence backslash-n."
- Use `_chat_raw` + `_extract`/`_parse_json_object` for structured output; a
  deterministic `_score_fallback` / template fallback guarantees the UI always
  returns something useful even when the AI response is unparseable.
- When writing unit tests that stub `aiwriter._chat_raw`, always snapshot the real
  fn and restore in a `finally:` — leaking a stub (or a `None` `_parse_json_object`)
  breaks the next test in file order.

## 3. Starlette sync TestClient portal contention (pytest)
- Symptom: `concurrent.futures._base.CancelledError` raised at
  `portal.call(self.wait_startup)` (i.e. at `with TestClient(app):`), sometimes
  deterministically for ONE admin HTTP test while an otherwise-identical test
  passes, and only in-suite (the same scenario passes in a standalone script).
- Cause: several HTTP tests reusing the SAME session-scoped `app` object, each
  opening/entering a sync TestClient on it → the anyio portal / lifespan state
  machine collides. A lone standalone reproduction does not show it.
- Fix: **consolidate the related admin HTTP tests into a single `TestClient(...)`
  context** (do all the sub-assertions inside one `with`), rather than many
  separate `with TestClient(app)` blocks over the shared app.
- Verify stability by running the full suite 2–3x (fails may be ordering-sensitive
  even if a single-run passes).

## 4. Self-sending daily digest (Owner's Daily Briefing)
- Build a `briefing.py` CLI: `python3 briefing.py` (dry-run, prints composed
  body), `--send` (real), `--to x` (override), `--no-ai`.
- Reuse the existing email stack: `curator.send_email(cfg, subject, plain, to,
  name, settings)` (Gmail-API backend), `curator.smtp_config(settings)`,
  `curator.sender_enabled(settings)`.
- Recipient via `owner_email` setting with Gmail-API from-address fallback.
- AI lead line optional (marker protocol, `_strip_reasoning`); deterministic
  fallback line if the router is down — never crashes the send.
- Cron: schedule `cronjob action=create schedule="0 8 * * *"` running the CLI
  `--send`; next_run logs the owner's real email so a recipient is always set.
