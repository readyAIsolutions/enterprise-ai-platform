# CRM & outreach automation patterns (this app)

Everything here follows the site's no-fake-data rule: auto-advance status + auto-capture
contacts ONLY from real, verified events. Never fabricate a reply, an email, or a pitch.

## Pitch funnel — drive every status from a REAL event
Statuses: `not_pitched -> pitched -> followed_up -> responded`.
- `pitched`      — set automatically the moment a pitch email is actually SENT
                   (both the release-pitch path and the blast path set it).
- `followed_up`  — set automatically the moment a follow-up actually Sends
                   (`/admin/followup-send`, non dry-run).
- `responded`    — must be DETECTED from the real inbox, not clicked.
- Do not auto-land in a state without the underlying event firing. dry_run must NOT advance.

### Auto-detect `responded` from the Gmail inbox
- `gmailapi.search_messages(query)` (GMAIL_LIST_URL + GET metadata) returns real
  inbound messages. Query per curator: `from:<their email> after:<YYYY/MM/DD of last_pitched_at>`.
  If any message matches => `db.set_curator_pitch_status(cid, "responded")`.
- Only scan curators with `email` set AND status in (pitched, followed_up). Skip
  not_pitched/responded.
- Manual "✓ replied" button kept as fallback, but auto-scan is the source of truth.

## Gmail scope: send + readonly, and the re-consent gotcha
- Sending alone needs `gmail.send`. Detecting replies needs **`gmail.readonly`** too.
  Change `SCOPE = "gmail.send gmail.readonly"`.
- CRITICAL: bumping the scope in code does NOT upgrade an already-stored refresh token.
  The user MUST re-run the OAuth consent (Admin -> Integrations -> Gmail) so the new
  refresh token carries the read scope. Until then queries 403; the scan should report
  "reconnect to grant inbox-read" honestly, not pretend.
- `enabled()` should also be mocked to True in tests that exercise the detection loop
  (a test DB has no Gmail config, so it would otherwise bail early).

## Automatic fan emails from SoundCloud
- A fan's email is captured at OAuth sign-in: `exchange_code -> sc.me(token) -> email`,
  stored through `upsert_fan(email=...)`.
- For returning fans, run a quiet auto-sync whenever a recognized fan loads a page
  (`_fan_from_cookie` -> `_sync_fan_profile_quietly(fan)`): resolve a valid token,
  call `sc.me()`, write back email if SC returns one, then stamp `profile_synced_at`
  (throttle ~12h) so it never hammers SC. Wrap in try/except — never break a page load.
- HONEST LIMIT: SoundCloud only returns email/profile to a VALID access token. Expired
  tokens with dead refresh tokens cannot be recovered from storage — the only fix is the
  fan signing in fresh once (fresh SC consent). Don't fabricate; wait for re-login.
- Add a `profile_synced_at REAL` column via the idempotent `_migrate()` (PRAGMA check
  then ALTER TABLE on the `fans` table).

## AI DM pitch — must let the owner SEE and EDIT before sending
- The DM-pitch modal already has an editable textarea; populate it so the owner reviews.
- Add an "✎ AI draft" button that calls `aiwriter.dm_pitch_ai(curator, release)` -> writes
  a SHORT on-brand DM referencing the curator's platform/focus/location, with a
  deterministic fallback to the template `curator.dm_pitch` when the AI is down — the
  button ALWAYS fills an editable pitch (never blanks, never fabricates).
- Route `GET /admin/ai-dm-pitch` is auth-gated and NEVER sends — it only returns
  `{ok, message, contact_url}` for the owner to copy+send on their profile.

## Lossless / press-kit leak check (defense-in-depth verification)
Verify the gated file is not reachable outside `/download/{sid}`:
- Store lossless as `{release_id}.ext` (NOT with a `cover-`/`release-`/`media-` prefix),
  so the `/media/{name}` prefix-whitelist route can never serve it.
- Do NOT mount `storage/` as a static dir — only `/static` should be mounted.
- Press-kit page should contain zero direct file links: gate_enabled => only a
  `/g/{slug}` (gate) CTA. Prove it live: fresh un-gated session hitting `/download/{sid}`
  should 307-redirect to the gate, not serve a file.

## Path-with-space in a systemd unit: quote ExecStart
This app lives at `~/Desktop/ac pe$0`. A systemd user unit with
`ExecStart=/usr/bin/env python3 ${APP_DIR}/server.py` (unquoted) splits on the space and
fails with exit code 2. Fix:
```ini
ExecStart=/usr/bin/env python3 "/home/hunter/Desktop/ac pe$0/server.py"
```
Always double-quote paths containing spaces in ExecStart/WorkingDirectory. The
`install-service.sh` heredoc must also escape `$0` (write `pe\$0`) so bash doesn't expand it.
