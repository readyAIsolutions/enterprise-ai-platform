# AC PE$0 site — operational map

Canonical example of the download-gate artist site built from `admin-dashboard-ui-patterns`.

## Where it lives / how to run
- Dir: `/home/hunter/Desktop/ac pe$0`  (NOTE the literal `$0` in the folder name — see the
  "Paths Containing `$` Break Inline `cd`" pitfall; always single-quote in shell or use a
  helper .py that sys.path-inserts the abs path without `cd`).
- Starlette on **:8533**. Boot: `cd '/home/hunter/Desktop/ac pe$0' && python3 server.py`.
- After code edits restart; static CSS/JS are served from disk but the HTML templates are
  rendered via the running process.

## Access / auth
- Admin: `http://localhost:8533/admin` — `admin` / `acpeso2026`. ALSO admin auto-grants when
  the owner's SoundCloud account (`acpeso`, email andrewdonnelly8502@gmail.com) signs in via
  SC OAuth.
- Everything is DB-backed (SQLite `acpeso.db`); `.env` + DB settings are one source of truth.

## Artist social / contact (use these exact URLs)
- SoundCloud: https://soundcloud.com/acpeso
- TikTok: https://www.tiktok.com/@acpeso
- YouTube: https://www.youtube.com/@acpeso
- Instagram: https://www.instagram.com/ac.peso
- Linktree: https://linktr.ee/acpeso
- Booking email: 8503hh@gmail.com  (also `booking_email` / `booking_insta=ac.peso`)
Social links live in `templates/base.html` (site-wide footer) and `templates/index.html`
(Bookings/Contact row). When the artist updates a handle, update BOTH.

## Feature map / routes
- `/` home, `/releases`, `/release/<slug>`, `/g/<slug>` gate page.
- `/free-for-profit` — `[FREE FOR PROFIT]` tab: gated free downloads. Auto-synced from the
  owner's SoundCloud tracks whose title contains "free for profit" via admin-only
  `POST /api/sync-ffp` (admin button in Release manager). Gate = like+repost+comment verified
  live through the SC API before `/download/<sid>` unlocks.
- `/beatpacks`, `/beatpack/<slug>` — paid store. Checkout = real Stripe Checkout Session,
  `/stripe/webhook` confirms payment. `cover` is an uploaded image/gif served at
  `/media/cover-<id>.<ext>`.
- `/media/<name>` — serves uploaded covers, path-traversal sanitized (basename + known prefix).
- `/admin` + tabs: Releases, Beatpacks (genre manager), Playlist Curators, Settings, Analytics.

## Data model notes
- releases: `free_for_profit` flag decides FFP-tab membership; `gate_requires` JSON list.
- beatpacks: currency locked to USD, BPM kept in the TITLE (no bpm field), slug auto-gen,
  `beatpack_genres` setting drives the genre dropdown (admin-managed).
- No `/api/seed` — the demo seeder is removed; never re-add fake orders/packs/subscribers to a
  real site.

## Status
Tracked in `/home/hunter/Desktop/ac pe$0/STATUS_ACPE$0.md` (PASS/FAIL board + "needs YOUR
action" list). Test suite: `tests/test_site.py` (run with pytest), render check:
`verify_render.py`. Stripe is wired but NOT live until the owner adds keys in
Admin → Settings → Stripe.
