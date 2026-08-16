# Admin Panel: Tab Organization + AI "Full Kit" Consolidation

Two patterns from the AC PE$0 admin (Starlette + Jinja2 admin at `/admin`, single
acpeso-SC-account admin auth, tabs driven by `data-ttab` sections + `data-tab` nav
anchors + a JS hash mapper in `static/app.js`).

## 1. Split a monolithic Settings page into grouped tabs

**Problem observed:** one "Settings" tab crammed 9 unrelated things (SC creds,
front-page text, follow-up window, briefing recipient, Gmail API, newsletter-send,
R2, Stripe, bookings) while a separate "Email Templates" tab existed that did NOT
include newsletter-send. Disorganized and the newsletter was buried.

**Fix — group tabs with visual separators, and route saves to the owning tab:**

- Tab bar = anchors with `data-tab`, separated into groups by a thin
  `<span class="tab-sep"></span>` divider (CSS: `.admin-tabs .tab-sep{width:1px;
  align-self:stretch;background:var(--accent-line);margin:2px 6px;min-height:20px}`).
  Logical groups read naturally: Content · Outreach · Comms · Data · Config.
- Each tab's HTML lives in `<section class="admin-card" id=X data-ttab="X">`.
- Every new tab MUST be added to the JS hash mapper `currentFromHash()` in
  `static/app.js` (e.g. `if (h === 'integrations') return 'integrations';`) or
  deep-linking/initial-tab breaks. Also add it to the special-case
  `if (name === 'releases' || ... )` return in `activateTab`.
- **Route saves to the owning tab server-side:** the one `/admin/settings` POST
  handler collects every key regardless of which form sent it. After saving,
  detect which form via a sentinel key set and redirect to the correct tab:
  ```python
  integ_keys = ("sc_client_id","smtp_host","r2_account_id","gc_client_id","stripe_secret_key")
  if any(data.get(k) is not None for k in integ_keys):
      return RedirectResponse("/admin#integrations", status_code=303)
  return RedirectResponse("/admin#settings", status_code=303)
  ```
- **Pitfall — moving big HTML blocks by substring slicing mangles the markup.**
  When reordering blocks inside a `<section>`, splitting on heading substrings
  (e.g. `rfind('<hr class="settings-divider">')` or slicing between heading
  positions) separated `<h3 class="admin-subtitle">` opening tags from their text
  and left dangling `<hr>` lines. The structure stayed loaded but render was
  broken. **Rebuild the whole section/region from scratch** (verbatim block
  content) rather than surgically relocating it — far less error-prone than
  trying to repair mangled nesting.
- Bump both cache-bust versions in `templates/base.html`
  (`link` stylesheet `?v=` and `script src app.js?v=`) after any admin UI change;
  hard-refresh is otherwise required to see it.

## 2. Collapse N scattered AI-generator buttons into ONE "Full kit" action

**Problem observed:** four per-release buttons (Tag → genre/BPM/key/desc, Share
card → og_title/og_desc, Press kit → blurb+highlights, Promo kit → pitch/IG/TikTok/
blog/newsletter) each fired a separate AI call and dropped output into a different
scattered panel. Overlapping marketing copy + clutter.

**Fix — one route that runs ALL generators, one organized drawer:**

- One `POST /admin/ai-full-kit` route calls every generator, **auto-saves the
  persistent pieces** (tag fields, og_title/og_desc, press_blurb/press_highlights)
  via `db.update_release_fields`, and returns non-persistent (editable) promo copy
  separately. Isolate per-piece failures so one generator erroring doesn't kill the
  rest:
  ```python
  def _try(name, fn):
      try: return fn()
      except Exception as e: errors[name] = str(e); return None
  ```
  Return `{ok, slug, tag:{}, share:{}, press:{}, promo:{pitch,social,tiktok,blog,newsletter}, errors:{}}`.
- One JS handler `[data-ai-full-kit]` opens a single organized modal/drawer with
  clearly-labeled sections: Metadata (auto-saved) · Share card (auto-saved +
  open/copy link) · Press kit (auto-saved + open page + highlights) · Promo copy
  (editable + Copy per piece). Errors surface at the bottom of the drawer.
- Keep the always-visible artifact links (↗ Release, 📄 Press kit) in the row so
  the generated outputs are reachable even without re-generating.
- **Pitfall — define shared helpers (`escHtml`) exactly once.** Two identical
  `function escHtml` declarations in the same IIFE scope: later one wins, work
  identically, but duplicate definitions are confusing — delete the copy you add.

## 3. Make AI-generated messages editable before send/copy

The backend send route already accepts arbitrary `subject`/`body` — the gap was a
read-only preview render. Render the AI draft as **editable fields** (subject
`<input>`, message `<textarea>`), then have the copy/send handlers read the
**current on-screen values** (`getVal()` reading `[data-fn-subject]`/`[data-fn-body]`)
rather than the original AI response object. Result: tweak the draft, then
send/copy exactly what you see. This pairs with `send-in-place-pattern.md`
(honest dry-run + refusal rails when no email / no sender configured). When
moving an email-sender hint between tabs, keep the tab name in sync (a stale
"Settings" label outlived the reorg to "Integrations").

## 4. `table-layout:fixed` strangles the last column — give it real width

Symptom: `<table class="admin-table">` uses `table-layout:fixed`, so the last
"Action" column (with no width set) gets only leftover space. Once that cell holds
an embedded editor (reward-note subject+message textarea, a save-email form, Copy/Send
buttons), everything on the right clips/cuts off. Fix in CSS:
```css
#community .admin-table{min-width:820px}
#community .admin-table th:nth-child(8){width:40%}          /* give Action its share */
#community .admin-table td:nth-child(8){vertical-align:top;min-width:340px}
#community .admin-table td:nth-child(8) input[name="email"]{min-width:180px}
```
CSS-only change = no server restart needed (static file served from disk); just bump
the `?v=` cache-bust in `base.html` and hard-refresh. Verify the new rule is actually
served with `curl -s ".../static/style.css?v=N" | grep -c <selector>`.

## 5. Blog attachments: serve media INLINE so it displays, not just "Download"

Symptom: uploaded blog images/videos only ever produced a Download button and never
rendered on the post. Two causes: (a) the serving endpoint stamped
`Content-Disposition: attachment` on EVERYTHING — a browser can't render a file told to
download; (b) the template only had a download link. Fix:
- Server (`blog_file`-style handler): choose disposition by media type —
  ```python
  cd = "inline" if med.startswith(("image/","video/","audio/")) else "attachment"
  ```
  so `<img>/<video>/<audio>` can actually render them; zip/pdf/other stay downloads.
- Template: by file extension render `<img>` / `<video controls>` / `<audio controls>`
  above the still-present `Download {file_name}` link; unknown types keep just the link.
- Verify: `curl` the served file and assert `Content-Disposition: inline` + correct
  Content-Type; fetch the post page and assert the inline `<img>`/`<video>`/`<audio>` tag
  is present. Template+server change (no JS) — no cache-bust strictly required.

## 6. Rendering check: register the app's custom Jinja filters in any harness
When you verify a template by rendering it directly (not via the running server), the
app's custom filters (e.g. `datetime`, `filesizeformat`) are missing and Jinja throws
`No filter named 'datetime'` — a HARNESS miss, not a template bug. Register them first
(`env.filters['datetime'] = lambda ts: ...`) before asserting render output.

