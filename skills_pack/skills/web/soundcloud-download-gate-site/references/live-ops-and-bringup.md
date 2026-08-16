# Live Ops & Bring-Up (acpeso / this class of site)

Session-tested checklist for restoring the site after the box/OS restart, plus
gotchas that cost debugging time.

## Full bring-up (order matters)
1. `systemctl --user restart acpeso` — the server. Confirm `active (running)` and
   that `:8533` is listening (`ss -ltnp | grep 8533`).
2. Cloudflare tunnel: `cloudflared tunnel --config ~/.cloudflared/config.yml run <tunnel-id>`.
   Config lives in `~/.cloudflared/config.yml` (NOT `~/.config/cloudflared/`). Confirm
   `curl -s -o /dev/null -w '%{http_code}' https://acpeso.shop/` → 200.
3. free-router AI (:8920) — usually already up; if not, restart the systemd user unit.
4. `python3 -m pytest -q` — expect 61 (grows as features land).
5. `curl` the key routes: `/`, `/free-for-profit`, `/blog`, `/releases`, `/beatpacks`,
   `/admin`, `/login` all → 200.

## PITFALL: systemd ExecStart path-quoting on a dir with spaces
The project lives in a directory with a space (`/home/hunter/Desktop/ac pe$0`). The
original `install-service.sh` heredoc wrote:
```
ExecStart=/usr/bin/env python3 ${APP_DIR}/server.py
```
systemd splits the unquoted path on the space → `python3: can't open file
'/home/hunter/Desktop/ac'` and the unit loop-restarts with `status=2/INVALIDARGUMENT`.
**Fix:** quote the path in the unit:
```
ExecStart=/usr/bin/env python3 "${APP_DIR}/server.py"
```
Also quote `WorkingDirectory=` and `EnvironmentFile=` the same way. `install-service.sh`
was patched; if it regresses, remember the quote. Also fix the script, not just the
installed unit, so a re-install doesn't recreate the bug.

## PITFALL: Gmail config key names are `gc_*`, NOT `gmail_*`
The Gmail-API (Google Cloud) config is stored under **`gc_client_id` /
`gc_client_secret` / `gc_refresh_token` / `gc_redirect_uri`** (settings table + optionally
`ACPE_GC_*` env). Don't grep for `gmail_*` — you'll wrongly conclude Gmail is
unconfigured. `gmailapi.settings(db)` reads exactly those keys.

## PITFALL: Gmail refresh token got wiped from the DB
The `gc_refresh_token` can be empty in the live DB while the other three `gc_*` keys
survive (the startup banner then reports "Gmail NOT connected"). Recovery:
1. Find it in a backup DB (`acpeso.db.bak_*`) where all 4 `gc_*` keys are present.
2. `UPDATE settings SET value='<token>' WHERE key='gc_refresh_token'`.
3. Verify it still mints a token: `gmailapi._refresh_access_token(gmailapi.settings(db))`
   → returns a `ya29.*` access token. If it mints, sending works.
Always confirm a backup has the value before relying on the live DB.

## PITFALL: SoundCloud `token_valid()` lies in standalone imports
`soundcloud.token_valid(token)` returns `bool(token)` (≈True) when in MOCK mode. A bare
`python3 -c "import soundcloud; ...token_valid(...)"` runs mock (no real creds wired), so
every fan token reports True — which looks like "tokens are fine" when they're actually
all expired. To get the TRUE live result you MUST first:
```
soundcloud.configure(client_id=..., client_secret=...)   # real creds from db.get_setting
# then token_valid() uses the real /me probe
```
Only trust `token_valid=False` reading (all fans expired) from a properly-configured
live probe.

## PITFALL: "Works after refresh, not first visit" = STALE cached HTML
Symptom: a client-side behavior (e.g. the chat "tap to edit profile" modal, or any
new inline JS/UI) doesn't appear on first hit but works after a manual refresh.
The fix "refresh makes it work" is NOT a JS bug report — it means the first hit
served a STALE copy of the page. All chat/gate UI ships as INLINE JS inside the
HTML, so a cached old page = dead buttons / missing features that "fix themselves"
on refresh when the browser re-fetches the current HTML.

Root cause: `server._render()` returned `HTMLResponse(...)` with **no cache
headers**, so Cloudflare and the browser were free to serve a stale page.
Fix — always send no-store on DYNAMIC personalized HTML (fan/admin identity, gate
state, download history change per-viewer; they must never be cached):
```python
def _render(name, ctx):
    return HTMLResponse(jinja_env.get_template(name).render(ctx),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                 "Pragma": "no-cache", "Expires": "0"})
```
Static CSS/JS keep their versioned cache-busting (`?v=` query param on the
`<link>`/`<script>` in base.html) so those still cache fine — bump the version
when you change them. Only the HTML is forced fresh.
Debugging note: before blaming the client JS, reproduce the page locally under the
real identity (fan AND admin AND full base-image wrapper) and check the console —
if the overlay/handler works there with zero errors, the code is fine and the
suspect is stale HTML. Confirm the fix live: `curl -sI <page> | grep -i cache-control`
should show `no-store, no-cache, must-revalidate, max-age=0`.

## PITFALL: local Template/Request repro needs a real Starlette Request scope
When you render a page outside the TestClient to eyeball inline JS, don't build a
bare `Request({'type':'http',...})` — Starlette's `Request`/`Headers` require
`'headers'` in the scope and will `KeyError: 'headers'`. Build the scope with
`'headers': []` (and `'query_string': b''`, `'client': (...)`) or, better, use the
test-suite's signed-in `client` fixture (`c.get("/connect?mode=login")` then the page)
under a fresh `ACPE_DB` so the members-only gate doesn't 303 you to /login.

## Recurring blocker: SC OAuth access tokens expire and refresh tokens die
SoundCloud access tokens expire (~hours) and its refresh-token grant is rejected here, so
the ONLY fix is a fresh SoundCloud OAuth consent ("Sign in with SoundCloud" as the owner
account). Until LO re-logs in: FFP auto-sync and gate "Verify" return connect_soundcloud /
silently fail. This is an owner action, not a code bug. Standalone probe gotcha above is
how you distinguish "tokens are fine (mock)" from "tokens truly expired (live)".
