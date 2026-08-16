# Owner (LO) preferences — non-negotiable for this site

Durable user preferences from 2026-08-02. Encode these BEFORE touching the site.

## 1. Front-page text is LO-owned and PERMANENT
- Tagline, hero_kicker, hero_desc, newsletter_heading/sub, and OG copy are set
  ONLY by LO through Admin → "Save front page text". They stay exactly as set
  until LO changes them.
- NEVER auto-edit, reword, regenerate, or "improve" this copy in any task,
  even when fixing unrelated bugs.
- Admin `admin_settings` must honor "blank = keep current" for the front-page
  group (server.py `front_page_keep_blank` = tagline, hero_kicker, hero_desc,
  newsletter_heading, newsletter_sub): a blank submitted box leaves the stored
  text untouched; only a field with a NEW value updates it. Regression test:
  `test_front_page_text_blank_keeps_current`.

## 2. Top-bar / nav buttons stay READABLE (phone + desktop)
- Do NOT apply decorative display fonts (blackletter / UnifrakturCook, ornate,
  heavy text-shadow) to the top nav links OR the corner wordmark.
- This was an actual bug twice: the SF `--display-brand` (UnifrakturCook)
  leaked onto `.wordmark` (fixed #67) and onto the synth `.site-nav > a`
  buttons (fixed #69) — both made the top bar unreadable.
- Fonts that work: primary nav + right-side cluster = Space Grotesk / Inter;
  corner wordmark = Anton. Keep any "synth key" visual flourishes (red gradient,
  neon border, glow ring, scanline) but the TEXT must be crisp (no text-shadow
  blur, no uppercase-everything, normal letter-spacing).
- The big decorative hero splash may keep a display/blackletter font; UI chrome
  (nav, buttons, input labels, tables) must not.
- Always hard-bump the CSS cache-bust version (`style.css?v=N`) when changing CSS
  and restart the server; verify computed font-family in the live DOM, not just
  the source.

## 3. Never fabricate / always best-effort with safe fallbacks
- Payment/email paths must never block the core action: wrap fulfillment email,
  fan sync, buy-link push, dollar-amount scans in try/except so an outage doesn't
  break the download or page render. (Already the site's standing convention.)
