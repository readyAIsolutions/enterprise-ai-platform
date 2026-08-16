# SoundCloud OAuth token lifecycle + gate-verify + buy-link ops

Session-derived operational knowledge for the AC PE$0 gate site (2026-08-02).
Complements `gate-verify-and-ops-gotchas.md`.

## 1. SoundCloud tokens DO expire — and how to make them effectively "never expire"

Fact (verified live, not guessed):
- SoundCloud owner access tokens are **short-lived JWTs (~1 hour)** — decode the
  JWT payload to see `iat`/`exp`. `https://api.soundcloud.com/me` 401s once expired.
- SoundCloud **secret/refresh tokens rotate**; the refresh endpoint returns
  `{"error":"invalid_grant"}` for a consumed/revoked refresh token.
- **`invalid_grant` on refresh = the refresh token itself is dead.** No code can
  revive it; the owner must re-consent once (only they can complete the SC login).
  Diagnose before blaming code: decode the JWT `client_id` claim and confirm it
  matches the DB's `sc_client_id`, and that the client_id used to refresh is the
  same app that issued the token (a mismatch also yields `invalid_grant`).

The "never expire" pattern that works:
- Proactive refresh: don't wait for `token_valid()` to fail — decode the JWT
  `exp` (add `access_token_expires_in(token)` helper) and refresh **before**
  <5 min remain. Persist the token + the ROTATED refresh token back to the fan row
  on every successful refresh (rotation can strand the stored token otherwise).
- Background keeper: run a 30-min systemd user timer that calls a
  `keep_owner_token.py` which resolves the owner fan and does the proactive
  refresh. Independent of site traffic, so the token is renewed every 30 min
  forever after the one re-auth.
- Surfaces: a no-network `_owner_token_status()` reads the JWT `exp` to show a
  green "auto-renews" vs red "re-sign in" banner in admin.

## 2. Instant gate verify: do the action server-side with the fan's token

Root cause of "repost verify is slow as hell": like/comment were fast because
comments were POSTed server-side with the fan's own token (2xx = proof). Repost
was **verify-only** — fan reposts, we read back `GET /me/track_reposts?limit=200`,
which is eventually-consistent (lags seconds) and paginates (fan with >200
reposts may not even have it on page 1).

Fix (mirror the comment flow): add a `POST /api/repost` that performs
`POST /me/track_reposts/{id}` server-side with the fan's token; a 2xx (or a 409
"already reposted") IS the proof — mark the step verified instantly, zero
read-back. Same idea generalizes to any action whose write-confirm is instant
(like already was via `/me/favorites`).

## 3. Buy-link (purchase_url) auto-sync from release page

Every new release (admin form OR FFP auto-sync) should write
`PUT /tracks/{id}` with form field `track[purchase_url] =
https://site/release/{slug}` (+ `track[purchase_title]`) using the OWNER token
(the only one allowed to edit owner track metadata). Add a one-click admin
"Push buy links to all releases" backfill. Update helper treats 409 as ok=already.

## 4. Gmail reply-scan: the config-surface bug + honest read-scope check

- **KeyError('client_id') "does nothing" bug:** a helper that calls
  `gmailapi.enabled(db, _site())` crashes immediately because `_site()` returns
  the site-settings dict (keys like `gc_client_id`) while `gmailapi.enabled()`
  expects a Gmail config with a bare `client_id` key. Fix: pass
  `gmailapi.settings(db)` (or `enabled(db)`). General lesson: always pass the
  helper's own config object, never a sibling settings dict.
- **Read-scope heuristic lies:** checking "creds exist" does NOT mean
  `gmail.readonly` was granted. The stored consent may predate the scope bump →
  real Gmail read returns 403 ACCESS_TOKEN_SCOPE_INSUFFICIENT. Verify by calling
  Google `oauth2.googleapis.com/tokeninfo?access_token=...` and checking the
  returned `scope` list. One-time re-consent is required; surface a clear
  "reconnect Gmail once" message.
- Keep the scan filter from being too narrow: scan any curator ever emailed
  (`last_pitched_at`/`last_contacted_at`), not only current `pitched/followed_up`.

## 5. Multi-source verified email finding (not just the discovery platform)

Old per-curator email fetch only read the SoundCloud profile + bio links. Real
booking emails live on the entity's own site, ZoomInfo, YouTube about, contact
directories, Discord, Bridge.audio. New `email_finder.py`:
- Runs many queries `("<name>"|<handle>) × (email|booking|contact|business|@gmail|...)`
  over lightweight JS-free engines (DuckDuckGo lite/html, Bing, Google).
- Harvests every candidate email + the page it came from; also crawls the
  entity's own linked pages.
- **Verifies identity before saving**: score each candidate by domain-matches-
  their-site, local-part/handle echoes name/handle, and page-context mentions
  them; auto-save only ≥0.4, list weak ones for manual pick. Filter noise
  (`noreply@`, image-file extension false-positives, sndcdn).
- Honest reality: entities that are DM-only or routed via management have no
  public email — report that with candidates, never fabricate.
- A bulk background pull exists so the whole roster gets searched at once.
