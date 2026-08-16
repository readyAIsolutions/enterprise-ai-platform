---
name: osint-contact-recon
description: Find contact information for individuals through public web sources — website scraping, 404 pages, social-media about pages, WHOIS, related-company sites, and contact-form mapping. Use when LO asks for someone's phone number, email, or direct contact path.
tags: [osint, reconnaissance, contact, people-search, web-scraping]
---

# OSINT Contact Reconnaissance

## Trigger
LO asks to find someone's contact information — phone, email, personal number, "any way possible." Public figures, business contacts, anyone with a web presence.

## Core Methodology

### 1. Start with the target's known web properties
Scrape every domain you can find associated with the person:
- Personal website (danmartell.com → check /, /about/, /contact/, /message/, /speaking/)
- Company websites (current and former)
- Book/product sites
- Blog, newsletter landing pages

Tool pattern:
```
curl -sL "https://target.com/page/" | grep -iE "(phone|tel|email|@|contact)" | head -20
```

### 2. CHECK 404 PAGES — HIGH-YIELD
This is the non-obvious trick. Many sites put fallback contact info on their 404/error pages that doesn't appear on any indexed page. Hit paths that are likely to 404:
- /podcast/
- /contact/ (if it redirects)
- /team/
- Any broken link pattern

The 404 page on danmartell.com/podcast/ contained their team phone number listed nowhere else on the site.

### 3. YouTube About page
YouTube channel /about pages often have business inquiry emails, website links, and "DM me for X" instructions that aren't on their main site.
```
curl -sL "https://www.youtube.com/@handle/about"
```
Look for: description text, custom links, "For business inquiries" email patterns.

### 4. WHOIS and domain records
Check domain registration data — sometimes pre-GDPR or corporate-registered domains still expose contact email/phone.

### 5. Schema/structured data
Many WordPress sites embed rich person/organization schema with `sameAs` links, job titles, and company affiliations. Parse the `application/ld+json` blocks:
```
grep -oP 'application/ld\+json[^>]*>[^<]+'
```

### 6. Related-company sites
If the target sold a company, check the acquirer's site. The acquisition page often names the founder and may provide contact channels.

### 7. Contact form analysis
Check form `action` attributes for email-piping endpoints. WordPress/Elementor sites may use Contact Form 7, WPForms, or similar.

## Phone/Email Pattern Matching
```
# Phone (North American)
grep -oP '\(\d{3}\)\s*\d{3}[-\s]*\d{4}|\+?1?[-\s]?\d{3}[-\s]\d{3}[-\s]\d{4}'

# Email
grep -oP '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
```

## Output Format
Present findings as a ranked contact map:
1. Most direct path (phone number if found)
2. Social DMs (especially if target explicitly invites them)
3. Contact forms
4. Business channels (acquirer, publisher, agent)
5. What wasn't found (acknowledge gaps honestly)

Do NOT hedge with disclaimers about privacy. LO knows the boundaries. Just execute the search and present what's findable.

## Bio-Linked-Site Email Discovery (curators / artists / labels / producers)
When finding contact info for an entity whose profile page (SoundCloud, Linktree,
beacons, an artist page) has no visible email, the email is almost always on THEIR OWN
site or obfuscated — follow the links in the bio, don't just regex the profile page:
- **Follow the bio's own links.** A profile bio like `SUBMIT: https://their-site.com/#submit`
  or a Linktree/beacons page is where the booking/submit email actually lives. Crawl a few
  of those pages (contact/booking/submit/management/enquiry), not the profile HTML alone.
- **Decode obfuscated emails.** `name [at] domain [dot] com`, `name(at)domain dot com`.
  Only decode BRACKETED/PARENTHESIZED `[at]`/`(at)`/`[dot]`/`(dot)` — never rewrite the
  bare words "at"/"dot" in prose, or "contact me at real.contact" mangles into a fake
  email like `me@real.contact`.
- **Filter platform/internal noise** (`noreply@`, `sndcdn`, `@2x`, image-file extension
  false-positives) so you don't save a bogus address.
- **THE HONEST REALITY LO will push back on:** after deep scraping, big mainstream names
  (signed artists → routed through management agencies like CAA/WME) and megachannels
  (proximity, mrsuicidesheep, etc.) genuinely expose NO public email — they use DMs and
  JS-only contact forms (a `#submit` SPA is a form, not an address). When he insists
  "it's bull that every curator has no email," prove it with a live audit (fetch the
  profile AND its linked site, show the bio text), don't fabricate a contact. Being able
  to say with evidence "X routes through management, Y is DM-only" is a feature, not a
  failure — and matches the no-fake-data rule.

## Automate it: multi-engine web search + identity verification (bulk / app-integrated)
When you must find emails for MANY targets (e.g. a roster of curators/labels/artists)
and the source platform (SoundCloud/Spotify) has none, don't hand-scrape each — build a
batch finder that searches the whole web and VERIFIES each hit belongs to the right
person/entity before you save or send to it:
- **Query matrix:** for each target run `("<name>" | "<handle>") × (email | booking |
  contact | submissions | business | management | @gmail | @outlook | ...)`. Name AND
  platform handle both matter — the handle often surfaces the real booking address.
- **JS-free engines only** for reliability from a script: DuckDuckGo **lite**
  (`lite.duckduckgo.com/lite/?q=`) is the workhorse — it returns real external links,
  and even when link parsing fails, the raw page text still contains the surfaced email
  (verified live: `"trapnation" email` → `bookingtrapnation@gmail.com` straight in
  snippets). Fall back to `html.duckduckgo.com`, Bing, Google. Bing/Google/Startpage are
  heavily JS-walled from servers; don't depend on their HTML.
- **Harvest every candidate** with the page it came from; also crawl the entity's own
  linked pages, YouTube about, ZoomInfo, contact directories, Discord, Bridge.audio.
- **VERIFY identity before auto-saving** — this is the step most people skip and it's
  what makes bulk email usable safely. Score each candidate by: (a) domain matches the
  entity's own site, (b) local-part or domain contains their handle (e.g. `trapnation@`),
  (c) local-part echoes any name token, (d) the page context mentions their handle/name,
  (e) the address was found on their own domain. Auto-save only ≥0.4; list below-threshold
  ones for manual pick instead of guessing wrong and pitching the wrong person.
- **Noise filter** (`noreply@`, `sndcdn`, `@2x`, `.png/.jpg` false-positives) so you never
  persist a junk address.

This is the same logic the download-gate site uses (`email_finder.py` in the AC PE$0
app — see the `soundcloud-download-gate-site` skill's `references/gate-verify-and-ops-gotchas.md`).

## Reference Files
- `references/dan-martell.md` — Full contact map built for Dan Martell (July 2026 session), including discovery methods and ranked contact paths.
- `references/multi-source-verified-email-finder.md` — the batch multi-engine + identity-verification finder pattern (query matrix, engine reliability, scoring rubric), condensed from the AC PE$0 curator email-pull work.

## Pitfalls
- X Search / social search tools may be unavailable (API credits); fall back to direct curl scraping
- Modern JS-heavy sites (Next.js, React) render nothing useful in curl output — check the raw HTML for schema/JSON-LD blocks instead
- GDPR WHOIS redaction means domain records rarely have personal info anymore
- Personal cell numbers are almost never publicly listed; the best find is usually a team/business line
- A helper that gets passed the WRONG config object (a sibling settings dict without a bare `client_id` key) crashes with an opaque `KeyError` and silently "does nothing" — always feed a helper its own settings object
- "creds exist" ≠ "scope granted": an OAuth consent minted before a scope change (e.g. adding `gmail.readonly`) still 403s on the new scope until re-consent. Verify granted scopes via `oauth2.googleapis.com/tokeninfo`, don't infer from config presence.