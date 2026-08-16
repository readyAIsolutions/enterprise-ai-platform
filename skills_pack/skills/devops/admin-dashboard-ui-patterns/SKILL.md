---
name: admin-dashboard-ui-patterns
description: Build admin dashboards (tab bars, settings forms, CRUD tables, analytics, orders/storefront), OAuth-gated download-gate flows (mock-first, SoundCloud), pure-stdlib Cloudflare R2/SigV4 storage, and the Starlette/SQLite pitfalls that bite these apps. Use for admin panels, artist/music sites, payment-order dashboards, email-blast CRMs, and any S3-compatible object store wiring.
---

# Admin Dashboard UI Patterns

## Trigger
Building admin dashboards with settings forms, multi-select dropdowns, and channel selection logic.

## Prerequisites
- Pure HTML/CSS/JS frontend (no React/Vue)
- Python backend with JSON settings storage
- Multi-tenant user settings via auth token

## Patterns

### Admin Tab Bar (show/hide sections by data group)
When an admin panel grows past ~4 stacked cards, promote sections to a real
top-level TAB BAR so users never have to scroll to find a feature. This is the
fix when LO re-issues a request for a feature that exists but is buried below
the fold as a long card — promote it to a tab and it becomes impossible to miss.

Server passes `?tab=<name>` (read query param in the route) and each section
card carries `data-ttab="<name>"`.

```html
<nav class="admin-tabs" data-admin-tabs>
  <a href="#releases" data-tab="releases">Releases</a>
  <a href="#curators" data-tab="curators" class="{{ 'active' if tab=='curators' else '' }}">Playlist Curators</a>
  <a href="#settings" data-tab="settings">Settings</a>
  <a href="#analytics" data-tab="analytics">Analytics</a>
</nav>
<section class="admin-card" id="settings" data-ttab="settings"> ... </section>
<section class="admin-card" id="curators" data-ttab="curators"> ... </section>
```

JS: on tab click + on `hashchange`, show only sections whose `data-ttab` equals
the active tab name (`sec.style.display = show ? '' : 'none'`), toggle an
`active` class on the tab. Derive initial tab from `location.hash` (so deep
links like `#curators` and `?tab=curators` both land on the right tab). Map
anchor ids to groups (e.g. `#sc-helper` → the `analytics` group).

### Reorganizing a Bloated Tab Into Multiple Grouped Tabs (the "Settings has 9 things" fix)
When one tab (usually Settings) has grown to hold unrelated things — config creds,
site copy, an email sender, storage, payments — split it into logically grouped tabs
rather than re-issuing the feature. The classic split: **Settings = site config/copy**
(front-page text, follow-up windows, recipient addresses, booking info) vs
**Integrations = accounts/connections** (SC creds, Gmail API, R2, Stripe), plus fold
loosely-related forms into the tab that already owns that topic (e.g. a newsletter-send
form belongs in the existing Email Templates tab, NOT buried in Settings). Group the tab
bar with thin `.tab-sep` dividers (content | outreach | comms | config) and give the new
config tab a distinct active color so tabs read at a glance.

Four things ALWAYS break when you reorganize — do all of them:
- **JS `currentFromHash()` and the `data-ttab` whitelist must learn the new tab name.**
  The JS shows sections whose `data-ttab` matches the active tab; a new `#integrations`
  hash falls through to the default if you don't add `if (h === 'integrations') return
  'integrations'` to the hash map. Miss this and the tab clicks but nothing shows /
  the section id target never activates.
- **The POST handler must bounce back to the tab that owns the submitted form.**
  A shared `/admin/settings` route that always `RedirectResponse("/admin#settings")`
  dumps you on the wrong tab after saving. Detect which form was submitted by checking
  for its distinguishing keys among the posted fields and redirect
  `#integrations` vs `#settings` accordingly.
- **Cache-bust every changed static file** (`style.css?v=N`, `app.js?v=N`) or the
  browser serves the stale JS/CSS and the new tab "doesn't work".
- **After ANY structural move, re-verify by render.** Rebuild a minimal context and
  render the template, then assert section boundaries: each `data-ttab` section contains
  ONLY its intended `h2/h3` subtitles, and no block leaked into the wrong section.

**CRITICAL PITFALL — don't move HTML sections by blind string-slicing on heading text.**
Programmatically splitting a `<section>` into two by finding heading substrings and
cutting between them mangles the markup: an `<hr class="settings-divider">` plus `<h3
class="admin-subtitle">` open tag at a block boundary gets separated from its heading
text, producing orphaned `<h3 ...>` open tags and broken nesting that only shows up as
a section with missing/empty subtitles. The fast, safe fix is to REBUILD each section
from scratch as clean literal strings (you have all the form content verbatim) and
`txt.replace(old_span, new_settings + new_integrations)`, rather than patching around
the mangled spans. Then run the structural assert above — it catches exactly this.

A reusable structural verifier you can run after any admin template edit:
```python
import re
txt = open("templates/admin.html").read()
assert txt.count("<section") == txt.count("</section>"), "unbalanced sections"
for s in re.split(r'(?=<section class="admin-card)', txt):
    m = re.search(r'data-ttab="([^"]+)"', s)
    if not m: continue
    h2 = re.search(r'<h2 class="admin-card-title">([^<]+)</h2>', s)
    subs = re.findall(r'<h[23][^>]*>([^<]+)</h[23]>', s)
    print(f"[{m.group(1)}]", (h2.group(1) if h2 else ""), "->", subs[1:])
```
If a section prints an empty/`[]` subtitle list that should have content, the split
mangled it — rebuild that section cleanly instead of fighting the strings.

### Combine Overlapping AI One-Click Buttons into ONE "Full Kit" Action
When an entity's admin row has accumulated multiple per-row AI buttons that all
generate overlapping marketing copy about the SAME object (e.g. ⚡ Tag, ⚡ Share
card, ⚡ Press kit, ⚡ Promo kit), LO will call it out as "seems like a repeat of
stuff and very unorganized." The right fix is NOT more buttons — collapse them
into ONE button that generates everything together and opens ONE organized
drawer. Concretely:
- **One backend route** (`POST /admin/ai-full-kit`) that runs ALL generators in a
  single request. Wrap each in a `_try(name, fn)` helper that collects `errors`
  per-piece and returns `None` on failure — **one generator failing must not kill
  the rest** (the blog/model hiccups, the other four still come through and you
  report which one failed). Return `{ok, slug, tag:{}, share:{}, press:{},
  promo:{pitch,social,tiktok,blog,newsletter}, errors:{}}`.
- **Auto-save the PERSISTENT pieces** (genre/BPM/key/description via
  `db.update_release_fields`, og_title/og_desc, press_blurb/press_highlights) in
  the same route; keep the editable promo-copy bundle non-persistent (user tweaks
  before sending). This is the key distinction: metadata/share/press are one-shot
  facts, promo is draft copy.
- **One organized drawer** (not N scattered output panels): labeled sections —
  Metadata (auto-saved) · Share card (auto-saved, Open + Copy-link) · Press kit
  (auto-saved, Open page + highlights) · Promo copy (editable, Copy each piece).
  A single `showFullKit(rid, json)` builds it; reuse the existing
  `.promo-overlay` / `.promo-box` modal CSS rather than inventing new overlay
  styles. Remember `.promo-overlay[hidden]{display:none !important}` if you toggle
  with `hidden`.
- **Also backfill the inline edit row** with the tag fields so the user can review
  them without a second click.
- Before deleting the old buttons, confirm nothing else references their
  `data-*` handlers; keep the always-visible direct artifact links (↗ Release,
  📄 Press kit) even after consolidating the generators.
- Reuse (don't duplicate) the existing `escHtml` helper already in the file — JS
  `function` declarations hoist, so declaring a second identical `escHtml` is
  harmless but sloppy; remove your copy and call the shared one.

### Channel Mutual Exclusion
When a "Both" option exists alongside individual channel options (Email, Phone), clicking "Both" must deselect Email/Phone and vice versa.

```javascript
// Add to init():
document.querySelectorAll('input[name="channel"]').forEach(function(cb) {
    cb.addEventListener('change', function() {
        if (this.value === 'both' && this.checked) {
            document.querySelectorAll('input[name="channel"][value="email"], input[name="channel"][value="phone"]').forEach(function(other) {
                other.checked = false;
            });
        } else if ((this.value === 'email' || this.value === 'phone') && this.checked) {
            const bothCb = document.querySelector('input[name="channel"][value="both"]');
            if (bothCb) bothCb.checked = false;
        }
    });
});
```

### Settings Form → API → Save
1. Build form with IDs matching settings keys (`voice-api-key`, `telegram-bot-token`, etc.)
2. On submit, collect into settings object including `test_phone` and `test_email`
3. POST to `/api/user/settings` with `token` for auth
4. Backend: verify token, save JSON to `data/users/{user_id}.json`
5. Add "Dev Mode" button to login page for immediate access when OAuth fails
code
# Test Campaign Implementation
Frontend: Button `btn-test-campaign` triggers fetch to `/api/campaign/test` with auth token.

Backend: Endpoint reads user settings, then makes actual API calls:
- Vapi: `POST https://api.vapi.ai/call` with `Authorization: Bearer {vapi_...`
- Resend: `POST https://api.resend.com/v1/emails` with `Authorization: Bearer *** 
- Telegram: `https://api.telegram.org/bot{bot_token}/sendMessage`

### Test Campaign Button
Button calls `/api/campaign/test` with stored credentials. Backend makes actual API calls to Vapi/Resend/Telegram.

### Pricing Calculator Implementation
Frontend: Form with inputs for usage metrics (calls/day, emails/day, etc.) submits to `/api/pricing/calculate`.

Backend: Endpoint calculates costs based on:
- Voice: Fonoster SIP at ~$0.005/min
- Email: useSend SMTP (FREE self-hosted)
- CRM: Odoo 19 Community Edition (FREE)
- AI Models: Based on token usage and provider pricing

Returns JSON with daily/monthly/annual costs and breakdown by service.

### Settings Persistence to Environment Variables
When saving settings via admin forms, persist to both:
1. Local storage for immediate UI updates
2. Backend API that writes to .env file for server configuration
3. Live Config class updates via setattr() for runtime changes

See `references/env-persistence-pattern.md` for implementation details.

Example pattern:
```javascript
// Frontend JS
fetch('/api/settings', {
   method: 'POST',
   headers: {'Content-Type': 'application/json'},
   body: JSON.stringify(settings)
});

// Backend Python
def save_settings():
   data = request.get_json()
   # Update in-memory config
   Config.update_config(**data)
   # Persist to .env
   save_to_env(data)
   # Update localStorage fallback
   return jsonify({"status": "success"})
```

### Testing Modules with External Dependencies
When testing backend modules that interact with external services:

1. Extract pure functions for formatting, validation, and business logic
2. Use dependency injection to pass service clients as parameters
3. Create mock clients for testing that simulate service behavior
4. Test error handling and edge cases with various input scenarios

```python
# Extract pure functions for easier testing
def format_notification_text(name, date_str, time_str, email="", source="chat"):
    """Pure function that can be tested without external dependencies."""
    email_line = f"\nEmail: {email}" if email else ""
    return (
        "🔔 <b>NEW BOOKING</b>\n\n"
        f"Prospect: <b>{name}</b>{email_line}\n"
        f"Date: {date_str}\n"
        f"Time: {time_str}\n"
        f"Source: {source}\n"
    )

# Test with dependency injection
def send_notification_to_client(client, message, recipient, user_settings):
    """Send notification using injected client."""
    if not client:
        raise ValueError("Client service not provided")
    
    # Extract settings needed for the service
    service_config = user_settings.get("notifications", {})
    
    return client.send_message(
        to=recipient,
        content=message,
        config=service_config
    )

# Test with mocks
def test_send_notification_to_client(mocker):
    # Mock the client
    mock_client = mocker.Mock()
    mock_client.send_message.return_value = {"status": "sent", "id": "test-123"}
    
    # Call function with mocked client
    result = send_notification_to_client(
        client=mock_client,
        message="Test notification",
        recipient="test@example.com",
        user_settings={"notifications": {"priority": "high"}}
    )
    
    # Verify the mock was called correctly
    mock_client.send_message.assert_called_once_with(
        to="test@example.com",
        content="Test notification",
        config={"priority": "high"}
    )
    
    assert result["status"] == "sent"
```
code
## Pitfalls

### Admin Table "Cut Off by Right Side Panel" = grid full-width class NEVER MATCHED
Symptom (reported repeatedly as "admin panel is cut off by the right side panel in
releases, the Edit/Delete buttons are covered"): cards render side-by-side in two
narrow grid columns instead of stacked full-width, so one card's right edge clips
the next card's action buttons. The FIRST thing to check is a **CSS class-name
mismatch between the HTML class and the CSS selector** — the template had
`class="admin-card admin-wide"` but the CSS rule was written `.admin-card-wide`
(hyphen). Because the selector never matched, `grid-column:1/-1` (full-width) and
`overflow-x:auto` never applied, so the grid's `auto-fit` laid the release manager
and the edit form side-by-side. All my column-width tweaks failed because they
treated the symptom (a narrow card) while the real bug was the missing rule.

Fixes/lessons:
- When "cut off" persists through repeated width/padding fixes, STOP tweaking
  CSS and verify the grid rule is actually being applied. Grep for the exact class
  in BOTH places: `grep -n 'admin-wide' static/style.css templates/admin.html`.
- If the class names differ by a hyphen/word, fix by adding the HTML's class to
  the CSS selector: `.admin-card-wide,.admin-wide{grid-column:1/-1;overflow-x:auto}`
  (keep the old name for back-compat).
- **Diagnose with a headless browser + bounding-box measurement, not eyeballing.**
  Playwright (`pip install playwright; python -m playwright install chromium`) can
  run the served page with the real admin cookies and report element rects. The
  smoking-gun output: the grid `gridTemplateColumns` shows TWO equal columns and a
  card's `getBoundingClientRect().width` is ~half the container (559px of 1240)
  instead of full — that proves the full-width class isn't applying. Also check
  whether the JS tab-hiding (`display:none` on inactive `data-ttab` sections) is
  working; if a sibling card is `display:block` beside the active one, that's the
  "right side panel."
- To run Playwright against a Starlette app that has heavy imports (stripe, etc.):
  install only `playwright starlette jinja2 httpx` into a throwaway venv, then run
  with `PYTHONPATH` including the SYSTEM site-packages so the project's deps resolve:
  `PYTHONPATH="<sys site-packages>" python3 shot.py`. Set the admin/fan cookies via
  `context.add_cookies([...])` using a real session token from `db.create_admin_session`.
- Full working measurement script pattern: `references/headless-layout-measure.md`.

### CSS `display:flex` Overrides the `hidden` Attribute (modal "won't close")
Symptom (reported as \"DM pitch just opens in admin and won't close\"): a modal
overlay uses the `hidden` HTML attribute to open/close, but it stays visible no
matter what the JS sets. Root cause: an author-stylesheet rule like
`.promo-overlay { display:flex; ... }` **overrides the browser's user-agent
`[hidden] { display:none }`** — in CSS precedence, a `display:flex` declaration
beats the built-in hidden rule, so `overlay.hidden = true` is set but the element
never disappears. This is the SAME class of bug as the \"cut off\" pitfall above:
a CSS precedence/selector-matching problem, not a JS problem.
- Fix with an explicit author rule that forces hidden to win:
  `.promo-overlay[hidden]{display:none !important}`.
- Don't chase the JS (closing logic was correct); grep the overlay's CSS class
  and look for a `display:` declaration that would beat default hidden.
- After the CSS-only change, cache-bump the stylesheet (`style.css?v=N`) and
  hard-refresh the browser — no server restart needed for a static file.
- Check whether other overlays share the class; if only one modal uses it, the
  fix is scoped and nothing else is at risk.

### Starlette sync TestClient Portal-Contention CancelledError (suite-level flake)
Opening a SECOND `starlette.testclient.TestClient` on the SAME session-scoped
`app` object (one is still open, or many TestClients share one app) can fail with
`concurrent.futures._base.CancelledError` at `with TestClient(app):` — at
startup (`portal.call(self.wait_startup)`), not in your logic. It is
deterministic in-suite but passes standalone, which makes it look like a real
app bug. The trigger is portal/event-loop contention between sync TestClients
reusing one app (exacerbated by the module-level session `client` fixture being
open on the same app).
- Confirm by running the failing test ALONE: it passes ⇒ it's portal contention,
  not app logic.
- Fix: CONSOLIDATE the competing route tests into a single `with TestClient(app)`
  block (do the multiple DB-setup + HTTP assertions in one client session)
  instead of spawning a second TestClient on the same app. Fewer clients = no
  contention. This also fixes ordering-dependent flakes.
- Robustness note for AI-output parsing tests: always restore monkeypatched
  module fns (`_chat_raw`, `_parse_json_object`) in a `finally`, or later tests
  inherit the stub and fail for the wrong reason.

### Release-Pitch Panel (compose once → subscribers + curators)
When LO wants to "send the release pitch to everyone" the realistic, working
version is EMAIL (not auto-posting to Spotify/IG/TikTok — those need per-platform
API app approvals the site doesn't have). Build one compose form that sends to BOTH
audiences through the same sender:
- Form: release `<select>`, platform `<select>`/checkboxes (which platforms it's on
  → curators filtered by those), audience checkboxes (`send_subscribers`,
  `send_curators`), subject + body textareas (leave body blank to auto-generate),
  and a `dry_run` checkbox (default ON so nothing sends by accident).
- Subscribers get the SAME subject/body verbatim; curators get a PERSONALIZED
  `compose_pitch()` per curator (name/platform-specific template). Handle `db.all_curators`
  accepting a LIST of platforms (not just one string) — add a `platform IN (...)` branch.
- Log every send/queue via `db.log_email(platform, email, subject, status, error)`
  and show a recent-email-log table. Always preview first (`admin_pitch_preview`
  returns counts + a sample subject/body), then send on explicit confirm.
- Email MUST be via the Gmail-API OAuth (see acpeso-site.md), never SMTP app password.

### Google Cloud Gmail-API — the ONLY sender; banner can lie
LO sends email via Google Cloud Console Gmail-API OAuth only (his single Gmail App
Password is held by iCloud, so the smtplib/App-Password path is blocked forever).
SMTP settings in the admin panel are legacy and should be REMOVED, not shown.
Two gotchas that cost real time:
- **The startup banner lies.** A banner that prints "Email: Gmail-API LIVE" based on
  `gmail_enabled()` only checks client_id+secret+refresh_token are non-empty — but a
  placeholder `gc_refresh_token` of `"\""` (2 chars, from a half-completed save) makes
  it pass while real sends 400 `invalid_request Missing required parameter:
  refresh_token`. ALWAYS verify with a real send or by checking
  `len(db.get_setting('gc_refresh_token')) > 50` before believing sending works.
- **The one-time consent is a browser step only the owner can do.** You cannot mint
  the refresh token on LO's behalf. Generate the Google authorize URL
  (`accounts.google.com/o/oauth2/v2/auth?...response_type=code&scope=gmail.send&
  access_type=offline&prompt=consent`) with the live `gc_redirect_uri`, hand it to him,
  and he clicks Allow → the site's `/gc-callback` stores the token. "Access blocked /
  not verified" = consent screen still in Testing → set In production or add the owner
  as a Test user.

### OAuth-Gated Download Flow (mock-first) + Starlette TestClient redirects
When building a droploud-style "download gate" (fan must like/repost/comment on
SoundCloud via OAuth before a download unlocks) or any external-OAuth-gated web
flow, build the ENTIRE flow against a mock client so it verifies offline, then
flip to real mode when credentials exist. Two critical pitfalls:
- **Starlette TestClient follows redirects by default** — an auth guard that
  returns 303 will show as 200 in tests (followed login page). Use
  `TestClient(app, follow_redirects=False)` to assert redirects.
- Use a plain cookie token for admin auth instead of SessionMiddleware
  (avoids the `itsdangerous` dependency).
Full recipe, droploud gate model, SC OAuth URL shape, mock-first snippet, and
playlist-curator email-blast CRM in `references/oauth-gated-download-flow.md`.

### Real-mode OAuth gate MUST verify against the upstream API, not self-report
A mock `_MOCK_DONE` marker is fine for offline demos, but the user WILL reject a
gate that unlocks just because a button was clicked — "the gate doesn't actually
force people to like/comment". In LIVE mode, after performing the action with the
fan's OAuth token, QUERY the platform API (like/repost/comment state) and only
`mark_complete` when it confirms. Accept ANY comment text (don't match canned
text). Also: persist the PKCE verifier between /connect and /callback (a
hardcoded verifier breaks real exchange), and make `configure()` set the client
secret WITHOUT calling `force_mock` on the still-True initial flag (or it
re-mocks). Gate admin to the OWNER's platform account only; other logged-in fans
get a "Download history" page instead of an Admin button. And NEVER iframe the
SoundCloud authorize/track page into a modal — SC sends `X-Frame-Options: DENY`
so it renders blank; pop out to a new tab with `target="_blank"` and active-verify
instead (the "comment window doesn't work" bug). Detail + code:
`references/oauth-gated-download-flow.md`.

### Double-Encoded JSON Columns Break Boolean "all steps complete" Logic
When the SAME column is written by older code as a JSON string of a JSON string
(e.g. `gate_requires` = `'"[\\"like\\", \\"repost\\"]"'`), `json.loads` returns a
STRING, not a list — so `all(x in completed for x in req)` scans characters and
never reaches `all_complete=True`. The gate looks broken even though each step
records fine. Fix with a robust decoder that repeatedly `json.loads` until it
hits a list (cap iterations to avoid loops):
```python
def parse_requires(x):
    if isinstance(x, list): return x
    if not x: return ["like","repost","comment"]
    for _ in range(4):
        if isinstance(x, str):
            x = x.strip()
            if x.startswith("[") or x.startswith('"'):
                try: x = json.loads(x)
                except Exception: break
            else: break
        else: break
    return x if isinstance(x, list) else ["like","repost","comment"]
```
Use it everywhere the column is read (gate-step build AND the all-complete
check), not just one spot.

### Raw-SQL Placeholder/Binding Count + UPDATE-WHERE Key
After adding columns to a hand-written UPDATE/INSERT, `sqlite3` fails with
`ProgrammingError: Incorrect number of bindings supplied. The current statement
uses N, and there are M supplied.` Count `?` placeholders on BOTH sides. Two
easy traps:
- Adding columns means adding bindings too — mismatch by the new column count.
- A latent bug where the UPDATE path never passes the WHERE key (e.g. `...,
  now))` with `WHERE id=?` and no `rid`) means every update silently errors with
  17/18 — it only shows once you exercise the UPDATE path (INSERT worked all
  along). Always append `rid` for the WHERE clause.
The fastest fix is to rewrite the function cleanly rather than patch around it.

### Stale Server Holds the Port → New Routes 404
After a big router change, if new routes (e.g. `/beatpacks`, `/login`) return
404 while old ones work, you are almost certainly talking to a PREVIOUS server
process still bound to the port — the new process failed to bind and exited, and
the old one keeps answering. This is silent (the new process may log nothing to
your handler). Verify you're on new code by hitting a route that exists ONLY in
the new build, and free the port with `fuser -k PORT/tcp` (NOT `pkill -f` which
self-kills your own shell pattern), then restart.

### Starlette 404 Handler Returns HTTP 200 (silently succeeds on removed routes)
The classic `app.add_exception_handler(404, not_found)` where
`not_found` just does `return _render("404.html", ...)` produces **HTTP 200**
because `HTMLResponse(...)` defaults to status 200. Consequence: ANY unmatched
route (including a deliberately-removed route like `/api/seed` that should be
gone) returns 200 with the 404 page body — so a test asserting
`client.post("/api/seed").status_code == 404` fails, and you think the route
still exists. Always pass the status:
```python
async def not_found(request, exc=None):
    return HTMLResponse(jinja_env.get_template("404.html").render(ctx), status_code=404)
```
When verifying a route was truly removed, assert status 404 AND that the body
is the 404 page (the template route vs. a legacy handler that still 200s).

### REAL SITE — NEVER seed fake orders / payments / subscribers (LO rule)
For a site LO is launching for real ("it's a real site"), he WILL reject any
demo data that masquerades as real activity: fake "paid" orders, fake
subscribers, placeholder products with fake covers, seeded playlist-curator
rosters with `@example.com` emails. Rules that emerged:
- **Purge seed data AND the seeder**: delete the demo rows from the DB and
  remove the seeding route/script entirely (e.g. `/api/seed`, `seed_*.py`) so
  nothing re-injects on restart. A removed route that returns 200 via the
  broken 404 handler (see above) looks alive — fix the 404 handler first.
- **Test fixtures ≠ real data**: tests may create mock releases/packs, but they
  must live in an isolated throwaway DB (`ACPE_DB` env override), never the real
  DB. A `seeded` pytest fixture should `upsert` directly into the test DB, not
  call a seed endpoint.
- **Keep is hard, delete is easy**: when unsure whether a row is real (e.g. a
  real-looking subscriber email), keep it and note it; only delete obvious
  placeholders (`@example.com`, `a@b.com`, `artworks-0000000004` fake covers).
Full Stripe recipe in `references/stripe-checkout-and-real-data.md`.

### Real Stripe Checkout — never mark an order "paid" yourself
To sell real products (beatpacks) for real money, use Stripe's hosted Checkout
Session and let STRIPE confirm payment; the server must never flip an order to
`paid` on its own. Pattern that held up:
- POST checkout → create the order `status='pending'` + `stripe_session_id`,
  call `stripe.checkout.Session.create(mode='payment', line_items=[{price_data
  {currency, unit_amount(cents)}, ...}], success_url=..., cancel_url=...)`, and
  return `checkout_url` for the frontend to redirect to (frontend: if
  `json.checkout_url` redirect there; if `json.download_url` (free pack) go
  straight to download).
- **Free (price=0) packs bypass Stripe** and download directly — that's
  genuinely free, not a fake payment, and should STILL work.
- Confirm payment two ways: (a) a `/stripe/webhook` endpoint that
  `Webhook.construct_event(payload, sig, whsec)` on `checkout.session.completed`
  then marks paid; (b) on the return redirect (`success_url?...={CHECKOUT_
  SESSION_ID}`), `Session.retrieve(session_id)` and if `payment_status=='paid'`
  mark paid. Both store the `stripe_session_id`/`payment_intent` on the order.
- **If Stripe isn't configured** (no `sk_` secret), return a clean 400
  "Payments aren't connected yet" instead of faking a sale. Regression-test this
  (`test_no_fake_stripe_orders_when_not_configured`) plus the free-pack path.
- Store the secret/publishable/webhook keys in admin settings; pip-install
  `stripe` with `--break-system-packages` on an externally-managed (PEP 668)
  system Python that the service runs as.
- Config keys belong in a small `stripepay.py` helper (`enabled`/`configure`/
  `cents`) so checkout code stays readable.

### Auto-sync a catalog by upstream title tag (e.g. "[FREE FOR PROFIT] tab")
To pull the owner's SoundCloud tracks that carry a licensing/type tag in their
title into a dedicated site section: add `sc.user_tracks(token)` → `GET
/me/tracks?limit=200` (mock mode returns `[]` so tests don't fabricate a
catalog), filter with `"free for profit" in (title or '').lower()`, upsert each
as a release keyed by `soundcloud_track_id` (keep uploaded lossless files on
update). The admin-only sync endpoint uses the OWNER fan's stored `sc_access_token`
(found via `admin_sc_username`), and returns counts `{scanned, free_for_profit,
added, updated}`. Expose it as an admin button, not an unauthenticated seed.
Operational map of the canonical instance (AC PE$0: routes, admin access,
artist social handles, data-model notes, status file) lives in
`references/acpeso-site.md`.

### Paths Containing `$` Break Inline `cd`
LO's project dir contains a literal `$0` (`~/Desktop/ac pe$0`). In bash,
`cd "/home/.../ac pe$0"` expands `$0` to the shell name (`.../usr/bin/bash`), so
every inline `cd $dir && python3 -c ...` fails with "No such file or directory".
Quoting does NOT fix it. Two reliable workarounds:
- Write a small helper `.py` that sets `sys.path.insert(0, "<abs path>")`
  itself, and run it WITHOUT `cd` — the script never touches a shell-visible `$`.
- Or single-quote the path in shell (`cd '/home/.../ac pe$0'`), which prevents
  expansion. Prefer the helper-script approach when running python anyway.
This bites repeatedly in verification commands; don't burn turns re-diagnosing it.

### Starlette Multipart File Upload (UploadFile in request.form)
Starlette's `await request.form()` parses BOTH urlencoded and multipart bodies. A
file input arrives as an `UploadFile` object (has `.filename`, is awaitable):
```python
form = await request.form()
up = form.get("lossless_file")            # UploadFile when a file was sent
if up is not None and hasattr(up, "filename") and up.filename:
    raw = await up.read()                 # bytes
    ext = Path(up.filename).suffix.lower() or ".wav"
    local.write_bytes(raw)
```
Two gotchas:
- The `<form>` MUST have `enctype="multipart/form-data"` or `request.form()`
  returns only text fields and the file silently drops (`.get()` returns None).
- One route can carry BOTH the CRUD fields and the optional file — no separate
  "upload" route needed. Put the file field on the same form that creates/updates
  the record and handle it inline.
Also: text fields arrive as plain strings and checkboxes as `"1"`/absent; call
`form.getlist("name")` for multi-checkboxes (e.g. `gate_requires`).

### Admin Entity Form Design — managed dropdowns, auto-slugs, file-upload covers, locked fields
When the admin CRUD form for a product/entity (e.g. beatpacks) tells you to simplify,
these four directives come up together and each has a concrete implementation:
- **Admin-curated value → managed dropdown, not free text.** If a field (genre,
  category, type) is a bounded set the ADMIN maintains, don't leave it a text input.
  Store the allowed values in a setting (`db.set_setting("beatpack_genres", [...])`),
  render a `<select>` from it, and give the admin two tiny POST routes (add-by-name,
  delete-by-name) feeding chips that read the SAME setting as the select. The select
  preselects the current value when editing. Seed sensible defaults, let LO add/remove.
- **Drop the slug field — auto-generate + preserve on edit.** Never expose slug to the
  user. `db.upsert_beatpack` already does `data.get("slug") or secrets.token_hex(4)`.
  CRITICAL: on EDIT the route must set `slug = existing.get("slug") or ""` in the
  payload, or every save mints a NEW random slug and the public URL changes under the
  user. Auto-gen on insert, freeze on update.
- **Lock fixed / redundant fields in the DB layer, delete the input.** If currency is
  USD-only, hardcode `"currency": "USD"` in the route payload and remove the input —
  never let the frontend send it. If a value already lives elsewhere (BPM is in the
  title), REMOVE the field: from the form, from the upsert UPDATE/INSERT column lists
  AND bindings (count `?` on both sides — mismatches throw ProgrammingError), and from
  the public template (an empty value just renders a blank tag). Removing it from the
  DB write layer but leaving the template reference shows a stale empty tag.
- **Cover/image = file upload, not URL text.** Replace `cover_url` text with
  `<input type="file" name="cover">` on the SAME multipart form as the record. On save,
  `raw = await cov.read()`; `ext = Path(cov.filename).suffix.lower()` whitelisted to
  `.png/.jpg/.jpeg/.gif/.webp`; write `storage/cover-<id><ext>`; set `cover_url` to a
  served relative path like `/media/cover-<id><ext>`. Serve via a route that sanitizes:
  `name = Path(path_params["name"]).name` and require a known prefix (`cover-`,
  `release-`) to block path traversal.
- **Test the whole flow through the admin.** Generate a tiny PNG bytes, log in,
  `POST /admin/beatpack-genre` (add a genre), then multipart `POST /admin/beatpack` with
  cover+zip files; assert currency locked to USD, `cover_url.startswith("/media/")`,
  genre in the managed list, and fetch the cover URL returns `image/*`. Use
  `TestClient(app, follow_redirects=False)` — otherwise the post-save 303 gets followed
  and you assert a 200 page instead of the redirect.

### `.env` as Single Source of Truth + Handoff Packaging
When LO wants to hand a project to another maker, produce a working `.env` that
the app ACTUALLY loads at boot (not just a doc), plus `.env.example` (redacted
template), README, `start.sh`, and `install-service.sh` (systemd user unit).
Two patterns that prevent the classic "credentials wrong in handoff" failure:
- **Generate `.env` programmatically FROM the DB settings** the user already
  entered in the admin panel (which are the authoritative values), not by
  hand-typing them — hand-typing truncates/mistypes secrets. A small script maps
  DB keys → env vars, writes the file, then re-reads it to verify lengths.
- **Sync env → DB at boot**: a tiny pure-stdlib loader parses `KEY=VALUE` lines
  (strip quotes + inline comments, skip blanks/`#`), and `apply(db, force=False)`
  writes non-empty env values into the settings table BEFORE the app reads them,
  so server.py / soundcloud.py / r2.py all share one source of truth. Real
  environment variables take precedence over the `.env` file.
Also write an `ADMIN_USER`/`ADMIN_PASSWORD` bootstrap so the admin account is
created on first boot. Full loader + generator in
`references/env-config-handoff.md`.

### Starlette Routes Capture Function Refs at Import — Monkeypatch Is a No-Op
`app.routes.extend([Route("/admin", admin_main), ...])` stores the ORIGINAL
function object at import time. If a test later does `server.admin_main = probe`
it has NO effect — the route still calls the old object, so you'll silently get
200/whatever the original returns and wonder why your probe never printed. To
assert route behavior, patch the function BEFORE the app is built, or drive the
real handler through the app (TestClient) instead of reassigning module attrs.
This is the same class as the "hit a new-only route to confirm fresh code"
pitfall above.

### Cloudflare R2 + Pure-Stdlib SigV4 (no boto3)
Connect to R2 (S3-compatible) with only stdlib using AWS SigV4 signing — no
boto3 needed. Two non-obvious things:
- **Credential field order** from a pasted blob: the R2 S3 **endpoint's
  subdomain IS the Cloudflare account id**; the 32-hex value is the Access Key
  ID; the 64-hex value is the Secret Key. Getting them in the wrong order yields
  `Authentication error` / `Invalid account identifier` from the CF API.
- Build SigV4 headers: canonical request made of method/path/query/host +
  `x-amz-content-sha256` + `x-amz-date`, sign with `HMAC-SHA256` keyed chain
  (`AWS4<secret>`→date→region→service→"aws4_request"). Region for R2 is `auto`.
- `PUT <endpoint>/<bucket>` with an empty body creates the bucket.
- If the CF management API says `error 10042 "Please enable R2 through the
  Cloudflare Dashboard."`, R2 isn't activated on the account — that's a dashboard
  click the USER must do, not a code or credential bug. Don't chase the code.
Config keys + a working SigV4 client are in `references/cloudflare-r2-stdlib.md`.

### Single-File Zero-Dep AI Dashboard (Hermes SSE Wrapper)
Pattern for building a complete AI chat dashboard in a single Python file using only stdlib, with SSE streaming from hermes subprocess, markdown rendering, file management, and AppImage packaging. Full recipe in `references/single-file-hermes-dashboard.md`. Covers SSE endpoint, hermes output parsing, nginx reverse proxy config, AppImage build, folder upload (with counter bug pitfall), code mode toggle with syntax highlighting, and live settings tab.

### File-Aware Chat + Auto-Project Pattern
When the user uploads files/folders, the chat must know about them. Implement a file sidebar showing uploaded files, click-to-attach context chips, and auto-project creation from folder uploads. Full recipe in `references/file-aware-chat-auto-project.md`. Covers sidebar CSS/HTML, file selection JS, auto-attaching file content to prompts via `/file_content` endpoint, and auto-project creation when filenames contain path separators.

### Provider List Hygiene
Never leave broken/non-working providers in the WORKING_PROVIDERS list. When the user says "fix providers," actually test each one via `hermes chat` and remove any that return errors. A provider returning "list index out of range" from hermes means either the API key is expired (401/403 at the API level) or hermes has an internal bug processing that provider's response format. In either case, remove it from the active fallback chain — a broken provider in the chain causes every request to waste time trying it before falling through. Only keep providers that return actual responses. The user expects the listed providers to work; stale entries erode trust faster than fewer entries.

Also note: hermes v0.15.2 has a bug where ALL non-OpenRouter providers return "Error: list index out of range" when API keys are invalid — instead of a clean error message. This masks the real problem (expired keys) behind a generic crash. When you see "list index out of range" for a provider, the API key is almost certainly dead. Don't waste time debugging hermes internals — just test the key directly with curl and remove the provider if the key is invalid.

### User Frustration Pattern
When a user says "just make it work" or uses strong language, they want the fix NOW, not diagnosis. Provide exact commands to run and exact values to enter. Do not iterate on explanation.

### Masterclass Quality Bar
When LO calls something "masterclass" or says it's "far from masterclass," he means: every tab/feature must do something real on first click. No static placeholder text. No "coming soon." No features that only work after configuration. Chat must stream, Files must accept uploads, Swarm must show live health, Settings must pull live metrics. An empty Settings tab with hardcoded strings is worse than no Settings tab — it signals "unfinished toy" and the user will conclude the entire app is broken. Build features fully or don't include them.

LO's specific complaints to avoid:
- "settings has nothing in it" → Every setting row must show a live value fetched from an API endpoint, not a hardcoded string
- "cant upload folders" → Folder upload must preserve directory structure, not flatten to basename
- "should chat just code when i ask it to" → Chat must have an inline code mode toggle; code generation must not require switching to a separate tab
- "this is FAR from masterclass" → Insufficient polish overall — the entire app is judged by its weakest tab

### Folder Upload Pitfall
When implementing drag-and-drop folder upload, do NOT use `webkitGetAsEntry()` with a counter that includes directories. The `total` counter includes directory entries but `allFiles` only gets file entries, so `allFiles.length === total` never matches for folders with subdirectories — the upload silently never fires. Use `e.dataTransfer.files` directly instead; modern browsers already populate it with all files from dropped folders and `webkitRelativePath` is set correctly.

### Path Flattening on Folder Upload
When uploading folders, the multipart filename contains the full relative path (e.g. `"myproject/src/main.py"`). Using `os.path.basename()` strips the directory structure, causing files with the same name from different subdirectories to overwrite each other. Preserve the relative path for folder uploads (`if '/' in raw_name: fname = raw_name`) but use basename for single-file uploads. Create subdirectories via `os.makedirs(os.path.dirname(fpath), exist_ok=True)`.

### Port Hogging + Pycache Staleness
After patching a running Python HTTP server, the old process may still hold the port. `pkill -f` with a pattern matching your own command line will SELF-KILL the shell (exit -9). Use `fuser -k PORT/tcp` to reliably free the port by killing whatever holds it. After each patch, clear `__pycache__/` directories and restart with `PYTHONDONTWRITEBYTECODE=1` to prevent stale bytecode from being loaded. The sequence: `fuser -k PORT/tcp; sleep 1; rm -rf __pycache__/; PYTHONDONTWRITEBYTECODE=1 python3 server.py`.

**The silent "restart apparently did nothing" trap — plain `kill` can fail, and HTTP 200 lies.** A plain `kill <pid>` (default SIGTERM) may be ignored (process ignores/handles the signal, or you killed a wrapper and the real child persists), so the OLD process keeps the port. Your fresh `python3 server.py` then dies with `[Errno 98] address already in use` (exit code 3) and logs nothing you'll notice — while the old server keeps answering with OLD code. The user's symptom is "my change isn't live". Diagnose and verify correctly:
- **`ss -ltnp | grep PORT` is the source of truth for WHO owns the port and its PID** — not `pgrep -f`, which matches wrappers too. Before starting the new server, confirm the port is actually FREE (`ss -ltnp | grep 8533` returns nothing). If a stale pid still shows, `kill -9 <pid>` it explicitly and re-check.
- After starting the new process, confirm the PID that now owns the port is the NEW one (compare `ss -ltnp` pid to the pid you just launched), AND that the served content reflects the new change — retrieving HTTP 200 alone is NOT proof of new code, because the old process also returns 200 on the same routes.
- For static-file changes (HTML/JS/CSS) your text may still render even on old code if templates are read live from disk — so the ONLY reliable "is my code live" check is a route/feature string that exists ONLY in the new build (e.g. grep served HTML for the new tab name) or the freshly-launched PID owning the port.
- If you ran the new server via a background process wrapper (`terminal(background=true)`), check that wrapper's status: an `address already in use` bind failure shows as exit code 3 — that's the tell you're competing with a stale holder.

### Google OAuth Origin Mismatch
Error `origin_mismatch` means localhost isn't whitelisted in Google Cloud Console. Add:
- Authorized JavaScript origins: `http://localhost:8000` (and `https://localhost:8000` for FedCM)
- Authorized redirect URIs: `http://localhost:8000/login`

Google OAuth requires project verification for non-public domains. Changes take 5-60 minutes to propagate globally. For immediate localhost testing, add a "Dev Mode" button to the login page that bypasses auth and uses stored user settings.

### Voice/Email API Key Format Verification
**Vapi**: Key format `OQ...` is PUBLIC key (for client-side). Private key starts with `sk_live_...` for server-side calls. Using wrong key type returns "Invalid Key" or 403.

**Twilio Credential Format**: Requires BOTH pieces:
- Account SID (starts with `AC...` or API Key `SK...`)
- Auth Token/Secret (separate value)

Single "API key" field is insufficient - Twilio needs Basic Auth with both values. Add `voice-auth-token` input to Settings form. See `references/twilio-credentials.md`.

**Resend**: Key format `re_...` must have "send" permission. Restricted keys return "This API key is restricted to only send emails" (401).

### Stale Browser Cache
After JS/CSS changes, hard refresh (Ctrl+Shift+R) required. Toast z-index fixes may not appear without cache clear.

### Settings Lost During Refactor
When renaming projects (Masterchief → Demiurge Marketing), user settings JSON files can be orphaned. Always preserve `data/users/*.json` files.

### Partial Settings Form Wipes ALL Other Settings (the "settings just disappeared" bug)
A shared settings-save handler that writes EVERY key with a default is a landmine when
the admin is split into many small forms. Symptom: LO saves the "Daily briefing
recipient" form (which posts ONLY `owner_email`) and suddenly the R2/Stripe/SC/Gmail
settings all show blank — "all of my saved settings just disappeared."

- **Root cause:** `for k in (ALL_KEYS): db.set_setting(k, data.get(k, ""))`. Every
  form POSTs to the same `/admin/settings` route, but a small form only submits its
  own fields. `data.get(k, "")` returns `""` for every key the form didn't send, so
  ALL other settings get overwritten to empty. The site still works; it's silent
  data loss (nothing errored, so you don't notice until the fields render blank).
- **Fix — only write keys that are actually present in the submitted form:**
  ```python
  for k in (ALL_KEYS):
      if k in data:
          db.set_setting(k, data.get(k, ""))
  ```
  Handle checkboxes separately — only touch the checkbox flag when its form was the
  one being saved (`if "smtp_starttls" in data or "smtp_host" in data:`), otherwise
  an unrelated form save also flips it off.
- **Always add a regression test:** seed several unrelated settings, POST a small
  form (only one field, e.g. `owner_email`), assert the submitted value persisted AND
  the untouched settings are all still present (not `""`). This bug is invisible
  without that test because nothing raises.

### Large File Upload Behind a Tunnel/Reverse-Proxy → 502 → Chunk the Upload
When a site is served through a Cloudflare Tunnel (or any reverse proxy with a ~100s
request timeout and throttled upload bandwidth), a big single multipart POST (a
50–150MB WAV) reliably dies with **HTTP 502** — Cloudflare's edge times out before the
origin finishes reading the body. The clean fix that works through the tunnel from ANY
machine (remote admin included) is **client-side chunked upload**, not a bigger timeout:
- **Server**: three (or four) endpoints. `start` → creates a session dir + returns
  `session_id`; `{sid}/{idx}` → writes one small slice to `{idx:06d}` inside the
  temp dir; `finish` → reads all slices sorted by name, `b"".join`s them, writes the
  final file, and (optionally) R2-puts it; `abort` → `shutil.rmtree` the session dir.
  Keep the assemble tolerant: `sorted(p for p in session_dir.iterdir() if p.is_file())`.
- **Client**: `File.slice(i*CHUNK, min((i+1)*CHUNK, file.size))` per 4MB chunk, POST each
  as its own request with a short timeout, track overall % by `uploaded/total`, then POST
  `finish`. Each chunk easily completes before the proxy timeout, so a 100MB file over a
  slow tunnel finishes in many small hops instead of one that 502s.
- **STARLETTE STAR-PATH ROUTE-ORDERING PITFALL**: register the FIXED sub-paths BEFORE the
  generic star path, or the generic route shadows them. `Route("/admin/upload-chunk/{sid}/{idx}")`
  captures `/finish` and `/abort` if listed first → "bad index". Put
  `{sid}/finish` and `{sid}/abort` ABOVE `{sid}/{idx}` in `app.routes.extend([...])`.
- This is the durable answer to the recurring "upload over acpeso.shop 502s" — the
  alternative (direct-to-R2 presigned PUT) is nicer but needs R2 enabled on the account
  (a dashboard click — the CF API reports `10042 Please enable R2`). Chunked upload works
  with zero dashboard/config changes.

### Google Translate Widget — add it + kill the top ribbon it injects
To let visitors translate a public site, add Google's free TranslateElement to the shared
`base.html` so it's site-wide: a `<span id="google_translate_element">` in the nav, an
`includedLanguages` list (on-demand only, `autoDisplay:false` so English users aren't
forced), and load
`//translate.google.com/translate_a/element.js?cb=googleTranslateElementInit`. It's
client-side, free, keeps the real domain/URL, and only runs when a visitor chooses a
language — no backend, no API key.
**The pitfall users WILL report:** after translating, Google injects a full-width top
ribbon that pushes the whole page down ~40px and covers the header. A single
`.goog-te-banner-frame{display:none!important}` is NOT enough — Google's JS re-adds the
ribbon and sets `body{top:40px}` inline, overriding it. Use the full kill-set:
```css
html body{top:0!important;margin-top:0!important}
.goog-te-banner-frame,.goog-te-banner-frame.skiptranslate{display:none!important;visibility:hidden!important}
iframe.goog-te-banner-frame{height:0!important;overflow:hidden!important}
#goog-gt-tt,.goog-tooltip{display:none!important}   /* floating tooltip popup */
.goog-text-highlight{background:transparent!important;box-shadow:none!important}
```
This removes ONLY the blocking ribbon/tooltip; the in-nav dropdown still works. Pure
CSS → cache-bump the stylesheet and hard-refresh; no server restart.

### OAuth access tokens EXPIRE — auto-refresh before gate/API verify, or the gate "never works"
SoundCloud (and most OAuth providers) issue short-lived access tokens that 401 after a
while. Symptom: LO says "I commented/reposted/liked but NO gate unlocks" — every
`verify_step` real-API call returns a 401 → `False`, so the gate stays locked no matter
what he does on the platform. This is NOT a logic bug in the gate; it's a stale token.
Fix: in the token-resolution helper (`_fan_token`), in LIVE mode call
`sc.token_valid(token)` first and if it fails, exchange the stored `refresh_token`
(which is long-lived and rotating) for a fresh access token BEFORE returning it to the
verifier, then persist the new token (AND the new refresh token — the provider rotates
it on every use; not persisting the rotated refresh leaves the next refresh dead with
`invalid_grant`). Two warning signs from diagnosis:
- **Refresh tokens are single-use/rotating**: calling `refresh_access_token` purely to
  TEST consumes it and invalidates the stored one (`invalid_grant` on the next try).
  Don't burn them in diagnostics; either persist the rotated token or accept that the
  owner must do a one-time re-login to re-mint a fresh pair.
- Verify the minted token actually authenticates (`token_valid`) — an 800-char blob from
  a mock/fabricated path returns 401 and can't gate-verify. Real visitors who complete
  the SC OAuth login get a fresh valid pair, so their gates work; it's stale/rotated
  stored tokens that break.

### Blog/Content Media Renders Inline vs. Force-Download (image/video/audio)
When a content site (blog, releases) lets the owner upload arbitrary files, the
default serve typical is `Content-Disposition: attachment` — so an uploaded image or
video only ever offers a Download button and LO will ask "if it's an image or video
it should DISPLAY on the page, not just download." Two coordinated changes make
media render inline:
- **Server:** choose `inline` vs `attachment` by MIME type, not by route. If the
  resolved media_type starts with `image/`, `video/`, or `audio/`, send
  `Content-Disposition: inline` (browsers can't render a file told to download);
  everything else (zip/pdf/etc.) stays `attachment`.
  ```python
  cd = "inline" if med.startswith(("image/", "video/", "audio/")) else "attachment"
  headers={"Content-Disposition": f'{cd}; filename="{disp}"'}
  ```
- **Template:** key off the file extension and emit `<img>`, `<video controls>`, or
  `<audio controls>` (with `preload="metadata"`) above the existing Download link.
  Unknown/archive types keep only the download link.
- Verify live by checking the served `Content-Disposition` header AND that the page
  contains the inline `<img class=...>` — fetch the actual page and grep, don't trust
  a bare HTTP 200.

### Testing External Dependencies
When testing modules that interact with external services like Google Calendar, Fonoster, or Odoo:
1. Don't import modules with unavailable dependencies directly in test files
2. Extract core functionality into pure functions that can be tested independently
3. Use dependency injection or mocking to simulate external services
4. Create test doubles that mimic the behavior of external dependencies
5. Handle missing dependencies gracefully with clear error messages

### Environment Variable Persistence
When implementing admin settings with environment variable persistence:
1. Always persist to both localStorage (for immediate UI feedback) and backend .env files (for server persistence)
2. Handle special characters in environment variables properly (quote values with spaces, =, or #)
3. Update Config class dynamically at runtime for immediate effect
4. Test persistence with special characters and edge cases
5. Verify Config class updates propagate to all relevant modules

See `references/env-persistence-pattern.md` for implementation details.