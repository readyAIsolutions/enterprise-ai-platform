# Admin ops pitfalls & durable techniques (AC PE$0 / download-gate site)

Class-level gotchas hit while operating/extending the single-account admin panel
and its remote deployment. Apply to *any* similar Starlette + Cloudflare tunnel +
SoundCloud-OAuth site.

## 1. Partial settings form WIPES every other setting (critical)
**Symptom:** saving ONE small settings form (e.g. the daily-briefing recipient,
which only posts `owner_email`) blanks out all your other stored credentials
(SC, Stripe, R2, Gmail client…).
**Root cause:** the `admin_settings` handler saved a fixed key tuple with
`db.set_setting(k, data.get(k, ""))` — so any key the form didn't include was
overwritten with `""`.
**Fix:** only write keys that are present in the submitted form:
```python
for k in (all_keys...):
    if k in data:
        db.set_setting(k, data.get(k, ""))
```
Checkbox fields (`smtp_starttls` etc.) likewise: only touch when their form
submits them. **Add a regression test** that seeds sc/stripe/r2/gc, POSTs an
owner_email-only form, and asserts the others survived.

## 2. Cloudflare Tunnel 502 on large uploads — remote upload design
**Symptom:** uploading a 50–150MB lossless WAV/FLAC through the tunnel domain
(`acpeso.shop`) dies with an HTTP 502 before finishing.
**Why:** the tunnel throttles large POSTs to ~140KB/s and hard-times-out around
100s, so big uploads never complete. Server is fine; the path is the problem.
**Fixes that work:**
- Local/on-box admin: POST straight to `127.0.0.1:8533` (bypass tunnel). In the
  JS, detect tunnel host and rewrite the XHR URL to localhost; fall back to
  same-origin otherwise.
- Remote admin (the real ask): use **direct-to-R2 presigned uploads** so the
  browser PUTs to Cloudflare R2 directly (no tunnel, no 502). Requires R2 to be
  properly provisioned — verify the S3 endpoint actually serves (a
  `https://<acct>.r2.cloudflarestorage.com` that fails TLS handshake means the
  account subdomain is wrong / R2 not enabled → needs a dashboard-side fix, not
  code).
- Verify an endpoint "reachable" vs "auth OK": a URL that `resolve`s and returns
  HTTP 403/400 on an unsigned request is reachable (expected); SSL handshake
  failure means the host itself is wrong.

## 3. SoundCloud OAuth refresh tokens ROTATE on each use
**Critical:** calling `refresh_access_token()` consumes the stored refresh token
(SoundCloud returns a NEW one; the old becomes `invalid_grant`). If you test-refresh
outside the app you burn the owner's token.
**Rules:**
- **Only refresh inside the request path that persists the rotated token.** In
  `_fan_token()`, detect an expired access token with `token_valid()`, refresh,
  and `update_fan_token(fid, new_at, refresh_token=new_rt)` (persist BOTH).
- Never call a refresh as a passive diagnostic — it invalidates what you're
  checking.
- SC access tokens expire routinely (401). Gates that verify against real SC API
  (`user_liked/user_reposted/user_commented`) return False on an expired token →
  gate never unlocks even after the fan acts. Auto-refresh fixes the "no gates
  work" bug for real visitors (fresh OAuth login mints a valid token).

## 4. "No email found" for curators is often CORRECT, not a lazy scraper
When a curator-email puller returns "no email" for most of a roster, verify
BEFORE assuming the tool is broken:
- **Mainstream/signed artists** (A Boogie, Ashnikko, Central Cee…) route booking
  through management agencies (CAA/WME) — no public email exists.
- **Megachannels** (proximity, mrsuicidesheep…) use DMs and JS-only contact forms
  (e.g. `trapandbass.com/#submit` is a ~9KB SPA, no email in HTML).
- Some DO publish: indie labels, blogs, type-beat pages ("licensing@…",
  "pr@…", "booking@…"). trapmusic has `licensing@indiemusicgroup.com` right in
  its SC bio.
**To make the puller honest AND effective:** (a) read the bio + follow its own
website/submit/contact links (that's where emails live, not the SC page);
(b) decode obfuscation (`name [at] domain`, `(dot)` — but ONLY bracketed/
parenthesized forms, not plain words "at"/"dot" in prose, which mangle real
sentences into fake emails); (c) handle linktr.ee / beacons.ai; (d) record
`from_url` / a note of where it was found; (e) NEVER fabricate an address.

## 5. Admin tab links MUST carry the `#tab` hash
**Symptom:** an "Edit" row button "does nothing."
**Cause:** the admin tab-activation JS keys off `location.hash`; a link like
`/admin?tab=curators&cedit=ID` has no `#curators`, so JS falls back to Dashboard
and hides the Curators section the edit form lives in.
**Fix:** include the hash: `/admin?tab=curators&cedit=ID#curators`. General rule:
any deep-link into a specific admin tab must end in `#<tabname>`; query params go
before the hash (`?tab=x&msg=... #x`).

## 6. Consolidate overlapping per-item AI buttons
Four per-release AI buttons (Tag / Share card / Press kit / Promo kit) produced
scattered duplicate marketing copy. Collapse to ONE action ("⚡ Full kit") that:
calls every generator (auto-saving the persistent pieces: genre/BPM/key, OG
title/desc, press blurb/highlights) and opens ONE organized drawer with clearly
labeled sections (Metadata · Share card · Press kit · Promo copy, each consumable
via Copy). Isolate per-piece failures so one failing generator doesn't kill the
rest, and report which failed. Keep the persistent pieces auto-saved; leave the
editable promo copy non-persistent so the admin can tweak before send.

## 7. Grouping the admin panel
A single "Settings" tab crammed with 9 unrelated groups is unmanageable. Split
into group tabs with visual separators:
- Content: Dashboard · Releases · Beatpacks · Blog
- Outreach: Curators · Community
- Comms: Email & Newsletter (merge the send form + templates + signature + preview)
- Data: Analytics
- Config: Settings (site copy) · Integrations (SC creds / Gmail API / R2 / Stripe)
Also make the save handler redirect back to the tab that owns the submitted form
(detect by which key the form includes), not a hardcoded tab.

## 8. Site-wide Google Translate widget
Add once to `base.html` (not per page): a `#google_translate_element` span in the
nav + the loader
(`translate.google.com/translate_a/element.js?cb=googleTranslateElementInit`).
`autoDisplay:false` so it never forces on English visitors; provide
`includedLanguages`; hide the intrusive top banner via CSS
(`.goog-te-banner-frame.skiptranslate{display:none!important}` + `body{top:0!important}`).
Style the dropdown to match a dark theme.
