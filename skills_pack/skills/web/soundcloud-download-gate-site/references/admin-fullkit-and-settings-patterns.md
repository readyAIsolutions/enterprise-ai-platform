# Admin panel patterns & the "Full Kit" AI generator (session learnings)

Class-level patterns from extending the AC PE$0 admin + AI outbound stack.

## 1. The settings-WIPE bug (most important — catches you by surprise)

**Symptom:** saving a small settings form (e.g. just the Daily Briefing recipient,
`owner_email`) erases ALL other saved settings (R2 / Stripe / SC creds / Gmail client…).
The settings page then shows blank forms and it looks like data was lost.

**Root cause:** a catch-all `/admin/settings` handler iterated its full key list and ran
`db.set_setting(k, data.get(k, ""))` on every key. A form that only posts one field writes
`""` over every other saved value.

**Fix (apply to ANY multi-form settings endpoint):**
```python
for k in (KEY_LIST):
    if k in data:                      # only write keys this form actually submitted
        db.set_setting(k, data.get(k, ""))
# checkboxes: only touch when that form is the one saved
if "smtp_starttls" in data or "smtp_host" in data:
    db.set_setting("smtp_starttls", "1" if data.get("smtp_starttls") else "0")
```

**Verification pattern:** seed unique sentinel values for 3-4 unrelated settings, POST a
partial form (only the real field), assert the others still equal their sentinels. Turn this
into a regression test. When live-testing, ALWAYS snapshot the real value first and restore
it afterward (a live POST to a settings handler writes to production DB).

## 2. "Full Kit" — collapse N overlapping single-purpose AI buttons into ONE

**Problem that prompted it:** a release row had 4 separate AI buttons — Tag (genre/BPM/key/desc),
Share card (og_title/og_desc), Press kit (blurb+highlights), Promo kit (pitch+IG+TikTok+blog+news).
They generated overlapping marketing copy and each dumped output into a different scattered
panel → cluttered and redundant.

**Pattern:** one unified backend route (`/admin/ai-full-kit`) that:
- runs all generators in a single pass;
- AUTO-SAVES the persistent pieces (tag fields, OG meta, press blurb) in the same call;
- returns `{tag, share, press, promo, errors}` grouped by section;
- isolates per-piece failures: each generator wrapped in `_try(name, fn)` so one failing
  generator doesn't kill the rest, and `errors` reports which one(s) failed.

One client button + ONE organized drawer (reuse the promo-overlay modal CSS) with clearly
labeled sections: Metadata (auto-saved) · Share card (auto-saved + open/copy link) ·
Press kit (auto-saved + open page + highlights) · Promo copy (editable, per-piece Copy).
Keep per-piece regenerate independent. This is the preferred end-state for any "several AI
buttons that all write about the same entity" situation.

## 3. Admin tab reorganization (grouped, not a flat settings dump)

**Anti-pattern:** a single "Settings" tab cramming 8+ unrelated forms (creds, site copy,
follow-up window, Gmail API, newsletter-send, R2, Stripe, bookings) while a related thing
(email templates + newsletter) lived in a separate tab.

**Pattern:**
- Group tabs with visual separators: `.admin-tabs .tab-sep { width:1px; align-self:stretch;
  background:var(--line); margin:2px 6px; }` inserted as `<span class="tab-sep"></span>`
  between groups (Content / Outreach / Comms / Data / Config).
- Split a giant config tab by concern: **Settings** = site copy + behavior (front-page text,
  follow-up window, briefing recipient, bookings); **Integrations** = external accounts
  (SC creds, Gmail API, R2, Stripe).
- **When adding a new tab you MUST update three places:** (a) the `<nav>` tab link
  `data-tab="X"`, (b) the `<section id="X" data-ttab="X">`, and (c) the JS hash-map in
  `currentFromHash()` and the `activateTab` "exists in tab" guard — otherwise the hash
  doesn't resolve and the section never shows. Miss (c) and the tab looks dead.
- Server-side redirect after a settings save should bounce to the tab that OWNS the form
  (route to `#integrations` for account forms, `#settings` for site-copy forms).

## 4. Blog media inline display (image/video/audio, not forced download)

**Problem:** a blog upload only ever offered "Download" — because the serving endpoint
stamped `Content-Disposition: attachment` on everything, so `<img>/<video>/<audio>` couldn't
render it.

**Fix (two parts):**
1. Server: set `Content-Disposition: inline` for `image/`, `video/`, `audio/` media types;
   keep `attachment` for zip/pdf/other.
2. Template: branch on the stored file extension and emit an inline `<img class="...">`,
   `<video controls>`, or `<audio controls>` above the existing Download button; unknown
   types keep only the download link.

## 5. Fixed-width admin table clipping the last/action column

**Problem:** a table with `table-layout: fixed` gives the last column ("Action") whatever
leftover width — and once that cell holds an inline editor + a save-email form, the content
clips off the right.

**Fix:** give the widest/action column an explicit width share and align top:
```css
#community .admin-table{min-width:820px}
#community .admin-table th:nth-child(8){width:40%}
#community .admin-table td:nth-child(8){vertical-align:top;min-width:340px}
#community .admin-table td:nth-child(8) input{min-width:180px}
```
A 40% action column (or min-width on the cells) is the reliable cure for "content cut off on
the right" in a fixed-layout admin table.

## 6. Restart hygiene when killing the site server

The site runs `python3 server.py` on :8533. `kill <pid>` may silently fail and leave the old
process holding the port, so a new instance then exits with **code 3 "address already in use"**
while the OLD code keeps serving. Before judging a live change, confirm the port owner:
`ss -ltnp | grep 8533` → note the pid, `kill -9 <pid>`, verify "port free", then relaunch as a
tracked background process and re-check `ss` shows the NEW pid. Background-process "exit code"
notifications (137 = SIGKILL, 143 = SIGTERM) are usually just the instance you killed during a
restart — not a crash of the live server.
