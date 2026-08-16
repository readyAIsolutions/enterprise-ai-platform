# Release-Pitch Composer (implemented 2026-08-02)

A single admin panel that composes + sends a release pitch to **newsletter subscribers**
and/or **curators**, filtered by which platforms the release is on. Built on the existing
`curator.compose_pitch` / `curator.send_email` (Gmail-API backend) machinery.

## Server routes (`server.py`)
- `GET /admin/pitch-preview` → `admin_pitch_preview`: returns `{counts:{subscribers,curators}, sample:{subject,body}, dry_run:True}`. Reads `release_id` + `platforms` (comma-separated) query params. Uses `curator.compose_pitch({}, rel, site, platforms[0] if platforms else None)` for the sample. NO sending.
- `POST /admin/release-pitch` → `admin_release_pitch`: form fields `release_id`, `send_subscribers=1`, `send_curators=1`, `platforms` (comma-separated), `subject`, `body`, `dry_run=1`. Sends to subscribers with the SAME subject/body (auto-generates a default if blank); sends to curators with a PER-CURATOR personalized pitch via `compose_pitch(cu, rel, site, cu.platform)`. Every attempt goes through `db.log_email(...)` with status sent/queued/error. Returns a 303 redirect to `/admin?tab=curators#curators&msg=...`.
- Register both in the `app.routes` list alongside the existing curator routes.

## Supporting change to `db.all_curators` (db.py)
`all_curators(platform=None)` previously accepted only a single platform string. The composer
passes a LIST of platforms, so it now handles `platform` as a list/tuple/set too:

```python
def all_curators(platform=None):
    c = conn()
    if platform:
        if isinstance(platform, (list, tuple, set)):
            plist = [p for p in platform if p]
            if not plist:
                rows = c.execute("SELECT * FROM curators ORDER BY platform, name").fetchall()
            else:
                marks = ",".join("?" for _ in plist)
                rows = c.execute(
                    f"SELECT * FROM curators WHERE platform IN ({marks}) ORDER BY platform, name",
                    tuple(plist)).fetchall()
        else:
            rows = c.execute("SELECT * FROM curators WHERE platform=? ORDER BY platform, name", (platform,)).fetchall()
    else:
        rows = c.execute("SELECT * FROM curators ORDER BY platform, name").fetchall()
    c.close()
    return [dict(r) for r in rows]
```

## Admin template shape (admin.html, Curators tab)
A `form[data-release-pitch]` POSTing to `/admin/release-pitch` with:
- `select[name=release_id]` (all releases)
- a `check-group` of `input[name=platforms][value=spotify|spotify_editor|apple|deezer|amazon|youtube|tiktok|soundcloud|blog|press|dj|venue|bar|collaborator|buyer]`
- audience checkboxes `send_subscribers` (default checked, show `subscriber_count`) and `send_curators`
- `input[name=subject]` + `textarea[name=body]` (blank body = auto-generate)
- `input[name=dry_run][value=1]` checked by default
- a `button[data-pitch-preview]` that fetches `/admin/pitch-preview?release_id=..&platforms=..` and renders `#pitch-preview`, plus the real submit.

NOTE: `db` is NOT in the Jinja template context — pass `subscriber_count=db.subscriber_count()` into the admin context and reference `{{ subscriber_count }}` in the template, not `db.subscriber_count()`.

## Design intent (what LO asked for)
- He does NOT want auto-posting to social platforms (no per-platform API keys wired, and he rejected that).
- He wants a **selection of platforms the release is on**, compose the email in-panel, send to newsletter subscribers AND/OR curators ("the found people"), with preview-first so nothing sends until he confirms.
