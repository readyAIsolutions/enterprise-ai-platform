# Autonomous free advertising: on-site SEO (no logins, no help needed)

When LO asks "can you advertise without my help / get us out there" the answer is
YES for on-site SEO — the only free ad channel a bot can execute 100% autonomously
(no accounts, no phone/email verification). External ad platforms (Google Business,
Facebook, Craigslist, Reddit, Discord) genuinely need LO's real accounts/verification
and can't be faked — don't try, don't create fake accounts.

## What to build (all live on acpeso.shop, upgrades #87)
1. `sitemap.xml` — dynamic endpoint listing ONLY indexable PUBLIC pages.
   For this StackOverflow-style login-gated site: home / , /releases, /free-for-profit,
   every `/release/{slug}`, every `/g/{slug}` (download gate, public by design), and
   published `/blog/{slug}` pages. CRITICAL: EXCLUDE login-gated pages (/beatpacks,
   /beatpack/*, /analyze, /community, /history). Sending Google to a login redirect
   = soft-404 that wastes crawl budget. This was the pre-existing bug (old sitemap
   included /beatpacks and /beatpack/*).
2. `robots.txt` — Allow public paths, Disallow /admin,/history,/gate-status/,/unlock/,/api/,
   point `Sitemap:` at the xml. Note Cloudflare injects its own managed robots block;
   the app's rules append after it (verify in live output, not just local).
3. JSON-LD `MusicGroup` (and per-page MusicRecording/Product when useful) in base.html
   so Google shows the artist/track correctly and can produce rich results.

## Gotchas
- The server ALREADY had robots.txt/sitemap_xml handlers near the 404 handler.
  Check for existing definitions + Route() registrations BEFORE adding new ones or you
  create duplicate defs (later `def` wins the name) and duplicate routes. Search
  `grep -n "robots.txt|sitemap" server.py` first; enhance the canonical, remove dupes.
- `Response` is already imported from starlette.responses in server.py.
- The free page flow must be genuinely public (no login redirect) or the sitemap
  lies to Google. Verify each URL returns 200 locally, not 303→/login.
- After deploying, the site still needs submitting to Google/Bing Search Console —
  that requires LO's Google account (one login). But the site becomes crawl-ready,
  which it wasn't. Google takes days-weeks to index.
