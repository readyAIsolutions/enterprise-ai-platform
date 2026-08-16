# Google Cloud Gmail-API OAuth sender (stdlib-only) — AC PE$0 recipe

Use when a Gmail account can't use an App Password (LO's single app password is
held by iCloud) but the artist site still needs to send the newsletter + curator
emails for free. This is the working build from `~/Desktop/ac pe$0` (file
`gmailapi.py` + two routes in `server.py`).

Why not an App Password: Google only allows one(ish) and the user has none free.
Why not an API key: **Gmail sending is OAuth-scoped — an `AIza...` key cannot
POST to `gmail.send` (403).** The credential that matters is a Web-application
OAuth Client ID + Secret + a one-time consent that yields a refresh token.

## Files & wiring (already built — reproduce with modifications)
- `gmailapi.py` — pure stdlib OAuth2 + Gmail send:
  - `settings(db)` reads `gc_client_id`, `gc_client_secret`, `gc_refresh_token`,
    `gc_redirect_uri` (from db settings / env `ACPE_GC_*`).
  - `enabled(cfg)` true when client_id+secret+refresh_token all set.
  - `auth_url(cfg)` → `https://accounts.google.com/o/oauth2/v2/auth?...scope=gmail.send&access_type=offline&prompt=consent`.
  - `exchange_code(code)` → POST token endpoint, returns tokens (incl. refresh_token).
  - `access_token(cfg)` — refresh_token → access_token, cached with expiry.
  - `send(to, subject, html, cfg)` → POST Gmail `users/messages/send`, `{"raw": base64url(MIME)}`, `Authorization: Bearer <at>`.
- `server.py`:
  - `GET /admin/gc-connect` (admin-only) → redirect to `gmailapi.auth_url`.
  - `GET /gc-callback` (public, via tunnel) → `gmailapi.exchange_code`, store
    `gc_refresh_token` in DB, show "Gmail connected".
- `curator.send_email(cfg, subject, body, to, settings=)`: when
  `gmail_enabled(settings)`, call `gmailapi.send(...)`; else SMTP. Every email
  appends the `email_signature` setting (the artist bio) to the body first.
- Settings flow: add `GC_CLIENT_ID/SECRET/REFRESH_TOKEN/REDIRECT_URI` to
  `config.py` MAPPING, `server._site()`, `newsletter._db_settings()`, and the
  admin Settings form (Gmail API section with a "Connect Gmail" button).

## User actions that gate this (recurring — collect all at once)
1. Google Cloud Console → create OAuth client, type **Web application** (a
   Desktop client only allows localhost redirect URIs and cannot use the live
   URL). Enable the **Gmail API** and the `gmail.send` scope.
2. Add the **Authorized redirect URI** = live site + `/gc-callback`
   (e.g. `https://<tunnel>.trycloudflare.com/gc-callback`) to that client.
3. OAuth consent screen: set **In production** (or keep Testing + add the
   owner's Gmail to **Test users**) — otherwise "Access blocked … has not
   completed the Google verification process".
4. Visit the consent link → "Google hasn't verified this app" → **Advanced →
   Go to <host> (unsafe) → Allow** (expected, harmless for a personal app).
5. Gmail API enabled in project: `.../apis/api/gmail.googleapis.com/overview?project=<numeric-id>` → ENABLE (else `SERVICE_DISABLED`).

## Error → fix map
| Symptom | Cause | Fix |
|---|---|---|
| `SERVICE_DISABLED` | Gmail API not enabled in project | Enable it; wait ~1-2 min |
| "Access blocked … not completed verification" | Consent screen in Testing | In production, or add owner as Test user |
| "Google hasn't verified this app" | New unverified app (expected) | Advanced → (unsafe) → Allow |
| "no refresh_token returned" | Already consented before (offline requires first-time) | Revoke app access → re-consent |
| `TypeError … got 'module'` | `import html` shadowing a string param | use `import re` only / rename param |

## Tunnel-rotation reminder
The `trycloudflare.com` hostname changes on cloudflared restart → update the
Google redirect URI in the console AND the DB `gc_redirect_uri` (plus the
SoundCloud app redirect and Stripe callbacks). A stable domain in front of a
named tunnel fixes all callbacks permanently.
