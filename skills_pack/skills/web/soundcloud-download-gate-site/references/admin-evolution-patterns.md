# Admin evolution — settings-save, tab-hash, inline media, email-from-profile

Session-distilled patterns for extending the artist-gate site's admin + public
templates without regressions. All four bit a real deployment; each has a
durable fix.

## 1. Partial settings forms MUST NOT wipe other settings (critical regression)

**Symptom:** Admin saves the "Daily Briefing recipient" form, and *every other*
saved setting (Stripe/R2/SC/Gmail keys, homepage text, etc.) comes back blank.

**Root cause:** a catch-all settings POST handler did the classic bug:

```python
for k in ("sc_client_id", ..., "owner_email", ...):
    db.set_setting(k, data.get(k, ""))   # ← writes "" for every key
```

Any form that submits only a *subset* of the keys (e.g. just `owner_email`)
overwrote every other key with an empty string. Cheap-looking, catastrophic.

**Fix — only write keys the form actually submitted:**

```python
for k in (...):
    if k in data:                       # form field present
        db.set_setting(k, data.get(k, ""))
```

Checkbox / boolean flags need the same guard — only set them when their form is
the one being saved:
```python
if "smtp_starttls" in data or "smtp_host" in data:
    db.set_setting("smtp_starttls", "1" if data.get("smtp_starttls") else "0")
```

**Add a regression test** that seeds several unrelated settings, POSTs a
single-field form, and asserts the other values survive. This is the pattern
that prevents silent total data loss.

## 2. Admin tab navigation keys off `location.hash`, not the query string

**Symptom:** clicking "Edit" on the curators roster "does nothing" — server
loads the edit form fine but the section stays hidden.

**Root cause:** the single-page admin controller toggles `data-ttab` sections
from `location.hash` (e.g. `currentFromHash()` maps `#curators` → curators tab).
A link that goes to `?tab=curators&cedit=ID` **without** a `#curators` hash
leaves `location.hash` empty → the JS forces the *default* (Dashboard) tab →
the server-rendered edit form is hidden.

**Fix:** always include the hash in any admin deep-link that must switch tabs:
```
/admin?tab=curators&cedit={{cu.id}}#curators
```
Rule of thumb: **hash selects the tab, query string carries the payload** (ids /
edit targets / filters). When adding a new admin tab, add its name to
`currentFromHash()` too, or hash deep-links to it will silently land on
Dashboard.

## 3. Media files: serve image/video/audio `inline`, only force `attachment` for blobs

**Symptom:** uploading a PNG/MP4 to a blog post only ever produced a Download
button; the image never displayed.

**Root cause:** the file-serving endpoint stamped `Content-Disposition:
attachment` on *everything*. A browser cannot render a response it's told to
download.

```python
inline_types = ("image/", "video/", "audio/")
cd = "inline" if med.startswith(inline_types) else "attachment"
resp.headers["Content-Disposition"] = f'{cd}; filename="{disp}"'
```

Then render an `<img>` / `<video controls>` / `<audio controls>` by file
extension, and keep the Download link *below* the inline player. Unknown types
(zip/pdf) stay attachment-only.

## 4. Pull a curator's public email from their profile page (never fabricate)

For curators whose bios/booking pages actually publish a contact email, fetch
their `contact_url` (or SoundCloud profile) and extract the email. Use
`mailto:` first, then a regex over the page text — but **filter known noise** so
the site's own internal addresses never get saved:

```python
_NOISE_EMAIL = re.compile(r"noreply|no-reply|donotreply|forbidden|example\.|@test\.|sndcdn|soundcloud\.com$", re.I)
def _first_real_email(text):
    for m in re.finditer(r"[\w.+-]+@[\w-]+\.[\w.]+", text):
        e = m.group(0).strip().rstrip(".,;:)]}>")
        if "@" in e and "." in e.split("@")[-1] and not _NOISE_EMAIL.search(e):
            return e.lower()
    return ""
```

Return `{found: False, note: "no public email"}` honestly when nothing real is
found — famous SC/Apple/Spotify accounts usually publish none. Never synthesize
a fake address (this user runs a strict no-fabricated-data policy). Wire it as a
per-row "Pull email" button that live-updates the email cell + contact badge.

## 5. Google Translate widget (client-side, site-wide) for a Jinja2 app

To let visitors translate the page to their own language on request without a
backend/API key, add the Google Translate element to the shared base template:

1. A host element in the nav: `<span id="google_translate_element" title="Translate this page"></span>`.
2. Init + loader before `</body>`:
   ```html
   <script>
     function googleTranslateElementInit() {
       new google.translate.TranslateElement({
         pageLanguage: 'en',
         includedLanguages: 'en,es,fr,...,uk',
         layout: google.translate.TranslateElement.InlineLayout.SIMPLE,
         autoDisplay: false
       }, 'google_translate_element');
     }
   </script>
   <script src="//translate.google.com/translate_a/element.js?cb=googleTranslateElementInit"></script>
   ```
3. Hide the Google top banner with CSS (`.goog-te-banner-frame.skiptranslate{display:none!important}` + `body{top:0!important}`), style the select to match the theme, and stack it in the mobile menu.

`autoDisplay:false` means English viewers are never force-translated — it's
visitor-initiated, exactly "upon their request". Google-hosted, so availability
is partly out of your control.
