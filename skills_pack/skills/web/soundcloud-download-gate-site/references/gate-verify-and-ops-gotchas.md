# Gate verify UX + ops gotchas (acpeso site)

## 1. The "verify just loads then does nothing / no message" bug — the DEBUGGING PATH

Symptom (live): clicking a gate "Verify" button did nothing — no success, no failure
text, nothing. LO: "it just loads then doesn't do anything or even give me a message if
i didnt verify."

When a web interaction is silently dead, reproduce it and inspect the RAW network
response, not just what the UI shows:

1. Open the page in the browser, read `data-sid` off the gate wrapper
   (`document.querySelector('[data-gate]').getAttribute('data-sid')`). If it is EMPTY,
   that is the first bug.
2. Fire the same request the button fires, but capture the raw body:
   `await fetch('/unlock/<sid>/like').then(r => r.text())`. Expect JSON; got a 404 HTML page.
3. Root cause chain:
   - A guest who had NOT connected SoundCloud loaded the gate page with an **empty gate
     session id** → Verify POSTed to `/unlock//like` (empty id) → the server returned a
     **404 HTML page**, not JSON.
   - The JS did `r.json().catch(() => null)` → the 404 HTML failed to parse → became
     `null` → `renderStatus(null)` early-returned → **nothing rendered**. Silent dead UI.

Second bug (independent): even when the server DID return the real `not_verified` msg,
the JS only ever rendered the `connect_soundcloud` error branch. The "not verified"
message was returned but never drawn → failed verify showed no feedback even for
logged-in fans.

## 2. The FIX pattern (durable, reusable)

- Guard against empty session id BEFORE firing the request; show a message pointing the
  user to Connect/Login instead of calling a malformed URL.
- Add a visible status region under the gate steps (`#gate-msg`, classes `.ok/.warn/.err`)
  and render EVERY meaningful outcome: connected-needed (warn), token-expired → reconnect
  (warn), not_verified (err, show server msg), verified (ok), and non-JSON/network trouble
  (err). Never swallow a parse failure into a silent null.
- Design reality baked in: a gate that requires SoundCloud interaction lives or dies on
  a currently-valid SC OAuth token. The gate page render happens BEFORE connect for a
  guest, so the empty-session state is a normal first step, not an error — the UI must
  acknowledge it.

## 3. systemd service with a PATH THAT CONTAINS A SPACE

The deploy dir is literally `~/Desktop/ac pe$0` (space + `$0`). A hand-built systemd
unit failed with `code=exited, status=2` and journal:
`python3: can't open file '/home/hunter/Desktop/ac': No such file or directory`.

Cause: unquoted `ExecStart=/usr/bin/env python3 ${APP_DIR}/server.py` — systemd splits
on the space. FIX (quote the executable path inside the unit):
```
ExecStart=/usr/bin/env python3 "/home/hunter/Desktop/ac pe$0/server.py"
```
Also quote `WorkingDirectory=` and `EnvironmentFile=` the same way. Always re-check with
`systemctl --user status <svc>` + `journalctl --user -u <svc> -n 30` after install,
because exit code 2 with a path-split message is a silent-on-first-glance failure.

## 4. Gmail / Google-Cloud config key naming trap

The Gmail-API sender config lives under **`gc_*`** DB setting keys, NOT `gmail_*`:
- `gc_client_id`, `gc_client_secret`, `gc_refresh_token`, `gc_redirect_uri`
  (env override: `ACPE_GC_CLIENT_ID`, `ACPE_GC_CLIENT_SECRET`, `ACPE_GC_REFRESH_TOKEN`).

Querying `gmail_client_id` / `gmail_refresh_token` returns nothing → you'll wrongly
conclude "Gmail config lost." Check the code's actual key names first
(`grep -nE "get_setting|gc_|gmail_" gmailapi.py`) before declaring it broken.

## 5. Recovering a wiped secret from a DB backup

The `gc_refresh_token` (and any setting) can vanish from the live DB (settings-wipe
bugs happen). Keep the `.db.bak_*` snapshots; restore with:
```
sqlite3 acpeso.db "update settings set value=(select value from
  <backup_db> where key='gc_refresh_token') where key='gc_refresh_token'"
```
Then PROVE it: mint a fresh access token via `gmailapi._refresh_access_token(cfg)`
(don't just check the value string exists). Note: values are stored with surrounding
double-quotes — trim if a consumer reads them raw.

## 6. Standalone imports run MOCK mode — probe tokens in LIVE mode

`soundcloud.token_valid(token)` returns `True` for any non-empty token when
`is_mock()` is true. A standalone `python3 -c "import soundcloud"` does NOT configure
real creds, so it reports mock → every token looks "valid." To probe real validity:
```
soundcloud.configure(client_id=db.get_setting('sc_client_id'),
                     client_secret=db.get_setting('sc_client_secret'))
soundcloud.token_valid(at)   # now hits the real /me endpoint
```
SC access tokens expire and SC REFUSES the stored refresh tokens (invalid_client),
so the ONLY recovery is a fresh SoundCloud OAuth consent (owner re-login). "Token valid
in my probe but not in reality" is almost always the mock/live mode trap.

## 7. PROVING a lossless download is truly gated (no bypass)

When the owner asks "the press kit / page should not let people download the song
unless they pass the gate," audit EVERY path the raw file could leave the site. The
lossless file must only ever be reachable through the gated `/download/{sid}` int. The
proof recipe (all quick curl/local checks):

1. **Raw `/download/{sid}` with a fresh, un-gated session** → must NOT serve the file;
   expect a 307 redirect to the gate page:
   `sid=$(curl -s localhost:8533/api/gate-start/<slug> | python3 -c "import sys,json;print(json.load(sys.stdin)['sid'])")`
   `curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' localhost:8533/download/$sid`
   The `.allow` check is `(not gate_enabled) or all_complete or fan_completed` — redirect
   to `/g/{slug}?sid=...` when false.
2. **Lossless files are stored as `{release_id}.wav` (NO cover-/release-/media- prefix)**.
   `/media/{name}` serves only names starting with `cover-`, `release-`, `media-` (and
   labels them image/*), so guessing `/media/{id}.wav` or `/media/release-{id}.wav` → 404.
   Verify with curl (both → 404).
3. **`storage/` is NOT mounted as a static dir** — only `app.mount("/static", ...)` exists.
   Confirm there is no `app.mount("/storage")` / StaticFiles on the lossless dir.
4. **`audio_url` must be empty** — the old direct-file handoff. Query
   `select gate_enabled, lossless_file, audio_url from releases`; every row should be
   gate_enabled=1, audio_url=''.
5. **Press-kit / release page templates** must link the download to the gate
   (`/g/{slug}`) when gate_enabled, never to a raw file. Dump all link hrefs on the live
   press kit page and assert none point at `/download`, `/media`, or a `.wav/.flac`.

Doing this gives the owner hard evidence ("307 redirect", "404", "no file link") instead
of an assertion. Also note: gate_enabled may be 1 while lossless_file is empty for most
releases (no-fake-audio rule) → those downloads honestly 404 "not available yet" until a
real file is uploaded; that's expected, not a bypass.

## 8. Fan emails from SoundCloud — capture them AUTOMATICALLY (Community CRM)

Owner ask: "in community we should already have their emails from soundcloud — get those
automatically somehow." Email should not need an admin button click.

- **SoundCloud exposes the authenticated fan's email via `GET /me`** — but ONLY to a
  request holding a VALID access token. `sc.me()` already returns `email`/`full_name`/`city`
  in LIVE mode; they are captured at OAuth sign-in already (`exchange_code` → `me()` →
  `upsert_fan(..., email)`).
- The gap: returning fans (signed in before email-capture existed, or whose email came
  back empty) never got backfilled without a manual button. FIX — automatic sync on every
  recognized fan visit:
  ```python
  def _fan_from_cookie(request):
      fan = db.get_fan(fan_id=request.cookies.get(FAN_COOKIE))
      if fan:
          _sync_fan_profile_quietly(fan)   # best-effort, throttled, never blocks page
      return fan

  def _sync_fan_profile_quietly(fan, throttle_hours=12):
      if mock or no token: return
      if time.time() - (fan.get("profile_synced_at") or 0) < throttle_hours*3600: return
      usable = _fan_token(None, fan) or token     # may auto-refresh
      if not sc.token_valid(usable): db.mark_fan_synced(fan["id"]); return
      prof = sc.me(usable)
      if prof.get("email") and != stored: db.update_fan_email(...)
      db.mark_fan_synced(fan["id"])               # throttle so we never hammer SC
  ```
- Schema: `fans.profile_synced_at REAL` (idempotent migrate in `db._migrate`) +
  `db.mark_fan_synced(fan_id, ts)`.
- Keep the one-shot `/admin/fan-pull-emails` full-roster sweep as a manual fallback.
- **Honest limit (unchanged reality):** email only comes back with a VALID token. With all
  stored tokens expired + dead refresh tokens, you CANNOT recover existing fans' emails —
  the auto-sync correctly skips them and never fabricates. The moment each fan re-signs in
  once (fresh SC consent) their email drops in automatically on the next page load. Never
  present a fake/guessed email as real.
- Always PROVE the wiring with a regression test that a signed-in fan loads a page (still
  200) and the sync helper is a safe no-op on None / no-token / mock.

## 9. Google Translate top bar — a pure-CSS hide gets defeated at runtime

Symptom (owner): "when we translate the page you need to hide the translate top bar
since it blocks off everything at top of page." The site ships the google.translate
widget (nav dropdown, `autoDisplay:false`). The first fix was pure CSS:
`.goog-te-banner-frame{display:none!important}` plus `body{top:0!important}`. That was
NOT enough — Google translate **re-injects the full-width banner into the DOM at runtime**
and sets the root/body to `top:40px` after the language switch, which can beat a
stylesheet hide (specificity/order + inline style) and push the whole page/header down.

Durable fix = a JS `MutationObserver` that PHYSICALLY removes the injected elements and
resets the inline shift every time they reappear (the nav dropdown widget keeps working;
only the blocking ribbon is gone):
```js
function killGoogRibbon(){
  try{
    document.querySelectorAll('iframe.goog-te-banner-frame, .goog-te-banner-frame, '+
      '#goog-te-banner-frame, .goog-te-banner, .goog-te-spinner-pos, '+
      'iframe[class*="skiptranslate"], iframe[class*="VIpgJd-ZVi9od"]')
      .forEach(el => el.remove());
    if(document.body) document.body.style.top='0px';
    if(document.documentElement) document.documentElement.style.top='0px';
    var tt=document.getElementById('goog-gt-tt'); if(tt) tt.style.display='none';
  }catch(e){}
}
killGoogRibbon();
new MutationObserver(killGoogRibbon).observe(document.documentElement,{childList:true,subtree:true});
```
PROVE it live: inject a fake banner iframe + set `body.style.top='40px'`, wait ~300ms for
the observer, assert the element is gone and both tops are back to `0px`. Keep the CSS as
first-line defense, but the JS is the actual guarantee. Frontend-only (no restart).
**2026 gotcha (AS OF 2026-08):** Google switched the injected ribbon to an obfuscated
element — `iframe.VIpgJd-ZVi9od-ORHb-OEVmcd.skiptranslate` (id `:2.container`,
position:fixed, top:0, height 39px, z-index 10000001) plus 0x0 `VIpgJd-ZVi9od-xl07Ob-OEVmcd.skiptranslate`
variants. The old `goog-te-banner-frame` selector no longer matches it. The stable constant
across ALL variants is the `skiptranslate` class / `VIpgJd-ZVi9od` prefix — match on
`iframe[class*="skiptranslate"], iframe[class*="VIpgJd-ZVi9od"]` in both the CSS
(`display:none!important`) and the JS killer. If a user still reports the ribbon after an
old fix, first reproduce with a real translate + inspect `document.querySelectorAll('iframe[class*="skiptranslate"]')`.

## 10. Pitch funnel — drive EVERY status from a real event (not a button)

Owner ask: "pitched / not-pitched / responded etc should be automatically updated." The
funnel is: `not_pitched` (default) → `pitched` → `followed_up` → `responded`. Make each
transition fire on a REAL event so no one has to click a status dropdown:

- `pitched`     — auto-set the moment a pitch email is actually sent (release-pitch + blast paths).
- `followed_up` — auto-set the moment a follow-up is actually sent (`followup-send`).
- `responded`   — the one that needs machinery: DETECT a real inbox reply.

For `responded`, add an inbox reader to the Gmail sender and scan for inbound mail from
each pitched/followed-up curator's address, since their `last_pitched_at`; if a real reply
exists → `db.set_curator_pitch_status(id,'responded')`. Never fabricate a reply.

KEY Gmail scope gotcha: the sender originally used `gmail.send` only. To read the inbox
you must widen the OAuth scope to `gmail.send gmail.readonly` — and the STORED refresh
token only carries the scopes granted at consent, so **the owner must re-connect Gmail
once** to mint a new refresh token that includes readonly. Until then the scan should
return a clear "reconnect to grant inbox-read" error rather than pretending. `enabled()`
only checks client_id+secret+refresh exist, so it says "configured" even without read —
handle the 403/`scope` error path explicitly.

Implementation shape:
- `gmailapi.search_messages(query)` → GET `users/me/messages?q=...` then
  `users/me/messages/{id}?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date`;
  returns [{id, from, subject, date}]. Throws RuntimeError on auth/scope failure.
- `_detect_curator_replies()` — loop curators `status in (pitched,followed_up)` with email,
  query `from:<email> after:<last_pitched_at>`, advance on any hit.
- Expose a `/admin/scan-replies` route + a Dashboard "Scan inbox for replies (auto)" button
  + a daily no-agent cron (watchdog script: print ONLY when a curator replied or an error;
  empty stdout = silent). Manual "✓ replied" button stays as fallback.
- Tests: mock `search_messages` to return a message from a pitched curator's address and
  assert status advances to `responded`; also 401 on unauthenticated route.

## 11. AI DM-pitch modal — "see the pitch and edit it" (editable + AI draft)

Owner ask: "dm pitch also lets me need to see the pitch and edit it." Pattern for any
compose-and-send modal (DM pitch here; also release-pitch, follow-ups, reward notes):
- The modal must SHOW the generated text in an **editable `<textarea>`** (never a read-only
  output or a copy of a hidden string) and populate any target link (curator profile/contact).
- Keep the deterministic template as the base fill; add an **"✎ AI draft"** button that hits
  an admin-gated route calling an AI generator. The AI-generator must have a deterministic
  fallback (template) so the button ALWAYS fills a usable, editable pitch when the model is
  down or returns garbage — never blanks, never fabricates.
- The AI prompt should reference the curator's real platform/focus/location/reach (not a
  generic hello) and include a free-lossless hook; ask for REAL newlines, normalize
  `\n` / `\r\n` escapes in the parser.
- Bundle the "Mark as pitched / copy / open profile" actions in the same drawer so the flow
  is review → edit → send in one place.
- This is a server.py + aiwriter.py change → needs a service restart to go live. Multiple
  such pending features accumulate; batch the restart decision rather than restarting per
  feature.
- ⚠️ Ask BEFORE restarting the production server. LO has actively denied a
  `systemctl --user restart acpeso` command when it was fired without asking. Treat a
  restart as a confirmation-gated action: finish the code + tests, present "the server needs
  a restart to ship X", and let LO green-light it (or leave it staged). Do NOT bundle the
  restart into the same turn as the code edit and run it unprompted.

## 12. "Fan did like+comment but the site says they didn't" — DIAGNOSE by proving the verify

Owner report: "user mimicry500 did like and comment, site says i didn't; he also recently
changed his username, that might be it."

The username change is a classic red herring. DIAGNOSE, don't guess:
1. **A username change does NOT break verification.** SoundCloud user IDs are permanent;
   the gate matches on the stable `sc_user_id`, not the name. Prove it: with the fan's OWN
   token, `sc.me(token)` returns the SAME numeric id (`/me id`) and the NEW username — if
   the stored id matches, username is irrelevant.
2. **Probe the fan's token in LIVE mode** (standalone import runs mock — see section 6).
   If their token is valid, then verify is REALLY running against SoundCloud.
3. **Run the actual verify functions live** for EACH release's `soundcloud_track_id` and
   print liked/commented. You'll find their real like+comment maps to ONE release (True)
   and every other release is correctly False — because those fans liked/commenting on
   different uploads.
4. **Root cause of a genuine false "didn't":** SoundCloud assigns a NEW numeric track id
   per upload. If a beat was re-uploaded (new file/link), a fan who liked/commented an
   older upload won't match the release's current id. The gate checks the release's stored
   `soundcloud_track_id`.
5. **Hardening that prevents the stale-id case:** a `track_id_from_url()` (oEmbed URL→id
   resolver) + a `_release_track_id(release)` helper that prefers the stored id and, if
   blank, resolves the release's `soundcloud_url` to the current id. Use it in BOTH the
   `/unlock` like/verify path and the comment path so the gate always checks the track the
   fan actually opened.

Also watch: if the release tracks return "private" from SoundCloud's public API, fans
can't be publicly verified against them (only a fan's own logged-in token works against
tracks they've genuinely engaged). oEmbed resolution returns '' for private tracks — which
is itself a signal the track isn't public.

## 13. "Fix all cut off text" — buttons clip long dynamic labels (CSS)

Owner ask: "fix all cut off text in the site." The culprit is almost always `.btn` +
dynamic labels, and the fix is one CSS rule.

Root cause: `.btn` set `white-space:nowrap`, while `.btn-primary`/`.btn-download` also set
`overflow:hidden` (for the animated sheen `::after`). Any long auto-generated button label —
e.g. the home CTA "Get [FREE FOR PROFIT] WHITE SHOOTER Type Beat - REAL MURDER SXIT | …" —
then clipped mid-word (measured ~1811px text in an ~805px box). Buttons were the ONLY
elements actually clipping.

Fix (durable):
```css
.btn{
  white-space:normal; line-height:1.2; text-align:center;
  overflow-wrap:anywhere;  /* never cut off long button labels */
}
```
Labels now wrap to multiple lines and break long words; the sheen stays (it's decorative,
the text no longer overflows because it wraps inside the box).

How to detect cut-off text PROVEN vs guessed: measuring `scrollWidth > clientWidth` gives
FALSE POSITIVES on these buttons because the animated sheen `::after` (absolute, animating
`left` to 170%) inflates `scrollWidth`. The reliable check is the real text-node bound:
```js
// for each element, walk text nodes and compare the textRange's right edge to the box's right
const r = el.getBoundingClientRect();
// set a range over the text node, if rangeRect.right > r.right + 2 -> actually clipped
```
Ignore `scrollWidth`/`scrollHeight` deltas on elements with an animated pseudo-element.
Cache-bust the CSS (bump `?v=` in base.html) so the fix actually ships; verify on Home,
/releases, /free-for-profit, and /release/{slug} after a hard refresh.

Belt-and-suspenders beyond `.btn` — do these in the same pass so NOTHING clips at any
width, not just buttons:
```css
.section-more{white-space:normal;}                 /* "All releases →" links used nowrap */
.card-title{overflow-wrap:anywhere; line-height:1.2;} /* long no-space strings in card titles */
```
`overflow-wrap:anywhere` is the one that breaks unbroken long words/URLs; `line-height`
fixed-height + centered so wrapped multi-line labels sit right for `.btn` and `.card-title`.

Verifying "no cut-off text" when the vision model is down: install `tesseract-ocr` and OCR
the rendered pages (screenshot full-page → `tesseract shot.png stdout 2>/dev/null | grep -E
'Your Long Title...'`) to PROVE the long labels wrap fully, rather than claiming from CSS
alone. Also probe the served CSS version to confirm the bump shipped (browser is fine, or
`curl -s <origin>/ | grep -oE "static/style.css\?v=[0-9]+"`).

HONEST LIMITATION: from a remote/headless box you can only reach the PUBLIC (non-auth) site.
The **admin panel needs the owner's SoundCloud login**, so cut-off text inside admin tables /
pitch panels cannot be visually verified remotely — tell the owner to eyeball those tabs, or
ask them to point you at the exact tab if that's where the clipping is. Admin tables usually
already use `word-break:break-word`, but never assume; confirm per-tab.

## 14. Repost verify is SLOW — make it INSTANT by performing the action server-side (not read-back)

Owner ask: "reposting verification is usually slow as hell on many sites. We need to compete
by making it just as fast as liking or commenting to verify. Find a way."

This is a CLASS-LEVEL SoundCloud gate-verification principle, not a one-off: **verify an
interaction either by (a) the result of the POST you just performed with the user's token,
or (b) a read-back GET — and the choice per step must match how fast SoundCloud's read-back
endpoint updates.** Not all read-backs are equal.

### Why each step's speed differs (the real reason)
- **like** → verify via `GET /me/favorites?limit=200`. SoundCloud updates favorites almost
  IMMEDIATELY after the POST, so read-back verify passes instantly. Fine as-is.
- **comment** → already had a FAST path: the site performs/adds the comment server-side with
  the fan's own token (`comment_action`); a 2xx from the POST **is** the proof → instant.
- **repost** → was `verify-only`: fan reposts externally, then we read back
  `GET /me/track_reposts?limit=200`. This endpoint is **eventually-consistent** on
  SoundCloud — it can lag MANY seconds after the repost, and if the fan has >200 reposts the
  fresh one may not even be on page 1 (limit=200 truncation). THAT read-back lag is the
  "slow as hell" every gating site hits.

### The fix — mirror the already-fast comment pattern
Add a **`POST /api/repost`** action endpoint that performs the repost **server-side with the
fan's own authenticated token**. A 2xx from `POST /me/track_reposts/{id}` IS the proof the
repost happened → mark the step verified instantly, ZERO read-back wait.

Also handle the "already reposted" case in the low-level action:
```python
result = _api_post(f"/me/track_reposts/{quote(track_id)}", token)
if result.get("error"):
    if result.get("status") in (409, 403) and "already" in (result.get("detail") or "").lower():
        return {"ok": True, "already": True, ...}   # already reposted = still a success
    return {"ok": False, ...}
return {"ok": True, ...}
```
This is instinct-compatible with the site's "never fabricate" rule: we are NOT faking a
verify — we genuinely perform the action on the fan's account with their own OAuth token,
exactly like the comment flow already does. The fan consents by clicking the one-click
button.

### Frontend wiring (reuse the comment fast-path shape)
- Gate wrapper gets `data-repost-action="/api/repost"`.
- The repost step renders a dedicated fast button (`.step-verify-fast`), distinct from the
  generic `.step-verify` read-back button: "⚡ Repost to verify".
- JS handler: require a `sid` present (else point to Connect), POST `sid` to the action,
  render every outcome (expired-token → reconnect; ok → step done + reveal download; error →
  message). Always `btn.disabled=true` + "Reposting…" then restore in `.finally`.
- Cache-bust JS (`app.js?v=…` bump in base.html) so the new handler ships.
- New tests: `test_fast_repost_action_verifies_instantly` (POST marks step complete) +
  `test_fast_repost_requires_session` (bad sid → 404). Full suite green (72/72 here).

### Generalize (apply to any future step)
When adding a social gate step, ask "is the read-back endpoint eventually-consistent?"
If yes (like SC reposts, follows), perform the action server-side with the user's token and
treat the 2xx as the verify. If the read-back is near-immediate (SC favorites, comments),
read-back is fine. This is how to keep a gating site "just as fast as liking" for every step.

Live verification after deploy: bad-sid POST → `{"error":"no session"}` 404; fetch the
bumped `app.js?v=` (200); render the gate for a release whose `gate_requires` includes
`repost` and confirm the fast button + `data-repost-action` are in the served HTML
(releases that only require like+comment will NOT show a repost button — expected).

## 14b. ⚠️ 2026-08: SoundCloud DECOMMISSIONED the v1 repost API — repost verify can go fully dead
(as-of 2026-08-02; verify current API state before relying on the section-14 pattern)

Owner report: "reposting still doesn't work on site, it says unknown route." That is NOT the
site's 404. `unknown route` is SoundCloud's own error body, and it comes from the v1 repost
endpoints being removed. Diagnosed by testing every variant against the LIVE API (with a
REAL valid token, in LIVE mode — never standalone/mock, see section 6):

- `POST  /me/track_reposts/{id}`  -> 405 "unknown route"
- `GET   /me/track_reposts`       -> 405 "unknown route"
- `GET   /me/reposts`             -> 405 "unknown route"
- `GET   /users/{id}/reposts`     -> 405 "unknown route"
- `POST  /me/favorites/{id}`      -> 405 "unknown route"  (v1 LIKE write is dead too)
Same token still works on the surviving v1 endpoints: `GET /me`, `GET /me/tracks`,
`GET /me/favorites` (like read-back verify still fine), and `POST /tracks/{id}/comments`
(comment write+verify still fine).

**Why "swap to v2" is not automatic** (tested, all fail from a server/datacenter context):
`api-v2.soundcloud.com` rejected calls here — empty `403 {}` with our app client_id (WAF /
non-browser client rejection) and `401` for known public web client ids; `access_token=`,
`Bearer`, `OAuth` header, `app_version` header, and browser-like headers all failed. So from a
plain server IP there may be NO working server-side call to create or read a repost. This is
an external, platform-level break, not a code bug.

**Debugging recipe for "unknown route" / any dead SC gate step** (durable):
1. Reproduce against the LIVE deployment with a real valid token and a real gate sid bound to
   that fan — `curl -X POST -H 'Cookie: acpeso_fan=<id>' .../api/repost -d sid=...` and read the
   JSON `msg`. Seeing `unknown route` INSIDE the msg == the SC API error is being passed through.
2. Enumerate which v1 read/write endpoints still resolve (405 "unknown route" == route GONE;
   422/400 == route alive, body wrong; 401 == auth). That instantly separates "SoundCloud
   removed it" from "my creds are dead".
3. Do NOT ship a fake "verified" path — the site's honesty rule forbids it. Present the choice:
   (a) get a v2 browser-context credential and wire repost to it once it's proven to work;
   (b) honest fallback (catch 405/unknown-route, tell the fan to repost manually + admin
   one-click "mark done" override); (c) drop `repost` from `gate_requires` (like+comment only)
   until a working endpoint exists.

The section-14 "perform the action server-side and trust the 2xx" pattern is still the right
mental model for steps whose read-back is eventually-consistent — but its endpoint must be
re-validated against the current SoundCloud API before each reuse, because SoundCloud is
actively decommissioning v1 write/read routes.

## 15. Back-write SoundCloud track METADATA (buy link / purchase_url) from the site

Owner ask: "every time a new acpeso.shop/release/(slug) is created use soundcloud api to
insert acpeso.shop/release/(slug) into the metadata -> buy link field."

This is the WRITE side of the integration (the gate flow is the read/verify side): point
each SoundCloud track's **Buy link** (`purchase_url`) at the site release page so the SC
"Buy" button drives fans back into the gate flow.

### The API shape
SoundCloud track metadata is updated with a **PUT** (there is no update helper in the
original client — you must add one):
```python
def _api_put(path, token, form=None, json_payload=None):
    url = SC_API_BASE + path
    data = urllib.parse.urlencode(form).encode("utf-8") if form is not None else (json.dumps(json_payload).encode() if json_payload is not None else None)
    req = urllib.request.Request(url, data=data, method="PUT")
    req.add_header("Authorization", "OAuth " + token)
    if form is not None: req.add_header("Content-Type", "application/x-www-form-urlencoded")
    ...  # urlopen; HTTPError -> {"error":True,"status":...,"detail":...} like _api_post/_api_get
```
The track-update endpoint takes **form-encoded fields under a `track[...]` namespace**:
```python
form = {"track[purchase_url]": url}
if purchase_title: form["track[purchase_title]"] = purchase_title
_api_put(f"/tracks/{quote(str(track_id))}", token, form=form)
```
Add a mock registry (e.g. `_MOCK_BUY_LINKS` + `remembered_buy_link(token, track_id)`) so the
wiring is unit-testable offline without a network call; `update_track_buy_link(...)` records
in mock, real code hits the API.

### ONLY the OWNER account can edit its tracks' metadata — resolve the OWNER token
Updating a track's buy link requires the token of the user who OWNS the track (the artist/
admin account), NOT a fan token. You must resolve the owner fan and auto-refresh its token.

**Matcher trap:** the owner fan's stored `sc_username` may NOT equal the `admin_sc_username`
setting (here the fan is "AC PE$0" but the setting is "acpeso"). Match on the stable
`admin_sc_user_id` / the fan's `sc_user_id` (and fall back to email), not on username:
```python
for f in db.all_fans():
    fname=(f.get("sc_username") or "").strip().lower(); femail=(f.get("email") or "").strip().lower()
    fuid=(f.get("sc_user_id") or "").strip().lower()
    if fname==admin_user or (admin_email and femail==admin_email) or \
       (admin_uid and fuid==admin_uid) or fname=="acpeso":
        admin_fan=f; break
```
Then auto-refresh like the fan/FFP code (`sc.token_valid` → `refresh_access_token` → persist
fresh token). Keep it as one `_owner_sc_token()` helper reused by every owner-token write so
you don't duplicate the find+refresh per call site.

### Wire it into EVERY release-creation path + add a backfill button
- Call `_sync_release_buy_link(rel)` after `db.upsert_release(...)` in BOTH the admin release
  form AND the FFP auto-sync loop. Build the URL from `_site_site_url().rstrip("/") + "/release/" + slug`
  (slug comes back on the `upsert_release` return row even for auto-generated slugs).
- Helper must be **best-effort, never raise, never block the save** (try/except, skip when
  mock / no track_id / no slug / no owner token).
- The owner's stored access token frequently EXPIRES and SC REFUSES the stored refresh token
  (see section 6). A write helper that silently returns on a dead owner token is correct —
  it fails safe and self-heals the moment the owner re-signs in once. DO NOT fabricate or
  half-write.
- Add a one-click **backfill** admin button for existing rows (mirror the FFP-sync button):
  `POST /admin/push-buy-links` loops all releases, `update_track_buy_link` each, returns
  pushed/skipped/failed counts + first few error details. Refuse 409 in mock mode or when the
  owner token is missing (`_owner_sc_token()` == ""), 401 when not admin. Frontend button +
  inline status, bump the `app.js?v=` cache-bust.
- Tests: mock `update_track_buy_link` records `(track_id, url)`; URL is exactly
  `site_url/release/{slug}`; push route 401 anon / 409 in mock. Getting the owner token to
  return non-empty live is the ONLY un-automatable part — it dies on the same expired-token
  blocker as FFP sync until the owner re-authenticates.

### Buy-link LABEL is a fixed "Free DL", NOT the track/release title
Owner preference (durable): the SoundCloud metadata **Buy link label** (`purchase_title`)
must be a fixed `"Free DL"` so every track shows a clean uniform Buy button. Do NOT pass
`rel.get("title")`. Set `purchase_title="Free DL"` in BOTH places that call
`update_track_buy_link(...)` so they stay consistent:
1. the one-shot backfill button `admin_push_buy_links` (the `/admin/push-buy-links` POST), and
2. the auto-write `_sync_release_buy_link(rel)` that fires on release create/edit.
(String is short enough that the 22-char SC cap is a non-issue.) If LO ever asks to change
the button behavior, keep "Free DL" fixed unless he explicitly says otherwise.

### Generalized to any SC track-metadata field
Same pattern covers `purchase_title`, `genre`, `tag_list`, `description`, etc.: PUT
`/tracks/{id}` with `track[<field>]`, using the OWNER token, wrapped best-effort. The
mock/live probe trap from section 6 applies — a standalone `import soundcloud` runs mock and
reports every token valid, so always test real validity under `sc.configure(...)`.

## 16. Keep the owner SoundCloud token from EVER expiring (proactive refresh + keeper)

Owner ask: "fix the soundcloud token and get those buy links working that token SHOULD
NEVER EXPIRE."

### Reality of the tokens (probe before believing anything)
SoundCloud issues **two different tokens** with different lives:
- **Access token = a ~1-hour JWT.** Decode it to see the real expiry: split on `.`, base64url-
  decode the middle segment, read the `exp` claim (also confirms `client_id` — use it to
  prove which registered app issued the token). It expires fast and `GET /me` starts 401ing.
- **Refresh token = a separate string (here ~32 chars).** SoundCloud **rotates/revokes**
  refresh tokens; on expiry it returns `invalid_grant`. An `invalid_grant` on refresh with the
  CORRECT `client_id` (verified from the JWT payload) cannot be revived by code — SoundCloud
  rejected it → the ONLY recovery is a fresh OAuth consent (owner re-login). No code fix
  resurrects a dead refresh token; say this plainly instead of guessing.

Test refresh variants to isolate: wrong client_id → `invalid_client` (401); correct client_id
but dead refresh token → `invalid_grant` (400). That pairing tells you the client is right and
the refresh token is what's dead.

### Durable architecture so the token then never lapses
1. **Decode expiry proactively** instead of waiting for 401:
   ```python
   def access_token_expires_in(token, now=None):
       parts=(token or "").split(".")
       if len(parts)<2: return None
       payload=parts[1]; payload+="="*(-len(payload)%4)
       data=json.loads(base64.urlsafe_b64decode(payload))
       return int(data["exp"]) - int(now or time.time())   # None if no exp claim
   ```
2. **Refresh BEFORE expiry** (not after): in the token-resolver, if the token is invalid OR
   has <5 min (`left < 300`) remaining, refresh; then re-verify. Always **persist the rotated
   refresh token back** (`db.update_fan_token(..., refresh_token=fresh.get("refresh_token"))`)
   so rotation can't strand the stored token.
   ```python
   def _owner_sc_token(refresh_if_stale=True):
       ... resolve owner fan (match on admin_sc_user_id, not username) ...
       left = sc.access_token_expires_in(token)
       still_valid = sc.token_valid(token)
       if not still_valid or (left is not None and left < 300):
           fresh = sc.refresh_access_token(cid, secret, refresh_token, redirect)
           if fresh and fresh.get("access_token"):
               token = fresh["access_token"]
               db.update_fan_token(fid, token, refresh_token=fresh.get("refresh_token"))
       return token
   ```
3. **Background keeper independent of site traffic** — the crux of "never expires": a tiny
   systemd user timer that runs every ~30 min (JWT lasts ~1h, so refresh at half-life) and
   calls the resolver, so the token is renewed even if nobody visits the site. Script prints
   a one-line status (OK with seconds-left / DEAD needs-reauth / ERROR); the unit is
   `Type=oneshot`, `TimeoutStartSec=~45`, `WorkingDirectory=`+`ExecStart=` **quoted** (space
   in the `ac pe$0` path — see section 3):
   ```
   [Timer] OnBootSec=2min  OnUnitActiveSec=30min  AccuracySec=1min
   ```
   `systemctl --user enable --now <name>.timer`; confirm `Active` + next `Trigger`.
4. **Status banner in admin** (no-network readout so the owner sees the fix and the one
   re-auth step): `_owner_token_status()` decodes the stored JWT exp (or "not connected") and
   returns `{ok, dead, label, need_reauth}`. Red banner → "⚠ owner login needed" + a
   `Log in → SoundCloud` link, then "Push buy links". Green banner once live. Pass it into the
   admin template context; render both branches.

### The honest handoff you must state
No code makes a dead `invalid_grant` refresh token work. The deliverable is: (a) a clear
red/green banner telling the owner the ONE re-auth step, and (b) a keeper that, once that one
re-auth happens, keeps the token renewed every 30 min forever. After re-auth, buy-link pushes
auto-run on new releases and via the backfill button — no manual refreshes ever again.

## 17. The "scan inbox for replies does nothing" bug — TWO real root causes + fix

Owner report: "scan inbox for replies doesn't seem to work; hunter.laidlaw.work replied and
it didn't do anything." A silent no-op like this hid a crash and a scope-lie:

**Root cause A — wrong config dict passed to `gmailapi.enabled()` → KeyError on line one.**
`_detect_curator_replies()` called `gmailapi.enabled(db, _site())`. But `_site()` returns the
SITE settings dict (keys like `gc_client_id`, NOT `client_id`), while `gmailapi.enabled()`
expects a Gmail config whose keys are `client_id`/`client_secret`/`refresh_token`. That raises
`KeyError('client_id')`, which the outer `except` swallowed, so the scan DIED before ever
touching the network (returned `"Gmail config: 'client_id'"` and never scanned anything).
FIX: pass the right object — `gmailapi.enabled(db, gmailapi.settings(db))` (or just
`gmailapi.enabled(db)`). This is the same class of trap as section 4 (config key naming): a
function that takes a config dict will KeyError silently if you hand it the wrong dict.

**Root cause B — `has_read_scope()` was a heuristic LIE.** It returned `True` whenever
client_id+secret+refresh existed. But the stored Google refresh token was minted under the old
`gmail.send`-only scope, so the real `search_messages()` call still returned
`403 ACCESS_TOKEN_SCOPE_INSUFFICIENT`. FIX = measure the token's REAL granted scopes via
Google's tokeninfo endpoint (cheap, no mailbox access), not by guessing from creds presence:
```python
def has_read_scope(cfg=None, db=None):
    if not (cfg['client_id'] and cfg['client_secret'] and cfg['refresh_token']): return False
    tok = access_token(cfg)
    info = json.loads(urlopen("https://oauth2.googleapis.com/tokeninfo?access_token="+quote(tok), timeout=20).read())
    return "https://www.googleapis.com/auth/gmail.readonly" in (info.get("scope") or "").split()
```
Then have the scan PRE-CHECK it and return a clear actionable error ("Reconnect Gmail once to
grant inbox-read") instead of silently scanning nothing. `gmailapi.SCOPE` already includes
`gmail.readonly`, so a fresh "Connect Gmail" consent grants it one-time.

**Root cause C (design) — filter too narrow.** The scan only looked at curators currently in
`pitched`/`followed_up`. Widen it to scan ANY curator that has a `last_pitched_at`/email, so a
late reply still advances them regardless of funnel-state drift.

Note: `hunter.laidlaw.work` (the owner's own address) isn't a curator row, so reply-detection
would only catch it if that address is actually in the roster under a pitched curator — reply
detection advances CURATORS we've emailed, not arbitrary inbox addresses.

## 18. Copy rule — NEVER em dashes; sound human like pe$0, not like AI

Owner rule (explicit + emphatic): "NEVER use em dashes again we don't want it to show that its
ai, make it human, make it sound exactly like pe$0 speaking."

This is a durable STYLE preference for ALL copy this site generates (AI pitches, DM drafts,
newsletters, captions, follow-ups, fan notes, email subjects), not a one-off throwaway line.
Enforce it two ways for defense-in-depth:
1. **Prompt the model to forbid it** and describe the voice as a person texting a friend
   (short, punchy, lowercase-friendly, zero corporate fluff, never a marketing bot).
2. **Deterministically strip it** from the returned copy with a `_humanize()` post-processor at
   the AI-return point so even a model slip can't leak a dash:
   ```python
   _EM_DASH = "\u2014\u2013"                       # em + en dash
   def _humanize(text):
       for d in _EM_DASH:
           text = text.replace(" "+d+" ", ", ").replace(d+" ", ", ")
           text = text.replace(" "+d, ", ").replace(d, ", ")
       text = text.replace(", ,", ",").replace(",,", ",")
       text = re.sub(r"\s*,\s*", ", ", text).strip()
       return re.sub(r"\s{2,}", " ", text).strip(" ,")
   ```

**Do NOT leave em dashes in hardcoded fallback copy either** — subjects, DM bodies,
follow-up/fan-note defaults, OG descriptions, social captions, newsletter defaults. Replaced
with clean punctuation: email subject separators use a pipe (`Submission: {title} | AC PE$0`),
prose uses commas/periods. Add a regression test asserting `_humanize` strips both dash types
AND that no SUBJECT template contains `—`/`–`. Cache-bust / restart so the new SYSTEM prompt +
sanitizer actually ship.

User-preference note: this "no em dashes, human voice" rule also governs general chat/status
copy for this user across other contexts (LO/pe$0 wants everything to read human, not bot).

## 19. "X isn't saving / doesn't work" → FIRST rule out stale cache on the LIVE server (recurring, #59/#60/#75)

The single most-repeated owner report on this site is some variant of "front page text isn't
saving" or "SOUNDS / EFFECT / edit profile don't work." In every case so far the LIVE SERVER
was correct and the report traces to a STALE cached page in the owner's browser (or an
edge/Cloudflare cache) — not a code bug. Before touching any code, run this diagnostic:

1. **Verify end-to-end against the real running server, in a real browser** — not assumptions.
   - SAVE path: fire the actual POST the form uses (e.g. `/admin/settings`), then reload the
     live `/` and confirm the saved value is rendered. Do it via the real admin form AND via a
     direct POST so both the route and the UI are proven.
   - CHAT/overlay path: click each overlay (SOUNDS soundboard, EFFECT picker, PROFILE editor)
     in the browser, confirm they open + populate, and read the console for JS errors. Zero
     errors + live page == UI is fine.
2. **Confirm the page is served fresh (not cached at any layer):** check response headers
   `Cache-Control: no-store` and `cf-cache-status: DYNAMIC` on `/` and `/community`. If
   no-store + DYNAMIC are present, Cloudflare is NOT the culprit — the stale copy is purely
   client-side.
3. **Root cause is almost always the owner's own browser cache.** The cure is a hard refresh
   (Ctrl+Shift+R desktop) or clearing site cache on mobile — ONE time per device. Tell the
   owner this plainly, don't just silently "fix" and move on.
4. **After testing, RESTORE what your probe overwrote.** If your verification saved throwaway
   front-page values or logged in test admin sessions, put the real ♰ tagline / real text back
   and clean up the test cookies so you don't leave the site changed. (This is the "restored
   the site's real front-page values" step — easy to forget, owner-visible if skipped.)
5. **Only if a clean reload still fails** do you treat it as a real defect and get the exact
   device/browser + what happens on tap.

Rule of thumb (durable): for ANY "doesn't save / doesn't work" report on a live site, the
cheapest high-value move is to prove the live server + headers are correct BEFORE assuming a
code defect — because a hard refresh clears the entire complaint class. Same class as the
section-13 "cache-bust + hard refresh to ship a fix" guidance, but applied as a DIAGNOSTIC
when the code was never wrong.

### Mobile top-bar overflow — pills untappable on narrow screens
A chat/top bar that uses a fixed height (e.g. `height:50px`) to cram a title + description +
action pills (Profile/Sounds/Effect/live) overflows on <720px, pushing the pills off and
making them untappable — which reads as "the buttons don't work" on a phone. Durable fix:
let the bar `wrap`, hide the description on small screens (`@media (max-width:720px)`), and
keep the action pills visible/tappable. Test by rendering at mobile width and confirming all
pills receive taps. This pairs with the section-13 cut-off-text class of fix (responsive
layout for dynamic content).


