# ACPE$0 site ops techniques (2026-08-02 session)

SEE ALSO:
- `references/content-moderation-and-chat-antiabuse.md` — severity-tiered censor
  (allow swearing / block slurs + hate, obfuscation-proof regexes, plural/slash/
  misspelled/emoji + genocide-phrase forms), instant chat delete, multi-emoji
  reactions, 15s per-user chat cooldown, the do-not-ban-tester rule + the account-
  block endgame, and the mock-test fan-ID teardown pitfall.
- `references/free-advertising-placement.md` — free ($0 budget) ad-placement pack:
  ranked free listings (Google Business, Craigslist, Bandcamp...), spam-safe music
  communities + anti-shadowban rules, and the copy-paste ad deliverable shape.

## Copy voice + NO em dashes (user rule, HIGH PRIORITY)
LO/PE$0: "NEVER use em dashes again. We don't want it to show that it's AI. Make it
sound human, like PE$0 speaking."
- Ban em (U+2014) AND en (U+2013) dashes in ALL user-facing copy: AI pitches, DM
  drafts, emails, newsletters, captions, fallback templates, status messages, admin
  strings. They read as "AI wrote this".
- Enforce TWO layers so it's guaranteed:
  1. SYSTEM prompt forbids the dashes + demands first-person street-smart human voice
     ("texting a friend", zero corporate fluff).
  2. Post-process all AI output through a `_humanize()`-style sanitizer that replaces
     em/en dashes with commas/periods and collapses doubles (" — " -> ", ").
- Use a pipe `|` as the email-subject separator (e.g. `Submission: {title} | AC PE$0`)
  instead of an em dash.
- Add a test that asserts no generated subject/template and no `_humanize` output
  contains U+2014 or U+2013. (Files: `aiwriter.py` — SYSTEM + `_humanize()`; `curator.py`
  — SUBJECTS + DM/newsletter bodies.)

## Instant repost verify (the "repost verify is slow as hell" fix)
Root cause: SoundCloud's read-back `GET /me/track_reposts?limit=200` is eventually
consistent and can lag many seconds (and paginates past 200). Like is fast because
`/me/favorites` updates almost instantly; comment was already fast because it reposts
server-side with the fan's token.
Fix: perform the repost server-side with the fan's own token. A 2xx (or 409 "already
reposted") from `POST /me/track_reposts/{id}` IS the proof, so mark verified instantly,
zero read-back. Pattern:
- `soundcloud.repost_track()` treats 409/403 "already" as success.
- New `POST /api/repost` endpoint = one-click "Repost to verify".
- 2xx/409 -> `db.mark_complete(sid,"repost")` immediately.

## SoundCloud token "never expires" (JWT + refresh)
SoundCloud issues SHORT-LIVED (~1h) JWT access tokens (decode `exp` from JWT payload)
PLUS rotating refresh tokens. Realities:
- A refresh token that returns `invalid_grant` is DEAD. No code revives it; the owner
  MUST re-auth once via the SoundCloud login to mint a fresh pair. Say this plainly.
- Because refresh tokens rotate and access tokens die hourly, the "never expires" fix
  is a PROACTIVE auto-refresh that renews BEFORE expiry:
  - Decode the JWT `exp` claim (`access_token_expires_in()`).
  - Refresh when <5 min left OR token invalid.
  - ALWAYS persist the rotated refresh token back to DB (rotation can't strand it).
  - Background keeper: `keep_owner_token.py` + a systemd user timer running every
    30 min, independent of site traffic, so the token is renewed every 30 min forever.
- The owner-scoped token (the only one that can edit owner track metadata like the buy
  link) needs its own resolver that matches by `admin_sc_user_id`, then auto-refreshes.

## Auto buy link on SC track (upgrade #35)
On release create/edit (admin form + FFP sync), call SoundCloud's track-update API to
set `track[purchase_url]` = `https://acpeso.shop/release/{slug}` (+ title as purchase
title). Needs the OWNER token (only owner can edit owner track metadata). Best-effort,
never blocks the save; skip silently if owner token missing. Backfill button: iterate
all releases, call the same. (Files: `server.py` `_owner_sc_token()` +
`_sync_release_buy_link()`; `soundcloud.py` `_api_put()` + `update_track_buy_link()`.)

## Bulk "pull emails for all curators" (upgrade #39 + email_finder.py)
Old approach: only fetched the SoundCloud profile + bio links (misses everything).
New: multi-source OPEN-WEB email finder that VERIFIES identity before saving:
- Search engines that work without JS: DuckDuckGo **lite** (`lite.duckduckgo.com/lite/?q=`,
  key: it surfaces real emails right in the result snippets) is most reliable; DDG html and
  Bing often JS-wall / vary. Google returns no emails in snippets.
- Queries from name + handle: `"<name>" email/booking/contact/submissions/business/@gmail`.
- Crawl the entity's own site + linked pages + ZoomInfo/YouTube/contact dirs.
- VERIFY each candidate: score by (a) domain matches entity's own site, (b) local-part /
  handle echoes their name, (c) page context mentions their name/handle. Auto-save only
  confidence >= 0.4; list weak ones for manual pick (never guess).
- Filter junk: `noreply@`, image-file extensions, sndcdn, schema.org.
- Honest reality: big/megachannel entities often have NO public email (DM-only or via
  management) — say so with evidence rather than fabricate.

## Gmail reply-scan (auto funnel) gotchas
- Config-type bug: `gmailapi.enabled(db, _site())` crashes because `_site()` returns the
  SITE settings dict (keys like `gc_client_id`, not `client_id`) while `enabled()` expects
  a Gmail config with a `client_id` key. Pass `gmailapi.settings(db)`.
- The stored Google consent may predate added scopes: `has_read_scope()` that merely
  checks "creds present" LIES. Check the token's REAL granted scopes via Google's
  `tokeninfo` endpoint (`oauth2.googleapis.com/tokeninfo?access_token=...`) and look for
  `gmail.readonly`. If it's missing, the scan needs a one-time Gmail re-consent (the
  SCOPE string already includes readonly; re-running Connect Gmail grants it).
- Reply detection only advances curators we actually emailed (last_pitched_at set), and
  only from the account's inbox.

## Comment spam rate limit
Client comments (`POST /api/item-comment` on releases/beatpacks) should be rate-limited:
1 comment / fan / 5 min. Look up the fan's last-comment timestamp (db
`last_comment_time()`), reject with HTTP 429 + friendly msg when <300s. In tests that
share a session-scoped DB + mock fan, clean up inserted comments so other tests using
the same fan aren't rate-limited.

## Test-suite sharing pitfall (all ACPE tests)
Tests share a SESSION-scoped test DB and the SAME mock fan. Any test that inserts rows
keyed to that fan (comments, an owner token) MUST clean up afterward (direct SQLite
DELETE via `os.environ["ACPE_DB"]`) or it breaks later tests (rate limit, admin identity,
fan favorites).
