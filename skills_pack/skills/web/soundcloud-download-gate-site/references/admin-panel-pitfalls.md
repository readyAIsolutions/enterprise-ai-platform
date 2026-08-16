# Admin-panel pitfalls & patterns (Starlette + Jinja single-page admin)

Durable lessons from operating the AC PE$0 single-page admin (one `/admin`
page, tab-switched sections via `data-ttab`, Starlette backend, SQLite).

## 1. Partial settings forms MUST NOT wipe other settings
**Symptom:** saving one small settings form (e.g. the Daily-Briefing recipient,
which posts only `owner_email`) erased every other saved setting (SC creds,
Stripe, R2, Gmail, etc.) so they showed blank.

**Root cause:** the handler iterated its full key list and ran
`db.set_setting(k, data.get(k, ""))` for EVERY key — so any key the form did
not submit got written as `""`.

**Fix (adopt unconditionally):** only write keys actually present in the form:
```python
for k in (KEY1, KEY2, ...):
    if k in data:
        db.set_setting(k, data.get(k, ""))
```
Checkboxes follow the same rule — only touch `smtp_starttls` when its form
submitted it. Always add a regression test that seeds several unrelated
settings, POSTs a one-field form, and asserts the others are unchanged.

## 2. Admin tab links need the `#hash`, not just `?tab=`
**Symptom:** "Edit button does nothing."
**Root cause:** tab-switching JS keys off `location.hash`
(`currentFromHash()` returns Dashboard when the hash is empty). A link like
`/admin?tab=curators&cedit=ID` has no `#curators`, so the JS force-shows
the Dashboard and hides the curators section — the edit form loads server-side
but is invisible.
**Fix:** every tab link that must land on a section must include the hash in
ORDER that survives `?query#hash` (params BEFORE the hash):
`/admin?tab=curators&cedit=ID#curators`.
Keep `currentFromHash()`'s mapping in sync whenever you add a tab
(used: dashboard, releases, curators, settings, integrations, analytics,
emails, community, beatpacks, blog).

## 3. Group tabs with dividers; split oversized tabs
A "Settings" tab that crammed 9 unrelated forms (creds, site copy, email send,
R2, Stripe, bookings) is unmanageable. Split into logical tabs and add
`.tab-sep` divider spans in the nav, with a distinct active color for the
config tab (e.g. Integrations in blue). Route each form's redirect back to the
tab that owns it (detect which form by checking which submitted keys are
present).

## 4. Collapse overlapping AI "generate" buttons into one action
Four per-release buttons (Tag / Share card / Press kit / Promo kit) produced
scattered, overlapping marketing output. Consolidate into ONE endpoint (e.g.
`/admin/ai-full-kit`) that runs all generators, AUTO-SAVES the persistent
pieces (genre/BPM/key, og_title/og_desc, press_blurb/highlights), and opens ONE
organized drawer with labeled sections. Isolate per-piece errors so one failing
generator doesn't kill the rest (`errors` dict, return partial success).

## 5. Editable AI drafts before send/copy
AI-generated text shown as `readonly`/plain text can't be reviewed. Render
subject + body as editable inputs, read the CURRENT on-screen value on
Copy/Send (`getVal()`), and send exactly what the user sees.

## 6. Inline media needs `Content-Disposition: inline`
A file-serving endpoint that always sends `attachment` prevents `<img>`/
`<video>`/`<audio>` from rendering. For image/*, video/*, audio/* MIME types,
serve `inline` (keep zip/pdf as `attachment`), then in the template render an
inline `<img>`/`<video controls>`/`<audio controls>` based on file extension
above the download link. (Example: `/blog-file/{name}`.)

## 7. Fixed-layout tables blow up the last column
`table-layout:fixed` gives the width defined per column; an un-sized last
"Actions" column gets the scraps and clips editors (reward-note box, save-email
form). Give the heavy column an explicit width %, a `min-width`, top-align its
cells, and set `overflow-x:auto` + `min-width:min-content` on wide grids so
they scroll instead of clipping.

## 8. Pulling real contact emails (never fabricate)
- Newsletter signup emails live in the `subscribers` table — surface them in
  the admin Community tab (they are email addresses the visitor actually gave).
- To pull a curator's email from their profile page: fetch the page, prefer a
  `mailto:` match, else regex-scan; FILTER noise (noreply / no-reply /
  donotreply / example. / @test. / sndcdn / soundcloud.com$). Save only real
  results; honestly report "no public email" when none exists. Famous SC/Apple
  pages usually expose no public email — that is the correct answer, not a bug.
- SoundCloud follower emails are NOT exposed via the API — you can't scrape
  fan emails from SC accounts; the community list comes from signups + manually
  added emails.

## 9. Server restart hygiene when two processes fight for a port
A stale `python3 server.py` can survive a `kill` and keep holding :8533 while a
fresh instance crashes with `Errno 98 address already in use` (exit 3). After
any restart, verify with `ss -ltnp | grep <port>` that exactly ONE process owns
the port and that it is the NEW pid. Exit 143/137 notifications are just the
old process you killed during a restart — not a real outage.
