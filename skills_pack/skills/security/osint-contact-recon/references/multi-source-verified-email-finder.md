# Multi-source verified email finder (batch / app-integrated)

Condensed from the AC PE$0 curator email-pull work (2026-08-02). Use when you need
to find public booking/contact emails for MANY people/entities (a curator roster, a
label list, an artist directory) and the platform you discovered them on has no email.

## Why the naive approach fails
Fetching only the source-platform profile (SoundCloud page) + following its bio links
misses the vast majority of real emails. Booking addresses live on the entity's OWN
site, ZoomInfo, YouTube about, contact directories, Discord, Bridge.audio, blog posts —
nowhere on the discovery platform.

## Query matrix
For each target, run the cartesian product over identity and intent terms:
- Identity: `"<full name>"` and `"<platform handle>"`
- Intent: `email`, `booking`, `contact`, `submissions`, `business`, `management`,
  `@gmail`, `@outlook`
- Plus combos: `"<name>" email contact`, `"<handle>" bookings email`

The handle is often the highest-signal query: `"trapnation" email` surfaces the real
booking address faster than the human-readable name.

## Engine reliability (server-side, no JS)
- **DuckDuckGo lite** (`https://lite.duckduckgo.com/lite/?q=…`) — the workhorse.
  Returns real external links AND, even when link parsing fails, the raw page text
  still contains the surfaced email directly in the snippet (verified live:
  `"trapnation" email` → `bookingtrapnation@gmail.com`). Always keep the raw HTML
  even if the link regex matches nothing.
- Fallbacks: `html.duckduckgo.com/html/`, Bing, Google, Startpage.
- Bing/Google/Startpage are heavily JS-walled from a server; do NOT depend on their
  HTML parsing. Try them as best-effort, don't require them.
- Parse DDG links: result `<a>` hrefs may be wrapped as `//duckduckgo.com/l/?uddg=<url>&rut=…`
  — extract `uddg=` and urldecode.

## Harvest
- Collect EVERY candidate email across all search pages + every fetched linked page,
  storing the page URL it came from.
- Fetch ~8 of the top linked pages (their own site, ZoomInfo, YouTube about, etc.) to
  get rich context + inline emails.

## Identity verification scoring (auto-save gate)
Before saving/sending to a found address, score it 0..1:
| signal | weight |
|---|---|
| email domain == entity's own site domain (or subdomain) | +0.5 |
| local-part or domain contains the entity handle (e.g. `trapnation@`) | +0.45 |
| local-part echoes any name token (trap, nation) | +0.3 |
| the source page context mentions their handle | +0.35 |
| the source page context mentions their name | +0.25 |
| address found on the entity's own domain | +0.3 |

Auto-save only when score ≥ 0.4. Below that, list candidates for manual review — never
auto-pitch someone you haven't confirmed is the right person/entity.

## Noise filter — never persist junk
Reject internal/platform noise: `noreply@`, `no-reply@`, `donotreply@`, `sentry@`,
`sndcdn`, `@2x`, image-file extension false-positives (`.png/.jpg/.gif`), `example.`,
`schema.org`, `@users.noreply`, wixpress/godaddy/squarespace/wordpress as false hit.

## Honest no-result
Entities that are DM-only or routed through management (CAA/WME, etc.) have NO public
email. Report "no verified email" + list the candidates found rather than fabricating
a contact. This matches the no-fake-data rule and survives pushback.

## Bulk application
Wrap it in a background job: iterate every target missing an email, run the shallow
(profile+bio) path first for cheap wins, then the deep finder; save only verified
matches; return a found/missing summary. Run it detached so an admin HTTP request
returns immediately.
