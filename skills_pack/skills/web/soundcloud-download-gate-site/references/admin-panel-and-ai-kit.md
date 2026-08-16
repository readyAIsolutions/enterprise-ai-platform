# Admin Panel Organization & AI-Kit Consolidation

Session-derived patterns for keeping the AC PE$0 admin usable as it grows.
(These are the technique/UI pitfalls, not one-off feature notes.)

## 1. Grouped tab bar beats a bloated Settings tab
The single biggest disorganization trap: one "Settings" tab accumulates
unrelated things (creds, site copy, follow-up window, newsletter-send, R2, Stripe,
bookings) because every new "save something" form just gets appended there.
Fix: split into **themed groups** with visual separators (`.tab-sep` dividers):
- Content: Dashboard · Releases · Beatpacks · Blog
- Outreach: Playlist Curators · Community
- Comms: Email & Newsletter · Analytics
- Config: Settings (site copy / config) · Integrations (accounts/connections)

`data-ttab` sections + `data-tab` nav links drive show/hide. Every new tab name
MUST be added to `currentFromHash()` in `static/app.js` or the hash won't activate it.

## 2. Redirect back to the tab that owns the submitted form
When one POST handler (e.g. `/admin/settings`) serves many forms now spread across
tabs, branch the redirect on which key the form submitted:
```python
integ_keys = ("sc_client_id", "smtp_host", "r2_account_id", "gc_client_id", "stripe_secret_key")
if any(data.get(k) is not None for k in integ_keys):
    return RedirectResponse("/admin#integrations", status_code=303)
return RedirectResponse("/admin#settings", status_code=303)
```
Otherwise a user "saves" on Integrations but lands back on Settings and thinks it
failed.

## 3. `table-layout: fixed` silently clips the last column
Admin tables use `table-layout: fixed`. Any column without an explicit `th:nth-child(n)`
width gets squeezed to leftover scraps. When a cell grows rich content (editable
textarea, multi-button forms, save-email input), everything past the edge gets
cut off and looks "broken." Fix: give the action column a real width and align top:
```css
#community .admin-table{min-width:820px}
#community .admin-table th:nth-child(8){width:40%}
#community .admin-table td:nth-child(8){vertical-align:top;min-width:340px}
```
Also set sensible min-widths on the inputs/textareas inside that cell.

## 4. Collapse overlapping AI buttons into ONE "Full kit"
Four per-release buttons (⚡ Tag, ⚡ Share card, ⚡ Press kit, ⚡ Promo kit) all
generated overlapping marketing copy and each dumped output to a DIFFERENT scattered
panel → felt repetitive and unorganized. Fix: one `POST /admin/ai-full-kit` route
that runs tag_release + seo_meta + press_kit + promo bundle (pitch, IG, TikTok,
blog, newsletter) together, auto-saves the persistent pieces, and opens ONE drawer
with labeled sections: **Metadata (auto-saved) · Share card (auto-saved) · Press kit
(auto-saved) · Promo copy (editable)**.
- Per-piece error isolation: wrap each generator in `_try(name, fn)` collecting into
  `errors`, so one failing generator doesn't kill the rest.
- Persistent pieces auto-save via `db.update_release_fields(...)`; promo copy stays
  editable (Copy / insert buttons).
- Keep the "tag all" bulk button separate for batch work.

## 5. Make AI drafts EDITABLE, and Send/Copy read the live edits
When an AI draft is shown read-only and then "sends," users are stuck with the
machine's wording. Render the draft as editable fields (subject input + message
textarea), and have Copy + Send read CURRENT values on click (a `getVal()` that
queries the on-screen fields), sending `v.subject`/`v.body` — not the stale `j.*`.
Backend already accepted arbitrary subject/body; only the render was the bottleneck.
Update stale "go to Settings" hints when tabs get renamed (point to Integrations).

## 6. Server restart gotcha: confirmed-dead before you start the new one
`kill <pid>` can fail silently (process lingers, still holds the port). Your fresh
instance then exits on "address already in use" and the SITE IS STILL THE OLD CODE —
you think you deployed but didn't. Always:
1. Find the real pid: `ss -ltnp | grep <port> | grep -oP 'pid=\K[0-9]+'`
2. `kill -9 <pid>` (SIGKILL, exit 137)
3. Re-check `ss -ltnp | grep <port>` → confirm "port free" before starting
4. Start, then verify owner pid changed AND `/` returns 200.
The background-process "exit 137/143" notifications about the SITE are exactly this —
old instances I killed during restarts, not the live one.
