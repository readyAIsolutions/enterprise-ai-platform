# SoundCloud OAuth token lifecycle + Gmail read-scope + API action patterns (acpeso, 2026-08)

Session-specific, hard-won detail for the download-gate artist site. Condensed so a
future session starts knowing these behaviors instead of re-deriving them.

## 1. SoundCloud OAuth tokens: they EXPIRE and the refresh token ROTATES

- SoundCloud issues **short-lived ~1h JWT access tokens**. Decode the `exp` claim:
  token does NOT stay valid; `token_valid()` (/me) goes False ~1h after mint.
- SoundCloud **rotates the refresh token on each refresh**. If a refresh succeeds but
  the NEW refresh token isn't persisted back to the DB, the stored refresh token is
  now **consumed/stale** and every later refresh returns `invalid_grant`.
- **`invalid_grant` on refresh is fatal and NOT fixable in code** — SoundCloud has
  rejected the stored refresh token outright. The ONLY fix is a fresh owner re-auth
  (click Log in → SoundCloud once). Test refresh with the correct client_id taken from
  the JWT payload itself (payload.client_id), with and without client_secret, to
  distinguish invalid_grant (token dead → re-auth) from invalid_client (wrong app).

### The "never expire" pattern (what to build)
- `access_token_expires_in(token)` — decode JWT `exp`, return seconds remaining.
- `_owner_sc_token(refresh_if_stale=True)` — **proactively refresh BEFORE the token
  dies**: if `not token_valid OR expires_in < 300`, refresh and **always persist the
  rotated refresh_token** via `db.update_fan_token(id, new_at, refresh_token=new_rt)`.
- Background keeper: a systemd user `oneshot` service + `OnUnitActiveSec=30min` timer
  runs a tiny script that calls `_owner_sc_token(refresh_if_stale=True)`. Because
  access tokens live ~1h and the keeper fires every 30 min, once the owner re-auths the
  token is renewed every 30 min FOREVER, independent of site traffic.
  - Service ExecStart must quote the space path: `ExecStart=/usr/bin/python3 /home/hunter/Desktop/ac\ pe$0/keep_owner_token.py` (space + `$0` are both shell-significant → escape both).
- Matcher `_owner_sc_token` must match the owner fan by `admin_sc_user_id` (uid), NOT
  by username string equality — the stored username is `AC PE$0` while the admin
  setting is `acpeso`, so username matching alone misses the owner. `(admin_uid and
  fuid == admin_uid)` is the reliable key (owner uid = 699988658 for acpeso).

## 2. Gmail read-scope: the config-mismatch crash + the heuristic lie

- **Bug that makes a feature "do nothing":** `_detect_curator_replies` called
  `gmailapi.enabled(db, _site())`. But `_site()` returns the SITE settings dict (keys
  like `gc_client_id`), while `gmailapi.enabled()` expects a Gmail config dict with a
  literal `client_id` key. → `KeyError('client_id')` raised on line 1, killing the whole
  scan before it ever touches Gmail. **Always pass `gmailapi.settings(db)`** to
  gmail functions, never `_site()`.
- **`has_read_scope()` was a heuristic lie**: it returned `True` whenever client_id +
  secret + refresh existed, but the stored token may lack `gmail.readonly`, so Gmail
  returns `403 ACCESS_TOKEN_SCOPE_INSUFFICIENT` on any read (search/list). Fix: check
  the token's REAL granted scopes via
  `https://oauth2.googleapis.com/tokeninfo?access_token=<at>` and look for
  `.../auth/gmail.readonly` in `scope`. Re-consent (Connect Gmail once) is the only fix
  when missing; the consent scope should include both `gmail.send` and `gmail.readonly`.
- Reply-scan filter: scan ANY curator ever emailed (last_pitched_at set), not just
  currently `pitched`/`followed_up`, so a late reply still advances the funnel.
- Reply detection can only advance curators actually in the DB with an email we emailed.
  A sender who isn't a curator is never flagged.

## 3. Server-side action = INSTANT verify (compete on speed)

- SoundCloud read-back endpoints are eventually-consistent: `/me/track_reposts?limit=200`
  can lag many seconds after a repost (and miss page 1 if the fan has >200). `/me/favorites`
  updates near-instantly (why like was already fast).
- **Fast pattern:** perform the action SERVER-SIDE with the fan's own OAuth token and treat
  a 2xx as proof. Exposed as `POST /api/repost` (mirrors the existing instant comment
  `/api/comment`). One-click "⚡ Repost to verify" button posts sid; server
  `sc.repost_track(token, track_id)`; 2xx OR `409 already reposted` ⇒ verified instantly.
  Make `repost_track` map 409/403 "already" → `{"ok": True, "already": True}` so an
  existing repost isn't an error. Give like/repost/comment a dedicated step-verify-fast
  handler in app.js; bump the `static/app.js?v=N` cache-bust in base.html every JS change.

## 4. Buy-link (purchase_url) sync back to the site

- To set the SoundCloud track's "Buy link" you `PUT /tracks/{id}` with form field
  `track[purchase_url]` (+ `track[purchase_title]`), using the **owner's** token (only the
  owner can edit their track metadata) → need `_owner_sc_token()`.
- Wire into release create/update: `_sync_release_buy_link(rel)` writes
  `https://acpeso.shop/release/{slug}` + title into the SC track after `db.upsert_release`.
  Best-effort, never raises/blocks. Also add an admin one-click
  `POST /admin/push-buy-links` that backfills all releases (refuse 401 unauth, 409 in mock).
- Add `_api_put(path, token, form=...)` helper (stdlib `urllib.request`, method="PUT") and a
  mock registry (`remembered_buy_link`) so tests assert wiring without network.
