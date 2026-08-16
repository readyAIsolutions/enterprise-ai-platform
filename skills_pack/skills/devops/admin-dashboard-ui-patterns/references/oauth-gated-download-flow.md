# OAuth-Gated Download Flow (droploud-style) — Starlette

Reference for building a "download gate" web app that forces fans to complete
social actions (like / repost / comment) through a third-party OAuth API
(SoundCloud in this case) before unlocking a free download. Built for the
AC PE$0 site at `~/Desktop/ac pe$0` (Starlette :8533). This is a GENERAL pattern —
any "do an action on platform X via OAuth, then unlock content" gate.

## droploud.com model (what we cloned/improved)
- Per-track gate page lists required steps (email, instagram_follow,
  soundcloud_follow, soundcloud_like, soundcloud_repost, soundcloud_comment,
  spotify_follow). Fan sees the required steps BEFORE starting.
- Actions are executed + VERIFIED server-side via SoundCloud OAuth before the
  download link appears. It is NOT a self-reported checkbox.
- SoundCloud OAuth: user clicks "Connect SoundCloud" → authorize popup →
  server holds a short-lived access token and performs the actions on the fan's
  behalf. Server-side token handling (never leak client_id/secret into JS).
- OAuth authorize URL shape (mirror this exactly):
  `https://secure.soundcloud.com/authorize?client_id=...&redirect_uri=URLENCODED`
  `&response_type=code&code_challenge=...&code_challenge_method=S256&state=...`
  (standard PKCE flow).
- Token endpoint: POST `https://secure.soundcloud.com/oauth/token` with
  grant_type=authorization_code + code_verifier.
- Gate data model per step: {id, type, label, url, urls[]}. Steps come from
  `GET /api/tracks/{id}/gate` returning {track, artist, steps[], fan_prefill}.
- Download served as WAV/MP3 only after all steps verified.

## MOCK-FIRST external-integration pattern (KEY TECHNIQUE)
External OAuth/email/social APIs can't be tested offline. Build the ENTIRE flow
against a first-class mock so it works end-to-end with zero network, then flip
to real mode when real credentials exist.

```python
DEFAULT_MOCK = True
_MOCK_DONE = {}  # token -> set of (step, track_id) completed

def is_mock():
    return bool(DEFAULT_MOCK) or not _SC_CLIENT_SECRET

def verify_step(step, token, track_id, **kw):
    return (step, track_id) in _MOCK_DONE.get(token or "anon", set())

def like_track(token, track_id):
    if is_mock():
        _MOCK_DONE.setdefault(token, set()).add(("like", track_id))
        return {"ok": True, "mock": True}
    # real POST to SC API
```

Real mode gated on a client secret being present (fall back to mock otherwise),
so the app never hard-fails without credentials. The UI/server code path is
identical in both modes — only the client swaps. This lets the whole gate flow
(download actually returns bytes) be verified live without a real SC app.

## Starlette TestClient redirect pitfall (IMPORTANT)
`starlette.testclient.TestClient(app)` **follows redirects by default**
(`follow_redirects=True`). So an auth-protected route that correctly returns
303 → `/admin/login` will show up in tests as **200** (the followed login page),
not the 302/303 you asserted. The server is fine; the test client hid the redirect.

```python
def make_client(app, follow_redirects=False):
    from starlette.testclient import TestClient
    return TestClient(app, follow_redirects=follow_redirects)
# then r = client.get("/admin") gives the raw 303 with location header
```
Use follow_redirects=False for any assertion that a route redirects (auth
guards, post-save redirects). Note the signature differs across Starlette
versions; the kwarg exists on recent releases.

## Cookie-based admin auth (no SessionMiddleware needed)
Avoid depending on `itsdangerous`/SessionMiddleware — a plain signed-ish cookie
token works and removes a dependency:

```python
ADMIN_COOKIE = "acpeso_admin"
resp = RedirectResponse("/admin", status_code=303)
resp.set_cookie(ADMIN_COOKIE, token, max_age=86400*7, httponly=True)
# guard:
if not db.get_admin_session(request.cookies.get(ADMIN_COOKIE)):
    return RedirectResponse("/admin/login", status_code=303)
```
`request.cookies.get(...)` works without SessionMiddleware. Drop the
`from starlette.middleware.sessions import SessionMiddleware` import if not
used — it pulls `itsdangerous`, which may be missing.

## Admin CRM with an email-blast tab (playlist curators)
A producer-style admin panel adds a "Playlist Curator CRM" tab: store a roster
of curators (platform, name, email, genre, reach, notes, focus), compose a
personalized pitch email per curator from a template, and blast a whole platform.

- Use DRY-RUN default for the email blaster: compose + log entries as
  status="queued" without sending, so it never spams without SMTP configured.
  Flip to real send when SMTP host/user/pass present (smtplib + STARTTLS).
- Roster data model per curator: platform in {spotify, spotify_editor, apple,
  deezer, amazon, youtube, tiktok, soundcloud, blog, press}.
- Use PLACEHOLDER emails (name.curator@example.com) for demo rosters — never
  invent real personal addresses.
- `email_log` table (curator_id, platform, email, subject, status, error) gives
  per-blast traceability shown back in the admin table.

## REAL-MODE GATE ENFORCEMENT (the big one — user complained it doesn't force)
A gate that marks a step complete when the button is CLICKED is not forcing the
action. LO explicitly rejected this: "the like repost and comment gate doesnt
actually force people to like the track and comment". A self-reported/mock
`_MOCK_DONE` marker is fine for OFFLINE demos but in LIVE mode the gate MUST
query the upstream API to confirm the action really exists before unlocking.

Two halves:
1) ACTION PERFORM: the server performs like/repost/comment ON the fan's behalf
   using their OAuth token (that IS the forcing — it happens on their account).
2) VERIFY: after performing, query the platform's API to confirm the state
   (user has liked / reposted / commented this track). Only `mark_complete`
   when verification passes. Return `verified_against_soundcloud` + a human
   error ("SoundCloud doesn't show this action yet. Do it, then verify again.")
   so a failed verify keeps the step LOCKED.

Add real GET-based verification functions to the client (not just the mock set):
```python
def _api_get(path, token):  # GET with OAuth header, return parsed JSON or {"error":True}
def user_liked(token, track_id):      # GET /me/favorites?limit=200, match track id
def user_reposted(token, track_id):   # GET /me/track_reposts?limit=200, match collection item track.id
def user_commented(token, track_id, user_id=None, text=None):
    # GET /tracks/{id}/comments?limit=100, match user_id and (optionally) text body
```
`verify_step` in live mode calls these; in mock mode it still checks `_MOCK_DONE`.
Gate route flow:
```python
if not is_mock and token is None/mock:  # MUST be signed in with real SC to unlock
    return 4xx/redirect "connect_soundcloud"
action_ok = perform_action(step, track_id, token)
verified = verify_step(step, token, track_id, user_id=fan_sc_id, text=None)
ok = action_ok and verified
if ok: mark_complete(sid, step)   # else step stays locked + tell them to re-verify
```
COMMENT: accept ANY comment — do NOT match an exact canned text (LO: "any comment
at all should work no need for fire track"). Pass `text=None` (or match substring
against the comment list) so a real user comment verifies.

## PKCE verifier must persist between /connect and /callback (real OAuth fails otherwise)
The authorize URL is built with a code_challenge derived from a code_verifier,
but the callback needs THAT SAME verifier to exchange the code. If the callback
uses a hardcoded `"mock_verifier"`, real exchange fails silently in production
("sign in does not work" even though the redirect to SC looks right). Keep a
module-level dict keyed by `state`, set at /connect, popped at /callback:
```python
_VERIFIERS = {}
def _store_verifier(state, v): _VERIFIERS[state] = v
def _pop_verifier(state):      return _VERIFIERS.pop(state, None) or "mock_verifier"
# /connect: verifier, challenge = sc.generate_pkce(); state=...; _store_verifier(state, verifier)
# /callback: verifier = _pop_verifier(state); sc.exchange_code(..., verifier)
```
(valid for single-process uvicorn; multi-worker would need a shared store).

## configure() must NOT re-mock itself
If `is_mock()` is `bool(DEFAULT_MOCK) or not _SC_CLIENT_SECRET`, and `_SC_CLIENT_SECRET`
is read from env AT IMPORT, then DB-stored creds never flip to live. Wire a
`configure(client_id, client_secret, redirect_uri)` called from server startup
with the DB values, and CRITICALLY do NOT call `force_mock(DEFAULT_MOCK)` inside
configure — DEFAULT_MOCK already flips False when a secret is present, so calling
force_mock with the still-True initial value re-enables mock. Just set the globals.

## Admin = owner's SoundCloud account only; everyone else gets Download history
For a personal artist site, the ONE admin is the owner's platform account
(SC username `acpeso`, email `andrewdonnelly8502@gmail.com`). Gate admin by the
fan's OAuth identity, not a generic password form:
```python
def _is_admin_fan(fan):
    # sc_username == admin_sc_username OR fan.email == admin_sc_email (case-insens)
def _admin_from_cookie(request):
    if valid admin session cookie: return it
    fan = fan_from_cookie(request)
    if _is_admin_fan(fan): return {"admin": True, "via": "soundcloud", "fan_id": fan["id"]}
```
Grant the admin cookie inside the OAuth callback when the fan IS the owner.
Nav/role: admin → Admin button; logged-in non-admin fan → "Download history"
(/history route showing their download_events); guest → "Sign in with SoundCloud".
Guard `/admin` so a non-admin fan is redirected to `/history` (not forced to login).

### `mode=admin` login routing (the "Continue with SoundCloud" admin entry)
Make the owner's admin login go through the SAME OAuth flow as fans, so admin
identity comes from the SC account, not a password. Encode the target in the
OAuth `state` and branch the callback redirect on it:
- `/admin/login` page: primary button `href="/login?mode=admin"` ("Continue with
  SoundCloud"); keep the old username/password form hidden behind a `<details>`
  collapsible as a staff fallback (so a session doesn't lock you out if SC OAuth
  is mid-debug).
- `/login?mode=admin` builds the SC authorize URL with `state = "admin|<slug>|<sid>"`.
- `/callback` parses `state`, and after `upsert_fan`, routes back:
  `"/admin" if mode == "admin" else ("/" if mode == "login" else "/releases")`.
  When the fan IS the owner, also create an admin session cookie here.
- Mock branch must mirror this: create a fan named `acpeso` (so `_is_admin_fan`
  is true in demo too), route `mode=admin` → `/admin`, and set the admin cookie.
- `/admin/login` GET handler: if the cookie fan is already the owner, 303 straight
  to `/admin?from=sc` instead of re-showing the form.

## SoundCloud blocks iframing — comment modal MUST open a new tab, not an iframe
SoundCloud sends `X-Frame-Options: DENY` on its authorize page AND track pages,
so an `<iframe src="<sc authorize URL>">` renders as a BLANK modal — the
"comment window doesn't work" bug. Do NOT try to embed SC in a modal/dialog. The
reliable pattern is a two-step modal:
1) The modal shows a **link/button** `target="_blank"` to the track permalink
   (`release.soundcloud_url`) so the fan opens SC in a new tab and actually
   comments there ("Open track on SoundCloud").
2) The fan returns and clicks **"I commented — verify"**, which posts the comment
   step; the server calls `user_commented()` against `/tracks/{id}/comments`
   (active check, accept ANY comment text) before unlocking.
Never load the SC OAuth authorize URL or track page inside an iframe — always
pop out to a new tab. This applies to ANY SC-gated action (like/repost too):
route them through `target="_blank"` links + active server-side verify, never an
embedded iframe.

## Auto-fetch cover art from a SoundCloud URL (oEmbed, no auth)
When a release has an SC permalink but no cover (or only a track id fetch fails),
fetch artwork via `https://soundcloud.com/oembed?format=json&url=<permalink>` and
upgrade the thumbnail to 500x500. Cache it back into the release row. Handles the
common case where you have a full URL, not a numeric track id.

## Directory path with `$` escaping
A directory literally named `ac pe$0` breaks unquoted/unescaped shell commands
because bash expands `$0`. Always escape as `ac pe\$0` in double-quoted shell,
or single-quote the whole path. In Python subprocesses pass the path as an
argument list, not an interpolated shell string.

## Demo seed pattern
`POST /api/seed` creates demo releases + demo admin + demo curators idempotently
so a fresh clone is instantly demonstrable. Useful for any self-contained web
app you want LO to be able to boot and click through immediately.
