# Editable email templates — implementation detail (added 2026-08-02)

Request: LO wanted an admin page to edit the actual email copy sent to the
newsletter and elsewhere. Previously the pitch bodies/subjects + newsletter copy
were hardcoded module constants (`BODY_TEMPLATE` / `DJ_BODY_TEMPLATE` /
`DEAL_BODY_TEMPLATE` / the `SUBJECTS` dict in `curator.py`, and inline strings
in `newsletter.build_digest`). This reference records the exact wiring so it can
be reproduced without re-deriving.

## Where the read-from-settings happens
`curator.email_templates(settings)` returns a dict, resolving each key to
`settings.get(k) or <hardcoded default>`. Empty DB value == keep the built-in
default, so blank fields never break sending.

Settings keys resolved:
- per-platform subjects: `subj_<platform>` (spotify, spotify_editor, apple,
  deezer, amazon, youtube, tiktok, soundcloud, blog, press, dj, venue, bar,
  collaborator, buyer) + `subj_default` fallback
- pitch bodies: `body_pitch`, `body_dj`, `body_deal`
- one-line: `default_pitch` (used as `{pitch}`)
- everywhere: `email_signature`
- newsletter: `newsletter_subject`, `newsletter_intro`, `newsletter_cta`

## Merge tags
`compose_pitch` builds a `merge` dict and `.format(**merge)`s the chosen subject
+ body template. Merge keys: curator_name, title, platform_name, genre, bpm, key,
soundcloud_url, download_url, pitch, fit_reason, list_name, artist_links, artist,
location. `curator.compose_pitch` chooses the body template by audience:
`dj/venue/bar` -> body_dj, `buyer/collaborator` -> body_deal, else body_pitch.
Subject = `T.get(platform) or T.get('subj_default') or SUBJECTS['spotify']`.
List the merge vars in the admin UI so the artist knows what tags exist.

## Four-place wiring for each editable key
(1) add to `_site()`'s settings tuple (so it reaches templates);
(2) add to the `TEMPLATE_KEYS` + `TEMPLATE_SUBJ_PLATFORMS` save list in the
`/admin/email-templates` POST handler;
(3) render `<input>`/`<textarea name="key">` in admin.html with
`{{ site.get('key') or T_<key> }}` (fallback to a `T_...` default value exposed
by `_site()` — e.g. `d["T_body_pitch"] = curator.BODY_TEMPLATE`);
(4) if it feeds the newsletter, ADD IT TO `newsletter._db_settings()`'s key list.

## THE newsletter gotcha (verified live)
`newsletter.build_digest()` calls `curator.email_templates(_db_settings())`.
`_db_settings()` loads ONLY a fixed key list. If a new newsletter key (e.g.
`newsletter_subject`) isn't in that list, the save works but the preview/actual
digest still falls back to the default. Fix: add the newsletter template keys to
`_db_settings()`'s key list too. Symptom: "I saved the subject but the email
still shows the old one."

## Routes
- `POST /admin/email-templates` — saves all `TEMPLATE_KEYS` + `subj_<platform>`
  keys via `db.set_setting`, redirects to `#emails` tab with flash msg.
- `POST /admin/email-preview` — body params `kind=pitch|newsletter`,
  `platform`. Builds a sample curator dict + sample release (first
  `db.all_releases()` or a literal fallback), returns JSON
  `{ok, subject, body}` via `compose_pitch` (or `newsletter.build_digest()`
  for newsletter). JS shows subject + body in a `white-space:pre-wrap` preview
  box.

## Signature
Append `email_signature` inside `curator.send_email` (both Gmail-API and SMTP
paths) so every outgoing message carries the bio/links block. Editable on the
same Email Templates page.

## Verify
POST a custom body/subject, GET `/admin/email-preview` and assert the custom
text appears, then DELETE those settings rows (`DELETE FROM settings WHERE key
IN (...)`) so the DB returns to defaults. Run `pytest`.
