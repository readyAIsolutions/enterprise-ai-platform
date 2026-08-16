# Gate verify speed + SoundCloud track buy-link sync

Two reusable SoundCloud-API techniques learned on the AC PE$0 site. Both are
about knowing WHICH endpoint/account to hit and WHEN the write is authoritative.

## 1. Make a gate step's verify INSTANT (competing on speed)

Problem: fans complain "repost verification is slow as hell". Like/comment feel
instant, repost feels laggy. This is NOT our code — it's SoundCloud's API.

Root cause of the asymmetry:
- **like**: verified via read-back `GET /me/favorites?limit=200` — SoundCloud
  updates favorites near-instantly, so a POST then read-back passes immediately.
- **comment**: already has a fast path — the server performs the action WITH the
  fan's own OAuth token (`POST /tracks/{id}/comments`); a 2xx IS the proof, no
  read-back at all.
- **repost**: was verify-only — fan reposts, then we `GET /me/track_reposts?limit=200`
  which is **eventually-consistent** and can lag many seconds; if the fan has
  >200 reposts the new one may not even be on page 1 → "slow as hell".

The fix (mirrors the comment fast path):
- Add a server endpoint (e.g. `POST /api/repost`) that performs the action
  server-side **with the fan's authenticated token**. A 2xx (or 409 "already
  reposted") from the POST is itself proof the action happened → mark the step
  verified INSTANTLY, zero read-back wait.
- One small frontend change: the step button calls this endpoint instead of the
  slow verify-only route; on `ok` render the step done + reveal the download.
- Treat SoundCloud 409/403 "already reposted" as SUCCESS, not an error.

General rule: **after a successful POST to the action endpoint, you don't need a
GET to re-verify — the 2xx is the proof.** Only use the read-back when the action
happened OUTSIDE your flow (fan did it in the SoundCloud app).

## 2. Auto-sync the SoundCloud track "Buy link" to the site release page

Goal: "when a site release (acpeso.shop/release/{slug}) is created, write the
site URL into the SoundCloud track's metadata buy-link field" so the Buy button
on SoundCloud points back at the site's release/gate page.

Technique:
- SoundCloud update = **`PUT /tracks/{id}`** with form-encoded fields under a
  `track[...]` namespace, e.g. `track[purchase_url]` (the buy-link) and
  `track[purchase_title]`. Header `Authorization: OAuth <token>`,
  `Content-Type: application/x-www-form-urlencoded`.
- **You MUST use the track OWNER's token** (the artist/admin account) — only the
  owner can edit its own track metadata. A fan's token cannot.
- Best-effort + fail-safe: wrap in try/except, never raise, never block the
  release-save. If the owner token is missing/expired, silently skip (the write
  self-heals on the next owner re-auth + next release save).
- Wire it into BOTH creation paths: the admin release form AND the auto FFP
  sync loop (so re-syncs keep the buy link fresh).
- Build the URL as `{site_url}/release/{slug}` where site_url comes from the
  site settings (default e.g. https://acpeso.shop).
- **purchase_title label = "Free DL"** (user preference, UPGRADE #55 follow-up):
  LO wants the SoundCloud Buy-link label to read "Free DL", NOT the beat/release
  title. Set `purchase_title="Free DL"` (trivially under SC's 22-char cap) in
  BOTH write sites so they stay consistent: the bulk "Push buy links" admin
  button (`admin_push_buy_links`) AND the per-release auto-sync
  (`_sync_release_buy_link` on create/edit). Do not label it with the track name.

## Owner-token resolution (shared pattern)

The only account that can (a) edit owner track metadata and (b) drive FFP sync is
the owner/admin SoundCloud account. Reuse one resolver:
- match the admin fan by `admin_sc_username` / `admin_sc_email` /
  `admin_sc_user_id`; fall back on `username == "acpeso"`.
- auto-refresh the stored access token via the refresh-token endpoint and persist
  the fresh token back onto the fan row.
- NOTE: the admin SC username may contain characters the setting doesn't (e.g.
  setting `"acpeso"` vs actual `"AC PE$0"`) — so matching by `admin_sc_user_id`
  is the reliable key, not the username string.
- Return "" (skip) when no usable token — never throw.

## Pitfalls
- A 409/403 on an idempotent action (repost) means "already done" → treat as ok.
- `_api_put` is a separate helper from `_api_post`/`_api_get` — form-encode under
  `track[...]` for track-metadata updates.
- Remember to bump the JS cache-bust (`app.js?v=N`) and add tests that assert the
  mock wiring (`update_track_buy_link` records `(track_id, url)`; verify action
  marks the step complete).
