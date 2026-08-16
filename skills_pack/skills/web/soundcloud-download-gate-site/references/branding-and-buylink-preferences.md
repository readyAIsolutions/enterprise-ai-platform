# Branding & buy-link label preferences (acpeso)

Two durable site decisions that recur when LO asks for branding/tweak work.
Both are small but easy to get inconsistent if you only change one site.

## Buy-link "Free DL" label
When the admin "📬 Push buy links to SC tracks" button (or the auto-sync on
release create/edit) writes a release's SoundCloud metadata buy link, the
purchase_title is now `"Free DL"` — NOT the beat/release name.

- Both call sites in `server.py` must use the label together so they stay
  consistent: `_sync_release_buy_link` (auto on create/edit) and
  `admin_push_buy_links` (the bulk button). They both call
  `sc.update_track_buy_link(token, track_id, buy, purchase_title="Free DL")`.
- The buy URL is still `https://acpeso.shop/release/{slug}` (untouched).
- "Free DL" is well under SoundCloud's 22-char `purchase_title` cap, so no
  truncation worry. If LO ever wants a different label, change BOTH call sites.

## Brand font: commercial-safe blackletter + the shared --display-brand trick
LO picked **Qindret** (fontspace.com/qindret-font-f154566), a blackletter /
Old English typeface — great fit for the ♰/AC PE$0 occult-cross branding.
BUT it is licensed **PERSONAL USE ONLY (no commercial use)** and the site sells
beatpacks (commercial). Do NOT drop a personal-use font into a storefront.
Rendered instead with **UnifrakturCook** (OFL, free for commercial use, a close
blackletter lookalike).

Glyph check matters for a badge like "AC PE$0": confirm the font has `$`,
digits (`0`), and the letters before committing — verify with fontTools in a
throwaway venv (`python3 -m venv /tmp/fenv && fenv/bin/pip install fonttools`,
then inspect `TTFont(...).getBestCmap()`). UnifrakturCook has the full set.

THE KEY TRICK: the site already routes BOTH the corner wordmark (`.wordmark`)
and the front-page hero splash (`.hero-line`) through the single brand CSS
variable `--display-brand` in `static/style.css`. So one change re-fonts both:
```css
--display-brand:'UnifrakturCook','Anton','Space Grotesk','Inter',system-ui,sans-serif;
```
Plus add `family=UnifrakturCook:wght@700` to the Google Fonts `<link>` in
`templates/base.html`, and bump the CSS cache-bust version (base.html
`style.css?v=N`). Verify live with `document.fonts.check('"UnifrakturCook"')`
and `getComputedStyle('.wordmark').fontFamily`.

## LO dislikes decorative animations on hover (2026-08-02)
LO asked to remove the "animated sound waves" from the synth nav buttons. That
was the floating **equalizer bars** block — the `.site-nav > a::after` styling
with the four `scaleY`-animated bar gradients (`@keyframes eq`), which revealed
itself on `:hover`. Remove it wholesale (the overlay `::after` background, the
`:hover::after` opacity rule, and the `@keyframes eq`), not just mask it.
- Keep the subtle underline `::after` (a separate width-animated rule) if present.
- Confirm gone via DOM: `@keyframes eq`, `site-nav > a:hover::after` + `scaleY`,
  and the `width:14px;height:10px` bar background should all return false.
- General taste signal: LO wants tasteful, restrained motion — decorative
  animated micro-elements (equalizer bars, etc.) on hover are unwanted. Prefer
  the neon scanline / glow / lift effects that read as "alive but not noisy".
- Always bump the CSS cache-bust version + restart + confirm 200 after.

## General rule for this site class
- Any font/asset destined for a storefront that SELLS must be commercially
  licensed (OFL/SIL, commercial personal check) — never personal-use-only.
- Shared CSS variables (`--display-brand`) are the single source of truth for
  re-branding a whole site; find the variable before editing many selectors.
- Always bump cache-bust version + restart the systemd unit + confirm 200
  after a font/CSS/JS change.
