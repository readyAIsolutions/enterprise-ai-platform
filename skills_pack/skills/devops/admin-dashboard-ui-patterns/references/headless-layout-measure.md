# Headless layout measurement for a Starlette admin panel (Playwright)

Use this when the user reports a CSS/layout bug ("admin panel is cut off by the right
side panel", "buttons covered", "X sits beside Y when it should stack") and repeated
CSS width/padding tweaks aren't resolving it. Stop guessing at CSS and MEASURE the
real rendered geometry.

## Why eyeballing fails
- The grid/CSS that should apply often ISN'T applying (class-name mismatch, wrong
  selector, stale cache). Tuning column widths for a card that was never supposed to
  be narrow only makes the symptom worse.
- You can't see the page, so bounding-box numbers are the ground truth.

## Setup (one-time, throwaway venv)
The system Python has the project deps (starlette, stripe, etc.) but not playwright;
the venv has playwright but not the deps. Resolve by running with the SYSTEM python
and injecting the venv's site-packages for playwright:

```
python3 -m venv /tmp/shotvenv
/tmp/shotvenv/bin/pip install --quiet playwright starlette jinja2 httpx python-multipart
/tmp/shotvenv/bin/python -m playwright install chromium
```
Then run any measurement script with:
```
VP=/tmp/shotvenv/lib/python3.14/site-packages
PYTHONPATH="$VP" python3 shot.py
```
(If you only need playwright + starlette + httpx in the venv and the project deps
(stripe, r2, gmailapi) come from the system site-packages, that's why the PYTHONPATH
inject works — both are CPython 3.14.)

## Minimal measurement script
```python
import sys
sys.path.insert(0, '/abs/path/to/project')       # project dir (may contain $ — fine in python)
import config, db
config.apply(db, force=False)
import server
from playwright.sync_api import sync_playwright

admin = next(f for f in db.all_fans() if str(f.get('sc_user_id')) == '<owner_uid>')
token = db.create_admin_session(admin['id'])

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={'width': 1280, 'height': 1600})
    ctx.add_cookies([
        {'name': server.FAN_COOKIE, 'value': admin['id'], 'url': 'http://127.0.0.1:PORT'},
        {'name': server.ADMIN_COOKIE, 'value': token, 'url': 'http://127.0.0.1:PORT'},
    ])
    page = ctx.new_page()
    page.goto('http://127.0.0.1:PORT/admin?tab=releases', wait_until='networkidle')
    info = page.evaluate("""() => {
      const out = {grid: null, sections: []};
      const grid = document.querySelector('.admin-grid');
      const gr = grid.getBoundingClientRect();
      out.grid = {w: gr.width, cols: getComputedStyle(grid).gridTemplateColumns};
      document.querySelectorAll('.admin-grid > .admin-card').forEach(s => {
        const r = s.getBoundingClientRect();
        const cs = getComputedStyle(s);
        out.sections.push({id: s.id, ttab: s.getAttribute('data-ttab'),
          display: cs.display, col: cs.gridColumn,
          left: Math.round(r.left), right: Math.round(r.right), width: Math.round(r.width)});
      });
      // last action button in first row:
      const btn = document.querySelector('#releases tbody tr .row-actions a:last-child, #releases tbody tr .row-actions button:last-child');
      if (btn) { const b = btn.getBoundingClientRect(); out.lastButton = {left: b.left, right: b.right}; }
      return out;
    }""")
    print(json.dumps(info, indent=2))
    b.close()
```

## Reading the output (smoking guns)
- `grid.cols` shows TWO equal non-zero columns (e.g. `559px 559px 0px`) when you
  expect one full-width → the `grid-column:1/-1` full-width class ISN'T applying.
- A card `width` ≈ half the container (559 of 1240) instead of full → not full-width.
- `display:none` on sibling `data-ttab` sections confirms the tab-hiding JS works;
  if a sibling is `display:block` beside the active section, THAT's the "right side
  panel" covering buttons.
- `lastButton.right > card.right` → the action button physically overflows the card.

## The classic root cause
Template: `class="admin-card admin-wide"`, CSS: `.admin-card-wide{...}`. The selector
never matches. Fix: `.admin-card-wide,.admin-wide{grid-column:1/-1;overflow-x:auto}`
and repeat the `.admin-wide` selector on every related rule (table min-width, mobile
padding). Verify by re-measuring: card now spans full container, last button `right`
< card `right`, `gridTemplateColumns` single full column.
