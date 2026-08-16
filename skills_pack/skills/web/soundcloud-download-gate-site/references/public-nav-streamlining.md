# Public-site top-bar / nav streamlining (AC PE$0)

Reusable UI pattern + the owner's explicit style preference. Whenever you need to
clean up a crowded site header, split it into PRIMARY nav + a right-side ACCOUNT
cluster instead of one flat row of equal-weight links.

## Owner preference (durable, style-level)

LO wants the top bar "way more streamlined and easier to use": fewer links, clear
visual hierarchy, the action items (sign in / admin / history) visibly distinct from
the browse links. A bar that crams 9+ same-weight links is wrong. This is a standing
preference for this site's public chrome, not a one-off.

## The pattern (what was done)

Old bar: `Home · Releases · [FREE FOR PROFIT] · Beatpacks · Analyze · Community ·
Blog · Contact · <account links> · translate` — one flat row, nothing stood out.

New structure (`templates/base.html`):
- **Primary left nav** — browse-only links, shorter labels, `white-space:nowrap`:
  `Releases · Free for Profit · Beatpacks · Analyze · Community · Blog`.
  - Drop "Home" (the site wordmark/logo already links home).
  - Drop "Contact" from the bar (it lives in the footer) unless the owner wants it.
  - Soften shouting links: `[FREE FOR PROFIT]` → `Free for Profit` (keeps the red
    accent, drops the all-caps).
- **Right-side `.nav-cluster`** — the account zone, separated by a subtle divider
  (`border-left`) so it reads as a group, not more nav links:
  - Guest: a real **primary CTA pill** (`Sign in`) — filled accent, border-radius 999px.
  - Fan: `My downloads` + bordered ghost `Logout`.
  - Admin: `History` + red pill `Admin` + ghost `Logout`.
  - The Google-translate widget sits in the cluster (it's a utility, not navigation).

Key CSS: `.site-nav{display:flex;gap:1.1rem}` (tighten from 2rem); scope the red
underline hover to `.site-nav > a` / `.nav-cluster > a` only (buttons don't get it);
`.nav-cluster > a` `white-space:nowrap`.

Mobile (<=860px): the nav drops to a column menu; `.nav-cluster` stacks full-width
under the primary links with its own top divider, and CTA/Admin/Logout become centered
pills (`flex-direction:column`, `border-left:none`, `margin:auto`). Touch targets
`min-height:44px`.

## Verification

- Desktop: header height ~62px, no horizontal overflow
  (`nav.scrollWidth <= nav.clientWidth`), one clean row: 6 links + red pill + translate.
- Walk `getBoundingClientRect()` across nav items to confirm left-to-right ordering,
  the pill is truly a pill (borderRadius 999px, accent bg), and nothing overlaps.

## Cache-bust + restart

CSS/JS changes ship only after bumping the `?v=` on `style.css` / `app.js` in
`base.html` AND a service restart (`systemctl --user restart <svc>`). Confirm the new
version serves (`curl -s <origin>/ | grep -oE 'static/style.css\?v=[0-9]+'`), then tell
the owner to hard-refresh (Ctrl+Shift+R) once. All tests must stay green (93/93 here).
