# Admin-panel mechanics: settings-wipe, tab-hash navigation, and inline media

Class-level pitfalls for this download-gate admin (Starlette on :8533, `templates/admin.html`
+ `static/app.js` + `static/style.css`, all read live from disk, cache-busted by versioned
`?v=` in `templates/base.html`). Each burned me in a real session; encode them so the next
session starts knowing.

## 1. Never let a partial settings form wipe other settings (HIGH SEVERITY)
Symptom: saving a small settings form (e.g. just the Daily Briefing recipient, which posts
only `owner_email`) erases every OTHER saved setting (SC/Stripe/R2/Gmail keys show blank).

Root cause: the shared `admin_settings()` handler iterated its full key list and ran
`db.set_setting(k, data.get(k, ""))` for EVERY key. A form that only submits one field writes
`""` over every key it didn't include → silent mass wipe.

Fix (the durable rule): **only write a key that the form actually submitted.**
```python
for k in (ALL_SETTINGS_KEYS...):
    if k in data:
        db.set_setting(k, data.get(k, ""))
```
Checkbox nuance: a checkbox is absent from the form when unchecked, so only touch it when its
own form is the one being saved (`if "smtp_starttls" in data or "smtp_host" in data`).

Why it happens in this codebase: every settings sub-form posts to the SAME `/admin/settings`
endpoint (they differ only in which fields they include). So the handler must be defensive
about presence, never about "the form is the full page".

## 2. Admin tab links MUST carry the `#tab` hash, not just `?tab=`
Symptom: an "Edit" button that navigates to `/admin?tab=curators&cedit=ID` "does nothing" —
the page reloads but stays on Dashboard, or the target section never appears.

Root cause: the tab-activation JS (`currentFromHash()`) keys off `location.hash`, NOT the
`?tab=` query param. With an empty hash it forces the Dashboard tab and hides every other
`[data-ttab]` section. The server may populate the edit form, but the JS hides the section so
it looks like the click did nothing.

Rule: any admin link that must land on (or return to) a specific tab must include that
section's hash — `href="/admin?tab=curators&cedit={{cu.id}}#curators"`. Order matters: keep
query params BEFORE the `#`. (There is already a known flash-message bug where params after
`#` are lost; same discipline — params first, hash last.)

Applies to every tab: dashboard, releases, beatpacks, blog, curators, community, emails,
analytics, settings, integrations.

## 3. Serve media as `inline`, not `attachment`, or images/video can't render
Symptom: blog-uploaded images/videos/press assets only ever show a "Download" button and never
display inline on the page.

Root cause: the file-serving route stamped `Content-Disposition: attachment` on everything, so
`<img>`/`<video>`/`<audio>` can't render it (a browser won't render a file told to download).

Fix: for media MIME types send `inline`, keep `attachment` for zip/pdf/other.
```python
inline_types = ("image/", "video/", "audio/")
cd = "inline" if med.startswith(inline_types) else "attachment"
```
Then in the template branch on the filename's extension and emit `<img>` / `<video controls>`
/ `<audio controls>` (with the source `/blog-file/...`), keeping the Download link below.

## 4. Combine overlapping per-item AI buttons into one "full kit" action
When several per-row AI buttons (Tag / Share card / Press kit / Promo kit) all write overlapping
marketing copy about the same item, collapse them into ONE backend route that runs all
generators and AUTO-SAVES the persistent pieces (tag fields, OG meta, press blurb) in one shot,
then opens ONE organized drawer with labeled sections (Metadata · Share card · Press kit ·
Promo copy). Isolate per-generator failures (`_try` collecting `errors`) so one generator
down doesn't kill the rest. Users find four scattered buttons "unorganized" — one full kit is
the version they want.

## 5. Make editable things actually editable (AI drafts you then send/copy)
AI-drafted messages (reward note, DM pitch, follow-up) should render as EDITABLE fields
(subject input + message textarea), and any "Send"/"Copy" action must read the CURRENT on-screen
values (`getVal()` at click time), not the original AI return. Also auto-generate on modal open
instead of forcing a manual first step. Users want to review/tweak a pitch BEFORE they DM it.

## Debugging reminder: verify the port owner after restarting the server
`kill` + relaunch can silently fail: the OLD process keeps holding :8533 ("address already in
use", exit 3), and the new instance exits while the site is still served by stale code. After
any restart, confirm `ss -ltnp | grep 8533` shows the NEW pid and the site is serving current
behaviors. (Static/template changed? No restart needed — files are read live; only server.py
logic changes need a restart.)
