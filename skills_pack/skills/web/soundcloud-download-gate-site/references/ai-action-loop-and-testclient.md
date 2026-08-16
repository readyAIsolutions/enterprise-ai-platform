# AI-action loop + Starlette sync-TestClient pitfall

Session-specific detail for the AC PE$0 / download-gate site (Starlette, session-scoped
`app` fixture tested via `starlette.testclient.TestClient`).

## 1. Starlette sync TestClient `CancelledError` (this bit us twice)

**Symptom:** a route test fails with:
```
concurrent.futures._base.CancelledError
    raise CancelledError()            # at portal.call(self.wait_startup)
```
It fails *consistently in the full suite* and *consistently even in isolation* for one
test, while an adjacent, near-identical test passes — and the same test passes when run
standalone from a fresh `python3` process.

**Root cause:** the test module declares a *session-scoped* `client` fixture (an open
`TestClient` on the same `app` object) while individual tests also open their own
`TestClient(app, ...)` with `from starlette.testclient import TestClient`. Starlette's
sync `TestClient` uses an anyio portal thread; a well-formed test that only *creates a
second* `TestClient` on the same app can collide with the portal/lifespan startup
(`wait_startup` gets cancelled). The failure surface is startup, not the body of the
request, so it looks like the app logic is broken when it isn't.

**Fix (reliable):** consolidate every route test that needs admin auth into ONE
`TestClient(app, follow_redirects=False)` session instead of opening a fresh TestClient
per test. Fold the "editing edge case" assertions (e.g. "skips rows without an email")
into the same test/session as the other auth checks rather than spawning a second client.

**Lesson for future suites:** when a Starlette test throws `CancelledError` at TestClient
creation, do NOT chase app logic — reduce the number of `TestClient` instances open on
the shared session-scoped app (see `test_site.py` section 9/10/11 for the consolidated
shape). This is a test-harness constraint, not an app bug.

## 2. "Close the loop" — every surfaced item gets a one-click AI action

The Command Center dashboard surfaces problems (stalled curator follow-up queue, releases
missing lossless files). The highest-value AI upgrade is not a new dashboard — it is
turning each surfaced item into a one-click action. Pattern used for the follow-up queue:

- `aiwriter.follow_up_nudge(curator_dict, release, settings)` returns `(subject, body)`.
  Deterministic fallback (always usable) computed FIRST; AI call wrapped in try/except;
  if AI reply body < 25 chars, return the fallback.
- Route `POST /admin/ai-followups` — auth-gated, NEVER sends; returns per-curator
  `{name, email, contact_url, subject, body}` and SKIPS rows with neither email nor
  contact URL (nothing reachable to send to).
- Dashboard button ("✍ AI draft follow-ups for all below") gathers the stale-curator ids
  from the rendered rows, POSTs, renders each nudge with a Copy button + `mailto:` link
  (subject/body pre-filled) for email curators or "Open profile ↗" for DM-only curators.
- The existing status dropdown lets the user mark "Followed up" to clear the queue —
  closing the loop.

Reusable rule: an AI-outreach feature on this site is a 4-piece kit —
**aiwriter f(x) with fallback → auth-gated read-only route → admin button+JS → tests with
`_chat_raw`/`_strip_reasoning` monkeypatched (both AI-down and AI-parse cases)**.

## 2b. The kit generalizes to a whole AI-feature family (not just outreach)

The same 4-piece kit has been applied ~6 times on this site, each time landing as a
fully-flushed, tested feature in a single push. Confirmed variants and their outputs:

| Feature | aiwriter f(x) returns | Parsing | Persists to DB? | Public page? |
|---|---|---|---|---|
| Per-curator pitch | `(subject, body)` | SUBJECT:/header | no (send-time) | no |
| Follow-up nudge | `(subject, body)` | SUBJECT:/header | no | no |
| Press kit one-sheet | `{blurb, highlights:[3]}` | JSON object (`_parse_json_object`) | yes (`press_blurb`, `press_highlights` cols) | yes `GET /press/{slug}` |
| Fan reward note | `(subject, body)` | SUBJECT:/header | no | no (Community tab) |
| SEO share card | `{og_title, og_desc}` | JSON object | yes (`og_title`, `og_desc`) | via base.html OG block |
| DM pitch (no-email curator) | body-only string (NO `SUBJECT:`) | plain text, gate on `len ≥ 40` | no | no (DM modal) |

Two distinct AI-output shapes on this site — parse for whichever the feature expects:
1. **Header shape (`SUBJECT:\n\n<body>`)** → normalize escaped newlines, grab subject
   off its own line, gate on `len(body) < 25`.
2. **JSON-object shape (`{"blurb": ..., "highlights": [...]}`)** → `_parse_json_object`
   (extracts the LAST balanced `{...}` and `json.loads` it). Validate shape (blurb +
   non-empty highlights list) before trusting it, else fall back.

Fallback rule that keeps every one of these crash-proof: **compute the deterministic
template/stats-derived fallback FIRST, try the AI in try/except, and only return the AI
result if it parses AND clears a length gate.** The button always returns something
usable even with the router down. Never fabricate facts — build fallbacks from the
release/curator's own real data.

## 2b1. DM pitch — a body-only shape + "see AND edit it" UX

The **DM pitch** (for curators with NO email, only a profile/contact link) is a third
AI-output shape the family table above needed:

- **Output = body only, NO `SUBJECT:` header.** `aiwriter.dm_pitch_ai(curator, release,
  settings)` returns a single string (50-90 word DM). Normalize escaped newlines, strip
  any `<<< ... >>>` reasoning aside, and gate on `len < 40` → fallback.
- **Fallback = `curator.dm_pitch(...)`** (the template), computed FIRST — so the "AI
  draft" button ALWAYS fills an editable message even with the router down.
- **Route:** `GET /admin/ai-dm-pitch?curator_id=&release_id=` (auth-gated, NEVER sends)
  → `{ok, message, contact_url}`.
- **UX rule — LO explicitly asked "dm pitch ... need to see the pitch and edit it":**
  the button must fill a REAL editable `<textarea>` (never a read-only preview, never a
  one-click send). LO reviews + edits, then Copy and pastes it into the curator's own
  profile/contact form himself. So: AI draft button fills an editable textarea + a
  pre-filled "Open their profile/contact ↗" link + a Copy button; the template text stays
  available as a type-in/fallback option. This is the DM-side counterpart of the email
  "✎ AI-personalize each selected curator" flow — both end at an editable textbox the
  owner is in control of before anything leaves the site.
- Test all three: route 401 without admin; authenticated route returns `ok` + a
  draftable message; AI-down → fallback still returns a usable, on-brand message.

## 2c. Adding a new admin tab (reusable pattern)

The admin panel's tab nav is generic (`data-tab` links + `data-ttab` sections in
`admin.html`, driven by `currentFromHash()` in `app.js`). Adding a tab is mechanical:
1. Add `<a href="#x" data-tab="x">` to the `[data-admin-tabs]` nav; add `class="active"`
   when `tab=='x'` if a server `?tab=` param should preselect it.
2. Add `<section id="x" data-ttab="x">` anywhere in the grid (it needs data in the
   `admin_main` context — pass it in `_ctx_base(...)` in `server.py`).
3. Add an `if (h === 'x') return 'x';` line in `currentFromHash()` so a lobby/refresh
   lands on it.
4. Any new buttons inside use the existing `document.querySelectorAll('[data-...]')`
   delegation — no nav plumbing needed beyond the hash line.
5. Bump the static cache-busters when you touch JS/CSS: `base.html` has
   `/static/app.js?v=N` and `/static/style.css?v=N` — always increment, and grow it past
   any version the sibling agent noted so stale assets don't persist.

## 2d. TestClient pitfall applies to EVERY new route test here

For each new feature the routes must be tested with admin auth. Do NOT open a fresh
`TestClient` per feature test — reuse ONE session-scoped `TestClient` and fold multiple
feature assertions into it (the `CancelledError` trap in §1). The consolidated shape in
`tests/test_site.py` is the model.

## 3. Emitting-decoder parsing (already in skill, keep consistent)

When the router model echoes `\n` as literal two-char `\n` (escaped newlines), normalize
BEFORE splitting subject/body:
```python
text = text.replace("\\r\\n","\n").replace("\\n","\n").replace("\r\n","\n").replace("\r","\n")
m = re.search(r"SUBJECT:\s*(.+)", text, re.I)
subject = m.group(1).strip().split("\n")[0][:110] if m else fallback_subj
body = text[m.end():].lstrip("\n").strip() if m else text.strip()
```
Always gate on `len(body) < 25` (or 40) → fallback, because the model will sometimes
emit the header and nothing else.

## 4. Testing AI functions with monkeypatched router

Never call the real network in tests. Patch:
- `aiwriter._chat_raw` → return a canned `"SUBJECT: ...\n\n<body>"` for the parse path.
- `aiwriter._chat_raw` → raise `ConnectionError` for the fallback path.
- Restore the real functions in a `finally:` block (a stub left in place poisons the next
  test in the module — this happened and was fixed).

## 5. User-generated content moderation (owner-delete / admin-delete-all)

A flat "anyone can delete" comment endpoint is wrong. The correct, durable permission
model (implemented as `POST /api/item-comment/delete`, single route):

1. **db:** `get_comment(comment_id)` + `delete_comment(comment_id)` — never delete by a
   caller-supplied WHERE; look the row up first so you can enforce ownership.
2. **Route logic (server-enforced, not just UI-hidden):**
   ```
   comment = db.get_comment(cid)          # 404 if missing
   fan = _fan_from_cookie(request); admin = bool(_need_admin(request))
   if admin: delete → {ok, deleted_by:"admin"}
   elif fan and fan.id == comment.fan_id: delete → {ok, deleted_by:"owner"}
   else: 403                              # not the owner, not admin
   ```
   Tests must cover all four: owner 200, stranger 403, admin-deletes-any 200, anonymous 403,
   plus unknown-id 404 and missing-id 400.
3. **UI:** render a small delete (✕) button on each row **only when** the viewer is that
   row's owner **or** an admin — in the template it's
   `{% if is_admin or (fan and fan.id == co.fan_id) %}<button ...>✕</button>{% endif %}`.
   Wire once with a delegated `bindCommentDelete(root)` handler (guard with a `__delBound`
   flag so re-binding on JS-injected rows doesn't double-fire), confirm(), POST, remove
   the row. Newly JS-injected rows get a delete button too (empty id → early-return).

Reusable rule: for any UGC delete feature, **serve-enforce ownership/admin (403/404), then
hide the affordance in the template for non-authorized viewers.** The button being absent
is a UX nicety; the route enforcing it is the actual guarantee.

## 6. Every generated artifact MUST be directly openable from the panel (user rule)

LO's explicit, durable expectation (he was frustrated when he had to hunt for output):
**"should be able to access press kit / share card / anything you added directly from
the admin panel — no just making files and expecting them to find them."**

So every AI-generated thing must expose an inline, clickable result IN THE PANEL after
generation, plus an always-visible direct link:
- Always-visible per-release links in the release row: `↗ Release` and `📄 Press kit`
  (open `/release/{slug}` and `/press/{slug}` in a new tab).
- After clicking ⚡ Share card: render an inline `.seo-card` preview (title + desc) with
  **Open ↗** + **Copy link** buttons alongside the button/msg span.
- After clicking ⚡ Press kit: render an inline "Press kit ready" card with **Open press
  kit ↗** + **Copy link**.
- Make the AI routes return `slug` (e.g. `{ok, slug, fields}`) so the JS can build the
  exact share/open URL instead of guessing. Verify the served HTML actually contains the
  new links after deploying (templates re-read per request; server-code changes need a
  restart; static JS/CSS only need a cache-bump in `base.html`).

Reusable rule: **generate → show the result in place with an open link + copy button.
Never "generate and leave it on disk for them to find."** Fold this in at build time; it
is a reported usability complaint this user has made before and will make again.

## 6a. CSS `hidden` attribute vs `display:flex` overlay bug

A modal that opens with `element.hidden = false` and closes with `element.hidden = true`
silently fails to close if its CSS sets `display:flex` (e.g. `.promo-overlay {
display:flex; ... }`). Author `display:flex` overrides the UA stylesheet's
`[hidden]{display:none}`, so the element stays visible even though `hidden` is set.

Fix: add an explicit higher-priority rule — `.promo-overlay[hidden]{display:none !important}`.
The `!important` makes hiding always win. The underlying JS was never broken; it was pure
CSS precedence. This is served from static disk, so no server restart is needed — just
bump `style.css?v=N` in `base.html` and hard-refresh.

## 7. Testing fan-engagement leaderboards

When ranking fans by activity, aggregate REAL actions (favorites/comments/downloads/gate
completions), never synthesize. Score weights intentional actions heaviest (e.g.
favorites×2 + comments×3 + downloads×4 + gates×2). Test the ranking with two fans (one
active, one idle) and assert both the score and the sort order. `db.upsert_fan(...)`
returns the fan **id string**, not a dict — don't do `fan["id"]` on its return.
