# Home-page crafted sections (featured releases + featured beatpacks)

Pattern for surfacing curated content on a storefront-style artist home page so
the admin doesn't have to hand-edit HTML. Builds on `_ctx_base` already passing
the full lists into the template context.

## The setup that makes this free
`server.py::_ctx_base` injects BOTH lists into EVERY page's template context:
```python
"releases": db.all_releases(),
"beatpacks": kw.pop("beatpacks", db.all_beatpacks())
```
So the home template (`index.html`) already has `beatpacks` available even
though the original home page only rendered `releases`. No server change is
needed to add a beatpack section to the home page.

## Curate with a `featured` flag, fall back to first N
The `featured` boolean column exists on both releases and beatpacks. In the
template, build a filtered list and fall back gracefully so the section never
renders empty/blank:
```jinja
{% set feat_packs = [] %}
{% for bp in beatpacks %}
  {% if bp.get('featured') %}{% set _ = feat_packs.append(bp) %}{% endif %}
{% endfor %}
{% if not feat_packs and beatpacks %}{% set feat_packs = beatpacks[:3] %}{% endif %}
```
Wrap the whole `<section>` in `{% if feat_packs %}` so it disappears entirely
when there is nothing to show (better than an empty grid).

## Reuse the release card markup
The beatpack card is the same `.release-card` grid used for releases, but with
an extra `.card-price` line (price or FREE) and track count instead of BPM.
Copy the beatpacks page card, don't invent a new one, so hover/grid/`overflow-wrap`
behaviors stay consistent.

## Pitfall: `.card-price` / `.money` may be unstyled
The beatpacks page renders `class="card-price"` and `class="money"` but if the
store predates a shop-style price line, there may be NO CSS rule for them, so
price renders as bare unstyled text. Grep before assuming styling exists:
```
grep -n "card-price\|\.money" static/style.css
```
If 0 matches, add minimal rules (theme vars) and bump the CSS cache-bust `v=`:
```css
.card-price{font-weight:700;font-size:.95rem;color:var(--text)}
.card-price .money{color:var(--accent)}
```

## Cache-bust + verify
- Bump `style.css?v=N` in `base.html` after any CSS change (browser caches by URL).
- Restart the service (systemd user unit), curl the new `?v=` returns 200, and
  snapshot the live page to confirm the new section appears with the Featured badge.
- Hard-refresh caveat for the OWNER's own browser: cached old JS/CSS can mask the
  fix, so tell them Ctrl+Shift+R once after a version bump.
