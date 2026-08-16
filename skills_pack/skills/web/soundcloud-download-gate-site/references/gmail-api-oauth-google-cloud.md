# Gmail-API OAuth send (Google Cloud Console) — free sender when no App Password

Used on the AC PE$0 site (`~/Desktop/ac pe$0`, Starlette :8533). Solves the case
where the user has no spare Gmail App Password (e.g. their one password is taken
by iCloud). OAuth replaces the password with a refresh token; 100% free.

## Why not an API key
A Google **API key** (`AIza...`) CANNOT POST to Gmail `users/messages/send` —
Gmail sending is OAuth-scoped user data. An API-key send returns 403. If the user
hands you an API key and asks you to "do email this way," tell them it can't send
Gmail and use OAuth instead (the Client ID + Secret they already made).

## The free OAuth client
- Cloud: APIs & Services → Credentials → Create credentials → **OAuth client ID**.
- **Type = "Web application"** — a "Desktop app" client only allows loopback
  (`localhost`) redirect URIs and will reject a public `https://.../gc-callback`.
- Enable the Gmail API and use scope `https://www.googleapis.com/auth/gmail.send`.
- Add the site's live callback as an **Authorized redirect URI**, e.g.
  `https://<host>.trycloudflare.com/gc-callback`.

## Stdlib-only implementation (no google-* pip deps)
```python
TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL  = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

# consent -> code
AUTH = ("https://accounts.google.com/o/oauth2/v2/auth?"
        "client_id=CID&redirect_uri=REDIR&response_type=code"
        "&scope=https://www.googleapis.com/auth/gmail.send"
        "&access_type=offline&prompt=consent&state=S")

# code -> tokens (first time gives refresh_token)
POST TOKEN_URL form: grant_type=authorization_code, code, client_id,
                     client_secret, redirect_uri

# refresh_token -> access_token (each send)
POST TOKEN_URL form: grant_type=refresh_token, refresh_token, client_id,
                     client_secret

# send
raw = base64.urlsafe_b64encode(mime_message.as_bytes())
POST SEND_URL JSON {"raw": raw}  Header: Authorization: Bearer <access_token>
```

## Consent-screen pitfalls (none need formal Google verification)
| See this | Means | Fix |
|---|---|---|
| "Access blocked: <host> has not completed the Google verification process" | OAuth consent screen in **Testing** mode; owner not a test user | Set Publishing status to **In production** (Confirm), OR add owner email to **Test users** |
| "Google hasn't verified this app — requesting access to sensitive info" | Unverified-app warning | Owner: **Advanced → Go to <host> (unsafe) → Allow**. Test users don't see it |
| "no refresh_token returned" | Authorized before; Google only issues refresh on FIRST consent | myaccount.google.com → Security → Third-party access → revoke, then consent again |

## Wiring into curator.py (two backends)
- `smtp_enabled(settings)`: require BOTH host+user AND password. A host+user with
  an empty password must NOT count as enabled, or sends attempt a doomed Gmail
  login instead of cleanly reporting "not configured."
- `gmail_enabled(settings)`: True when gc_client_id AND gc_client_secret AND
  gc_refresh_token are all present.
- `sender_enabled(settings)`: `gmail_enabled(settings) or smtp_enabled(settings)`.
- `send_email(cfg, subject, body, to, name, settings)`: if `gmail_enabled(settings)`
  → Gmail-API send; else SMTP. Append the artist `email_signature` setting to the
  body in BOTH paths so every email carries the bio + contacts + tagline.
- Newsletter (`newsletter.py`) builds its settings dict from DB and calls the same
  `send_email`, so one backend choice covers newsletter + curator blast.

## Live callback (not localhost)
- `/admin/gc-connect` (admin-only): build `auth_url` from DB gc_* settings, 302 to
  Google.
- `/gc-callback` (public): read `?code=`, `exchange_code(code, redirect, cfg)`,
  store `gc_refresh_token`, show "connected ✔".
- **Redirect = the LIVE public URL**, per LO ("it should be the live site not
  local host"). This lets the owner authorize from any device and matches the DB
  `site_url`. Because the trycloudflare hostname rotates on restart, a permanent
  domain removes the re-registration churn — offer it.
