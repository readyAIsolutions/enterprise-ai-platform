# Public hosting (free) + SC login fix + smtplib newsletter + curator audiences

## Free public URL without buying a domain — Cloudflare Quick Tunnel
Install (no root / system-wide):
```bash
mkdir -p ~/bin
curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o ~/bin/cloudflared
chmod +x ~/bin/cloudflared
```
Run (long-lived, background, silent):
```bash
~/bin/cloudflared tunnel --no-autoupdate --url http://localhost:8533 --logfile /tmp/site_tunnel.log
```
Grab the URL: `grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" /tmp/site_tunnel.log | head -1`
Verify: `curl -s -o /dev/null -w "%{http_code}\n" https://<url>/`

Gotchas:
- Random hostname, **changes on restart** → ephemeral. Permanent address needs a real domain on the Cloudflare account (a named tunnel via the CF API token + DNS records).
- The public site is the SAME process + DB behind the tunnel. No separate deployment, no config to "upload".

## SC login blank-white-page fix (public URL)
Symptom: site loads publicly, but clicking "Continue with SoundCloud" ends in a blank/white page.
Root cause: the OAuth `redirect_uri` still points at localhost, so SoundCloud bounces to a dead local address.
Fix (both sides):
1. In the site's settings set `sc_redirect_uri = https://<public-url>/callback` and `site_url = https://<public-url>` (they're separate settings; keep them in sync).
2. User must add `https://<public-url>/callback` as a Redirect URI in their SoundCloud app — SC rejects unregistered redirect URIs with a blank/error page.
Note: regenerating the tunnel changes the hostname and re-breaks login until SC's app redirect URI + site settings are updated again.

## Free open-source email sender = smtplib (CPython stdlib)
- No pip package: `import smtplib` + `email.mime` are built-in open source.
- Gmail SMTP: host `smtp.gmail.com`, port `587`, STARTTLS `1`, user = from address (e.g. `8503hh@gmail.com`).
- To actually send you need a **Gmail App Password** in the `smtp_password` setting; until then `curator.smtp_enabled()` is False and the app composes/queues only.
- Reuse one helper set for both jobs: `curator.smtp_config()`, `curator.smtp_enabled()`, `curator.send_email(cfg, subject, body, to, name)`.

### Bi-weekly newsletter cron (watchdog pattern)
- Site-local `newsletter.py`: `build_digest()` (recent releases + beatpacks within N days) → `send_digest(dry_run=...)` to every `db.subscribers_list()` email via `curator.send_email`. Dry-run prints a preview; real send with `--send`.
- Cron: the scheduler requires scripts under `~/.hermes/scripts/`, so put a THIN wrapper there that `subprocess.run`s the site-local script (so it can `import db`).
- Schedule every 14 days = `every 336h`. `no_agent=True`; deliver `origin`; empty stdout stays silent.
- Digest links use `site_url` → point it at the public URL so recipients' links resolve.

## Playlist-curator audiences: local vs global
- Local (ask for location): platform `dj` / `venue` / `bar` — add a `location` column to `curators`, show the admin Location input only for these (JS toggle on the platform `<select>`), and use a DJ body template that names the city.
- Global (no location): `buyer` / `collaborator` — use a deal/beat body template.
- `curator.py` chooses the body template by platform (`DJ_BODY_TEMPLATE` / `DEAL_BODY_TEMPLATE` / default playlist `BODY_TEMPLATE`).
