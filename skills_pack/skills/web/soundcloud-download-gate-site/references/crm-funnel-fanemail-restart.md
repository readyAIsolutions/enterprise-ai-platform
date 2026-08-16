# CRM funnel, fan emails, press-kit gating & server restart

Durable patterns for the AC PE$0 gate-site (git/project skills umbrella:
soundcloud-download-gate-site).

## 1. Auto-advance the pitch funnel (LO expects this — no manual dropdowns)
Pitch funnel states: `not_pitched -> pitched -> followed_up -> responded`.
LO's standing expectation: **statuses update themselves from real actions**,
never from the admin picking a dropdown value.

Rules that satisfy it:
- A pitch email **actually sent** -> `set_curator_pitch_status(cid,"pitched")`.
  Apply in EVERY send path, not just one: `admin_release_pitch` AND
  `admin_curator_blast`. The blast path must add the curator `id` into each
  `blast_to_curators()` result dict or you can't advance it there.
- A follow-up **actually sent** -> `followed_up`. This needs a REAL send route
  (`/admin/followup-send`); the old "AI draft follow-ups" button only drafted
  text for manual copy, so `followed_up` never auto-set. Add a "🚀 Send
  follow-ups & auto-mark Followed up" button beside the draft button.
- `responded` is ONE CLICK, not fully auto: Gmail scope is `gmail.send`
  only, so the site cannot read the inbox to detect an email reply. To make it
  truly automatic you must add `gmail.readonly` + re-consent. Be honest about
  this limit rather than pretending. Provide a "✓ replied" one-click in the
  follow-up queue AND a "✅ Mark as pitched" one-click in the DM-pitch modal.
- `dry_run` should preview WITHOUT advancing status (only a real send advances).
  Also: the dry-run path must NOT require a configured sender — only the real
  send path should check `sender_enabled` (else preview fails in tests/unset).

## 2. Fan emails from SoundCloud — capture automatically
SoundCloud `/me` returns the authenticated user's `email`, `full_name`, `city`.
The `sc.me()` wrapper was stripping email; surface it and thread it through:
- `me()` -> return `email`/`full_name`/`city` too.
- `exchange_code()` -> pass `profile.get("email")` into the returned dict.
- OAuth callback -> pass `ident.get("email","")` into `db.upsert_fan(...)`.
- Backfill pre-existing fans (who authed before this existed) with a
  `/admin/fan-pull-emails` route: loop fans, call `me(token)` best-effort,
  `update_fan_email()` on hit, skip expired/no-email silently. Guard with
  `if sc.is_mock(): refuse` so you never fabricate emails (LO hard rule).
- New OAuth logins then carry the email automatically; the backfill button is
  the completion path for old fans.

## 3. Press kit must never bypass the gate
The raw audio binary is (and stays) served ONLY via `/download/{sid}` which
requires `all_complete` or `fan_completed(sid, release)`. The press-kit page's
CTA must point at the gate, never a direct link:
- `gate_enabled` -> "🔒 Free Download — unlock via gate" -> `/g/{slug}`.
- else -> `/release/{slug}`.
- Never render `/download/{slug}` (no session) in press-kit HTML.
Smoke test that asserts: press page contains `/g/{slug}` AND NOT
`/download/{slug}` when gate_enabled.

## 4. Server restart pitfall (new routes show as 404)
The old `python3 server.py` keeps holding port 8533. A new `python3 server.py`
then fails with `[Errno 98] address already in use` and EXITS — so the STALE
old process keeps serving, and every brand-new route returns **404** (the old
code doesn't have them). This looks like "my route never registered" but it's
really "old server still running".
Fix: `kill -9 <oldpid>` first (find via `pgrep -af "python3 server.py"`), then
start, then smoke-check a NEW route returns **401-without-auth** (route exists)
not 404 (stale code). 401 = new code live; 404 = kill didn't take.
Use the background runner (terminal background=true) for the server process.

## 5. ac pe$0 path shell-expansion
The project dir `/home/hunter/Desktop/ac pe$0` contains `$0`, which the shell
expands inside DOUBLE quotes. In terminal commands always single-quote the cd
path: `cd '/home/hunter/Desktop/ac pe$0' && ...`. The `patch` tool hits
"escape-drift" on `\"` in this path; do file edits via execute_code's patch()
or read exact bytes and avoid backslash-escaping quotes.
