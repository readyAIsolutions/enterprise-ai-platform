# Starlette admin / SC-gate / tunnel ops pitfalls (AC PE$0 class)

Session-derived, class-level pitfalls for the download-gate artist site. Each one
cost real debugging time — check these before re-diagnosing the same symptom.

## 1. Partial settings form wipes ALL saved settings (data-loss bug)
Symptom: you save one small settings form (e.g. the Daily Briefing recipient,
which only posts `owner_email`) and *every* other saved setting disappears
(SC creds, Stripe keys, R2, Gmail client, bookings...).

Root cause: the shared `admin_settings` handler ran
`db.set_setting(k, data.get(k, ""))` for a hardcoded list of ALL keys. A form
that submits only one field left every other key absent → wrote `""` over it.

Fix (non-negotiable in this class of app):
```python
for k in (ALL_SETTING_KEYS):
    if k in data:                       # only touch what this form submitted
        db.set_setting(k, data.get(k, ""))
```
Checkbox settings (`smtp_starttls`) must also be guarded: only set when
`"smtp_starttls" in data or "smtp_host" in data`.

Rule of thumb: a Starlette admin page with many small `<form>`s posting to ONE
route MUST NOT blindly overwrite the full settings dict. Test with a
partial-form regression test (seed 4 keys, POST only `owner_email`, assert the
other 4 survive).

## 2. Gate "not verifying" = expired SC access token, not logic
Symptom: fan likes/reposts/comments on SoundCloud, gate still says not verified.
Root cause is usually that the stored SoundCloud OAuth **access token is expired
(401)**. `verify_step()` makes a REAL `_api_get` to `/me/favorites`,
`/me/track_reposts`, `/tracks/{id}/comments`; a 401 makes every check return
False → gate never unlocks regardless of what the fan did.

Fix: auto-refresh the access token before verifying, using the stored refresh
token, and PERSIST the fresh token back (also persist a rotated refresh_token
if SoundCloud returns one):
```python
if not sc.is_mock() and not sc.token_valid(token):
    fresh = sc.refresh_access_token(client_id, client_secret, refresh_token, redirect_uri)
    if fresh and fresh.get("access_token"):
        token = fresh["access_token"]; db.update_fan_token(fid, token, refresh_token=fresh.get("refresh_token") or None)
```

### ⚠️ Refresh tokens ROTATE on use — don't burn them in diagnosis
SoundCloud refresh tokens are single-use + rotate. Calling `refresh_access_token`
in a diagnostic/test CONSUMES the stored token and returns a NEW one you must
persist. If you refresh-then-throw-away, the stored refresh token becomes
`invalid_grant` and the owner must do a manual SC re-login. NEVER test-refresh a
production token without saving the rotated result. Valid tokens authenticate
against `/me` (use `token_valid` to confirm, not just that refresh returned bytes).

## 3. Cloudflare Tunnel 502 on large uploads
Symptom: lossless WAV/FLAC upload (50–150MB) fails with HTTP 502 mid-upload.
The origin server is fine — the **tunnel** throttles large POSTs (~140KB/s) and
hard-times-out (~100s), so big uploads die at the edge before the server finishes.

This is a known, non-app-level limit. Options:
- Localhost direct upload (`127.0.0.1:8533`, no tunnel) — works only from the
  server box itself.
- Proper remote fix = **direct-to-R2 presigned upload**: browser uploads the
  object straight to Cloudflare R2, bypassing the tunnel entirely, then the site
  records the R2 reference. R2 must be correctly provisioned (S3 endpoint
  `https://<account>.r2.cloudflarestorage.com` must complete TLS; an SSL
  handshake failure there = wrong/stale account subdomain or R2 not enabled on
  that Cloudflare account — fix in the Cloudflare dashboard, then wire presigned).

Don't treat the 502 as a server bug. Set the XHR `timeout = 0` so the client
doesn't abort slow-but-legit uploads.

## 4. Admin Edit links must carry the `#tab` hash
Symptom: an "Edit" link in a roster row "does nothing." The link was
`/admin?tab=curators&cedit=ID` with NO `#curators` hash. The tab-activation JS
keys off `location.hash`; empty hash forces the DEFAULT tab (dashboard), so the
server loaded the edit form but JS hid the whole section → looks dead.
Fix: `href="/admin?tab=curators&cedit=ID#curators"`. Any JS-driven tab UI must
have links include the qualifying hash, else default-tab wins.

## 5. Fetching a contact's public email from their profile page
SoundCloud/Apple/Spotify/booking pages: extract via `mailto:` first, else a
regex email scan, and FILTER noise (`noreply|no-reply|donotreply|example.|@test.
|sndcdn` + trailing-punctuation strip). Honest result: many famous profiles
don't publish an email → report "No public email" and never fabricate one.
Persist with `contact_type="email"` so it's pitchable by email afterward.

## 6. Rebuildings / tab merges: keep the block move atomic & re-verify
When splitting a huge settings `<section>` into two tabs (e.g. Settings vs
Integrations), re-render-test to confirm `data-ttab`, section ids, and the
`subj-grid`/input CSS still work. Editing a shared `base.html`: only ONE writer
at a time — a sibling-session warning on `base.html` means a concurrent edit
happened; re-read before patching to avoid clobbering.

## 7. Google Translate on a public Starlette site
Add once to the shared `base.html`: a `#google_translate_element` span in the
nav + `googleTranslateElementInit` (InlineLayout.SIMPLE, `pageLanguage:'en'`,
`autoDisplay:false`) + `translate.google.com/translate_a/element.js?cb=...`.
Style the dropdown to the dark theme, hide `.goog-te-banner-frame`, force
`body{top:0!important}`. Client-side translate on the visitor's own request —
no backend, no API key, keeps the owned URL.
