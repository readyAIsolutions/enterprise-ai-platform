# Admin Panel & Uploads — Durable Pitfalls (AC PE$0)

Collected from operating the download-gate site. Class-level, reusable for any
Starlette/Jinja2 artist admin panel behind a Cloudflare Tunnel.

## 1. Starlette multi-form settings-wipe bug (CRITICAL)

Symptom: saving ONE small settings form (e.g. "Daily briefing recipient" which
only posts `owner_email`) erased every other saved setting (R2/Stripe/SC/Gmail…).

Root cause:
```python
for k in ("sc_client_id", ..., "owner_email"):
    db.set_setting(k, data.get(k, ""))     # BAD — writes "" for keys not in the form
```
A partial form only submits its own fields, so `data.get(k, "")` returns `""`
for every other key and OVERWRITES it with empty.

Fix — only write keys actually present in the submitted form:
```python
for k in (...):
    if k in data:
        db.set_setting(k, data.get(k, ""))
# checkbox special-case: only touch when its form is the one being saved
if "smtp_starttls" in data or "smtp_host" in data:
    db.set_setting("smtp_starttls", "1" if data.get("smtp_starttls") else "0")
```
Also: route the redirect back to the tab that owns the form (detect an
integration-form key vs a settings-form key) so the user lands where they saved.

Regression-test pattern: seed SC/Stripe/R2/Gmail settings, POST owner_email-only,
assert the others are untouched. This is a real data-loss bug — add the test.

## 2. Cloudflare Tunnel 502 on large file uploads

Symptom: uploading a 50–150MB lossless WAV through the tunnel ("Upload lossless
now") dies with HTTP 502 after a long stall — the tunnel throttles large POSTs
(~140KB/s) and hard-times-out around ~100s, so the file never finishes.

The local server (127.0.0.1:8533) is fine. The tunnel is the bottleneck.

Fixes (pick per deployment):
- **Admin on the same box:** XHR POST straight to `http(s)://127.0.0.1:8533/<upload-route>`
  when `location.hostname` matches the tunnel domain — bypasses the tunnel entirely.
  Fall back to same-origin `/path` otherwise.
- **Remote admin (best, works from anywhere):** direct-to-R2 presigned upload —
  the browser PUTs the file straight to Cloudflare R2 (its own edge, no tunnel),
  the site records the object key. Implement a server route that mints a
  presigned PUT URL and point the XHR there.
- R2 must actually be provisioned for the account first. A black-box tell that
  R2 is misconfigured: even an unauthenticated HTTPS GET to
  `<accountid>.r2.cloudflarestorage.com` fails with
  `ssl/tls alert handshake failure` — the account subdomain host is wrong/R2 not
  enabled. That needs a Cloudflare dashboard fix, not code.

Also: the upload handler should stream to disk in chunks (`await file.read(1MB)`
loop → write), never `b"".join(chunks)` the whole file into RAM.

## 3. SoundCloud OAuth expiry → GATE NEVER UNLOCKS

Symptom: fans comment/repost/like on SoundCloud but the gate stays locked.

Root cause: the saved SC access_token expires (401). Every gate verify is a REAL
call to SC's API (`/me/favorites`, `/me/track_reposts`, `/tracks/{id}/comments`);
an expired token makes all of them return error → `verify_step` returns False →
gate never unlocks no matter what the fan does.

Fix — auto-refresh before verifying:
```python
def _fan_token(session, fan):
    token = fan.get("sc_access_token") or session.get("sc_access_token") or "mock_token"
    if sc.is_mock() or token == "mock_token":
        return token
    if not sc.token_valid(token):           # live: probe /me
        fresh = sc.refresh_access_token(client_id, secret, refresh_token, redirect)
        if fresh:
            token = fresh["access_token"]
            db.update_fan_token(fid, token, refresh_token=fresh.get("refresh_token"))
    return token
```
CRITICAL: SoundCloud refresh tokens are SINGLE-USE / rotate on each refresh.
- Persist the newly-rotated refresh token every time you refresh, or the next
  refresh gets `invalid_grant`.
- Do NOT run refresh as a one-off diagnostic on production data — it consumes the
  stored refresh token and invalidates it (the token you tested is gone).
- After a token is consumed/rotated, the only recovery is one manual SC re-login.

## 4. Curator email scraping — naive regex misses everything

Symptom: "Pull email" says every curator has no email, which feels wrong.

Reality (verified live): big channels don't publish a crawlable email ON
SoundCloud. The email lives (a) obfuscated in the bio (`bookings [at] site [dot]
com`), or (b) on the curator's OWN website via a "SUBMIT"/"booking" link in the
bio (e.g. `SUBMIT: https://trapandbass.com/#submit`).

A scraper that only regexes the SC page HTML + a heavy noise filter finds almost
nothing. The useful scraper:
1. Reads the bio and ALSO follows the bio's own website/submit/contact/management
   links (BFS a few pages deep, prefer linktr.ee/beacons.ai/mailto).
2. Decodes obfuscated emails: replace bracketed `[at]/(at)/[dot]/(dot)` with
   `@`/`.` — but ONLY bracketed forms. Do NOT rewrite plain identical words
   (`\s+at\s+` in prose mangles "contact me at real.contact" into a fake email).
3. Filters internal/noise domains (noreply, sndcdn, image extensions) but not so
   aggressively it discards real ones.
4. Returns `from_url` so the user sees where it came from; record source in notes.
5. Still never fabricates — for form-only megachannels, report honestly and fall
   back to the DM-pitch copy path.

## 5. Admin tab navigation (Jinja2/Starlette hash routing)

The admin panel keys tab selection off `location.hash`. Links that pass `?tab=...`
as a QUERY param but no `#tab` hash make the JS fall back to Dashboard, so the
target section is hidden — a button like "Edit" appears to do nothing. Always
include the hash: `href="/admin?tab=curators&cedit=ID#curators"`.

## 6. Google Translate on the public site (multi-language visitors)

> Also see `references/public-nav-streamlining.md` — turning the crowded public
> header into a clean PRIMARY nav + right-side account cluster (LO's standing
> style preference for the top bar).

Simple: Google's client-side TranslateElement widget in the shared nav. Add to the
base template (site-wide):
```html
<span id="google_translate_element" title="Translate"></span>
<script>function googleTranslateElementInit(){
  new google.translate.TranslateElement({
    pageLanguage:'en', autoDisplay:false,
    layout: google.translate.TranslateElement.InlineLayout.SIMPLE,
    includedLanguages:'en,es,fr,de,it,pt,ru,...'
  },'google_translate_element');
}</script>
<script src="//translate.google.com/translate_a/element.js?cb=googleTranslateElementInit"></script>
```
No backend, no API key. Style the dropdown to match dark theme and hide the
Google banner (`.goog-te-banner-frame{display:none}` + `body{top:0!important}`).

## 7. Consolidating overlapping AI "buttons" into one Full Kit

When several AI generators produce overlapping marketing copy for the same entity
(tag, share-card/OG, press kit, promo copy), collapse them: one endpoint that runs
all generators, AUTO-SAVES the persistent fields (genre/BPM/key, og_title/desc,
press blurb), isolates per-piece failures (one failing generator doesn't kill the
rest), and opens ONE organized drawer with labeled sections instead of 4 scattered
panels. Remove the superseded buttons + their stray output spans.

## 8. Beatpack 30s previews — unzip server-side, cap at 30s, serve safely

Owner ask: buyers need to hear each track in a beatpack before buying, but you
must not give away the full lossless file. Approach:
- On beatpack upload, unzip server-side and ffmpeg-render a 30s low-bitrate mp3 per
  audio member. `-t 30` is the HARD cap; a short source stays short, a long source
  is truncated to exactly 30s and never exceeds it. Use `-b:a 64k` so even the
  preview isn't release quality.
- Store the JSON preview list (`{name, filename, url}`) in a beatpacks column;
  render numbered `<audio controls>` players on the page from it.
- Serve preview files ONLY via a dedicated route with a `f.parent.resolve() ==
  pdir.resolve()` check so `../server.py` / absolute paths / unknown filenames all
  404. Public previews are fine (that's the point); the full zip stays the paid
  download behind the order-only /beatpack/order route.
- Gotcha: a beatpack can have a real zip on disk but an EMPTY `file` column (if an
  earlier save didn't persist the path). Before generating previews, always
  verify `bp['file']` is set and the file exists; fix the DB path if not.
- PROVE the "can't rip it" guarantee in a test, don't trust it: render a SHORT
  source (1s wav) and assert the preview is <=30s but still has audio, THEN render
  a LONG source (45s wav) and assert the preview is 29.0-30.5s. A 45s source that
  comes back 45s means your `-t 30` cap silently failed and you're leaking full
  tracks. ffprobe duration via `-show_entries format=duration -of csv=p=0`.

## 9. Stripe beatpack product catalog

To make each beatpack a real Stripe catalog item (stable one-time price, visible
in the Stripe Dashboard), a single `/admin/sync-stripe-catalog` route (auth-gated)
should: create/update a `Product` per pack (metadata `beatpack_id`: id), create a
one-time `Price`, and persist `stripe_product_id`/`stripe_price_id` on the pack.
Checkout then uses the stored `price_id` in `line_items=[{"price": id}]` (falling
back to inline `price_data` when unset). Use the configured `stripepay.currency()`
NOT the account's default currency (the two can differ — this account's default was
CAD while the site sells in USD; Stripe charges the requested currency fine).
Gotcha: verify live connectivity with `Balance.retrieve()` + `Product.list()`
first; `Account.retrieve()` can throw `AttributeError` on some standard accounts.
Only create products when `stripepay.enabled()` and after admin auth (401/409
otherwise) so the catalog never gets polluted by anonymous or unconfigured calls.

## 10. Admin direct download (no gate / no payment)

Owner wants to grab any release or beatpack file without doing the fan gate or
paying. Never weaken the public checks — add SEPARATE admin-only routes that are
identity-gated, plus a bypass flag in the shared public download handler:
- Public `/download/{sid}` (release): add `is_admin = _admin_from_cookie(request)
  is not None` and OR it into the allow check. Public gate still enforced for
  everyone else.
- Beatpacks: the paid download is `/beatpack/order/{oid}` keyed by an order token;
  add a NEW `/admin/beatpack/{bid}/download` route (not the token route) that
  calls `_need_admin(request)` (401 if not) then serves the zip directly.
- Same for releases: `/admin/release/{rid}/download` → `_serve_release_audio`.
- Wire the buttons into the admin roster tables (only render when a file exists).
- Test pattern: without auth both admin routes must 401/redirect; with admin
  (mock acpeso via `/connect?mode=admin`) they reach the file-serving layer
  (404 "no file" proves they bypassed gate/payment), NOT a gate redirect. Keep
  the public gate/payment tests passing unchanged.

## 11. Members-only site (login gate before home)

Owner wants the content tabs to appear only when logged in, plus a login page
before home. Implement BOTH layers:
- Nav (base.html): only render the content links (`{% if fan or admin %}`); the
  guest sees just the wordmark + a "Sign in" button.
- Middleware gate: a `BaseHTTPMiddleware` that 303-redirects anonymous visitors
  to `/login` for content PAGES. Key details:
  - Explicit public allowlist: the auth flow (`, /login /connect /callback
    /logout`), `/admin` (has its own auth), `/api/` (returns its own 401 —
    DON'T redirect fetches or client JS breaks), `/static/ /media/`,
    `/stripe/webhook`, seo files.
  - Protect `/` (home) explicitly with `path == "/"` — a leading "/" prefix
    would ALSO match /admin and collide with the admin public prefix.
  - Check BOTH fan cookie and admin session.
- Test impact: the shared `client` fixture should now sign in via the mock
  (`/connect?mode=login`) since content pages are gated; individual tests that
  assert anonymous->401/200 on now-gated pages must switch to a fresh anonymous
  TestClient or sign in first. Add a gate test asserting anonymous content pages
  -> 303 /login while the whitelist stays public.

## 12. SoundCloud owner-token + buy-link push pitfalls

Diagnosing "Push buy links to SC tracks" failing with `N failed (owner token/API)`:

- **Check the keeper systemd unit path FIRST** — a backslash-escaped space
  (`ac\\ pe$0`) is passed to Python literally, so the keeper dies silently every
  run ("No such file") and the owner token never auto-renews → it expires.
  Match the WORKING server unit format: double-quote the whole path
  `ExecStart=/usr/bin/python3 "/home/hunter/Desktop/ac pe$0/keep_owner_token.py"`.
  Verify with `systemd-analyze verify` and watch `journalctl --user -u ...`.
- **The admin banner lies if it only reads the JWT exp claim.** A token can be
  dead (401 on /me) while its JWT still claims ~59m left. Make `_owner_token_status()`
  do a real, throttled (~60s, keyed by token) `sc.token_valid()` /me check instead
  of trusting `access_token_expires_in()`.
- **SoundCloud rotates refresh tokens on every refresh** — once you refresh, the
  old refresh token is consumed and must be replaced by the one returned, or the
  next refresh returns None. Persist the NEW pair immediately (`db.update_fan_token`).
- **`purchase_title` is capped at 22 chars** — sending a full release title makes
  the track PUT return `400 purchase_title is too long`. Truncate to `[:22]` before
  the request; the `track[purchase_url]` field is what actually matters.
- When testing live token state standalone, remember to call
  `sc.configure(client_id=..., client_secret=..., redirect_uri=...)` FIRST or
  `is_mock()` stays True and the results are fake (mock:True).

## 13. Gate "unlike / delete comment" re-lock (live re-verification)

Owner wants: if a fan unlikes a track or deletes their comment AFTER completing
the gate, they lose access and must re-verify to re-download.

- Add `db.revoke_fan_completed(fan_id, release_id)` (DELETE from fan_completions)
  and `db.uncomplete_gate_step(sid, step)` (remove a step from the session's
  `completed` list, recompute all_complete). These undo an earlier completion.
- Add `server.gate_live_recheck(fan, release, session, force=False, ttl=120)`:
  - no-op (return True) when: no fan, mock mode, release not gate_enabled, or
    no like/comment steps in `gate_requires` (only re-check like/comment live;
    repost can't be read back reliably, follow isn't track-scoped).
  - resolve token via `_fan_token`; if `_gate_token_ready` fails -> revoke (can't
    prove they still hold it).
  - for each live-checkable step call `sc.verify_step(step, token, track_id,
    user_id=fan_uid)`; on any False -> `revoke_fan_completed` + `uncomplete_gate_step`
    and return False.
  - throttle with a module-level `_GATE_RECHECK_CACHE[(fan_id,release_id)]=(ts,ok)`
    on the 120s TTL so page loads don't hammer SoundCloud.
- Wire it in TWO places in server.py:
  - `download()`: when `allow and fan and gate_enabled and not is_admin`, call
    `gate_live_recheck(fan, rel, s, force=True)`; if False, redirect back to
    `/g/{slug}?sid={sid}` (re-locked).
  - `gate_page()` remember-me block: only auto-credit `all_complete=1` when
    `gate_live_recheck(...)` is True, so an unliker sees a locked gate, not
    auto-complete.
- Test with monkeypatched live SC (`is_mock->False`, `token_valid->True`,
  `verify_step` returning True then False for "like") — assert completion revoked,
  step cleared, all_complete=0. Mock-mode tests are unaffected (recheck no-ops in
  mock).
- Pitfall: `db.fan_completed()` requires the fan ROW to exist (`get_fan`), so in
  tests use the id returned by `db.upsert_fan(...)` for the fan_id, not a made-up
  string.

## 14. Per-user scoping: DB read helpers must never treat None as "everything"

"Recently analyzed on the analyzer needs to be per user" exposed a cross-user
privacy leak: the page passed `db.list_user_analyses((fan or {}).get("id") or None)`,
and the helper's `if fan_id:` branch silently fell back to `SELECT * FROM analyses
ORDER BY created_at DESC` — returning EVERY user's private analyses whenever the
viewer's fan id couldn't be resolved (e.g. admin signed in via only the admin
cookie, or any auth state without a fan cookie).

Rule for any per-user data helper: an unresolved/None filter MUST yield an empty
list, never "give me everything". Write the guard as `if not fan_id: return []`
and drop the all-rows branch entirely. If an admin overview legitimately needs
everything, give it an explicit dedicated query, not a silent fallback shared
with the user-facing path.

Also, the upload side must store under a real per-user key: anonymous uploads
were funneled to a single shared `"anon"` bucket, which would have mixed every
anonymous user's results together. Use a per-user key (fan id), or gate the
feature behind login so there is no anonymous shared bucket at all.

Test the contract: owner sees exactly their own rows; a different user sees
theirs and never the owner's; and `None`/`""`/unknown id all return `[]`. Add a
regression test like `test_analyze_history_is_per_user` proving the no-leak path.


## 15. Analyzer key detection: band-limit + centering fixes "key is wrong but BPM is right"

BPM was reliable (onset autocorrelation) but key was off on real tracks. Two
recurring DSP mistakes fix it (audio_analyzer.py):

- **Band-limit the chroma.** Raw full-band STFT magnitude lets drums/cymbals
  (broadband, no tonal center, often the LOUDEST thing) dominate the global
  chroma average and drag the key off. Restrict chroma bins to ~55 Hz - 4.2 kHz
  and log-compress each bin's magnitude (`np.log1p(mag)`) before summing into
  pitch classes so pitched harmony wins.
- **Center + normalize the correlation.** A plain `np.dot(avg_chroma, profile)`
  against un-centered Krumhansl-Schmuckler profiles favors keys with loud
  profiles, not the one that actually fits the harmonic SHAPE. Subtract the mean
  from both the averaged chroma and each profile, then score by normalized cosine
  correlation (`dot/(||a||*||p||)`). Guard: if best centered corr < ~0.05, fall
  back to the plain-loudness winner so a weak estimate never returns a random key
  with high confidence.
- **Regression test:** synthesize sine-chord tracks (3 harmonic partials + kick +
  noise) at every root and major/minor, assert >=22/24 exact-key hits. This is the
  test that would have caught the original bug and guards the fix.
- Validation bar is the worker's own synthetic sweep (all 24 correct, conf ~0.85+);
  do NOT defend with a single cherry-picked track.

## 16. Community feed: posts must be grouped into the section the author chose

"Community chats need to be properly organized to the different sections people
choose to put them in" - posts already stored the chosen kind, but the default
"All" view was one flat chronological list with only a tiny badge, so posts did
not clearly live in their section.

Pattern:
- Keep the tab filter working (server-side `?kind=`), but for the default view
  group posts by kind into a FIXED section order (Beats, Tutorials, Chat,
  Connections) with labeled headers; hide empty sections. Single-section tabs show
  just that block.
- In `community_page()` build a `sections` list of `{"id": kind, "posts": [...]}`
  in fixed order; template iterates sections and renders `<h3>` headers with a
  friendly label map + post count. Add CSS for `.community-section / .section-head /
  .section-title` and bump the CSS cache-bust version.
- Regression test: post one of each kind, assert the "All" view renders all four
  headers in fixed order (compare `html.find('>Beats</h3>')` positions) and that a
  single tab omits every other section header.

## 17. Synth-wave nav buttons (fancy animated top header)

Owner wants the top-header links to look like glowing synth buttons, "animated and
fancy". Pattern that fits the existing red/black identity:

- Target `.site-nav > a` (the primary nav links). Turn them into keys with
  rounded border-radius, a red vertical gradient, a neon red border, an inset top
  highlight, a drop shadow for a 3D push feel, Anton/UPPERCASE + letter-spacing,
  and a subtle red text-shadow glow.
- `::before` = a skewed neon scanline that sweeps left->right on a loop, faster on
  hover (`left:-60% -> 160%`).
- `::after` = hidden 4-bar "equalizer" (4 stacked `linear-gradient` bars with
  scaled `background-size`) that fades in on hover and bounces with an `eq` keyframe.
  NOTE: .site-nav > a already used `::after` for an underline hover — replacing it
  with the EQ removes that underline; that's fine.
- Hover lifts the key 1px + boosts glow; `:active` sinks + scales to .97 for a
  press feel. A `synthGlow` keyframe breathes a glow ring on the whole row
  (desktop >=860px only, set gap smaller to fit).
- Accessibility: append every new animated selector (`.site-nav > a`, `::before`,
  `::after`) to the `@media (prefers-reduced-motion:reduce)` kill list.
- Verify: computed style shows the border/radius/gradient/Anton font, and no
  horizontal overflow at desktop (header stays ~62px). Bump the CSS cache-bust
  version in base.html.


## 18. Replacing the community tab with a nexus-style live chatroom (SC identity)

Owner handed a self-contained `nexus.html` (Discord-style chat with channels/DMs/
reactions/presence) and asked to "replace the community tab with this", where the
poster's identity is their SoundCloud account and username defaults to their SC
name, on a page the fans can all chat together in. Do NOT port the file verbatim —
it was Firestore-backed and un-auth'd. Rebuild it against the SITE's own SQLite
backend so accounts tie to the existing SoundCloud fan login:

- New DB tables: `chat_messages(channel,fan_id,author,avatar,color,effect,text,
  action,system,admin,reactions JSON,ts)`, `chat_presence(fan_id,ts,status)`,
  `chat_profiles(fan_id,name,bio,status,avatar,color,effect)`. Steamroll identity
  from the fan: name defaults to `sc_username`, avatar to `sc_avatar`; `chat_profiles`
  rows (display name/color/status) override but default back to SC identity.
- Channels mirror the old community sections (The Void, Beats, Tutorials, Connect)
  so existing homes stay but become real-time chat. Add a `db.chat_channels()`
  fixed list; per-channel feeds via `WHERE channel=? ORDER BY id`.
- Real-time without a socket: client polls `messages?after_id=` every ~2.5s,
  presence heartbeat every ~20s, online list every ~5s. `after_id` pagination keeps
  payloads tiny. Reactions toggle stored as JSON `{emoji:[fan_id]}`.
- Commands: `/me` action msg, admin `/announce` + `/highlight` (system field + badge),
  `/confess` anon. Strip unknown `/cmd` gracefully.
- **Starlette gotcha — do NOT rely on path-param kwargs being injected.** The route
  `Route("/api/chat/send/{channel}", api_chat_send)` did NOT pass `channel` into the
  handler kwarg (it arrived as the function default), while `request.path_params`
  DID hold the real value. Always read `request.path_params.get("channel")` /
  `.get("mid")` inside the handler instead of trusting the signature default. This
  bit twice (send channel + react mid) and only surfaced under a live request, not
  import. 
- **Jinja `tojson` gotcha — mark it Markup or autoescape corrupts the inline JS.**
  Adding a plain `jinja_env.filters["tojson"]=lambda v: json.dumps(v)` then using
  `{{ channels | tojson }}` inside a `<script>` produced `&#34;` `&#39;` `&amp;`
  (HTML entities) because the env has `autoescape=True` — which silently breaks the
  JS (page renders, message feed never loads, composer dead). Fix: return
  `Markup(json.dumps(value, ensure_ascii=False))` so autoescape does not re-escape
  the JSON quotes. Register the filter if the env doesn't already ship `tojson`.
- Serve the chat page on the EXISTING `/community` route (it's already in
  `_PROTECTED_PAGE_PREFIXES`) — no gate/nav changes needed; the chat API lives under
  `/api/chat/...` (public prefix, but each handler 401s without a fan cookie).
- Test via TestClient: page 200 and contains the shell; send to a channel comes back
  in that channel's feed and NOT in another channel's (isolation); reactions toggle.
  Update the OLD community-feed-section test to assert the chatroom instead.

## 19. Embedded link preview (OG tags) — the DB tagline overrides the template

Owner ask: change the site's embedded share/link preview text (e.g. from "Free
downloads. Sick EDM." to something new). There are TWO places that must agree, and
the DB one wins:

- `templates/base.html` OG block: `og:title` / `og:description` (+ `twitter:card`
  mirrors `og_title`/`og_desc`). The non-release fallback is
  `{%% set og_desc = (site.get('tagline') if site else '') or 'fallback' %%}`.
- **The stored `tagline` setting in the DB takes precedence** over the template
  fallback. Editing only the template does nothing for the live preview if a
  tagline is saved (it was: `'Free downloads. Sick EDM.'`). You must ALSO write the
  value to the DB: `db.set_setting('tagline','<new text>')` on the live DB
  (`acpeso.db` — confirm no `ACPE_DB` env override on the systemd unit first).
- Release-specific previews use per-release `og_*`/`description`, so only the
  default site preview changes — say that explicitly to the owner.
- Embed-scrapers (Discord/DM link unfurlers) often cache aggressively; a restart +
  a cache-busting query string or a fresh scrape is expected, not a bug.

## 20. Auto-sync beatpacks to Stripe (create + price change)

Owner ask: "when I update the price on my site it should change the price
accordingly on Stripe per product, and whenever I create a new beatpack or buylink
it makes a product on Stripe." The manual "Sync beatpacks to Stripe catalog" admin
button was the only path; it should happen automatically on create/update.

Pattern:
- Extract a single idempotent + price-aware helper `_auto_sync_beatpack_stripe(db,
  stripe_pay, bp)`: ensure the Product exists (or reuse stored stripe_product_id;
  fall back to create if a stored id is dead), update name/desc/image, then list the
  product's prices and reuse an active Price whose unit_amount == current site cents.
  If none matches, create a new one-time Price at the current amount, ARCHIVE older
  active prices, and set the product `default_price` to the new one. Persist
  product/price ids via `db.set_beatpack_stripe`.
- Stripe Prices are IMMUTABLE — you cannot edit an existing price's amount. "Changing
  the price" always means create a new Price + archive the old + repoint default.
  Build for that, don't try `Price.modify(amount=...)`.
- Hook the helper into `admin_beatpack` right after the save (covers create AND edit
  incl. price change), wrapped in try/except so a Stripe outage never blocks saving.
  Reuse it inside the bulk `admin_sync_stripe_catalog` handler too.
- Checkout already uses the stored `stripe_price_id`, so the updated price flows to
  Stripe Checkout automatically once sync writes it.
- Test with a fake Stripe object (no network): product+price created at the site
  amount, idempotent for an unchanged price (no new Price spawned), and a site price
  change spawns a new Price at the new amount while archiving the old one.









