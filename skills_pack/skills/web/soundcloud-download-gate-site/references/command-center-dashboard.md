# Command Center dashboard (upgrade #6) — implementation detail

Reference build: AC PE$0 admin panel. Turns the scattered admin tabs into one
default landing view that surfaces actionable gaps. All verified live 2026-08-02.

## Why this is the right "AI upgrade"
An AI-flavored upgrade on an artist promo site isn't another button — it's
converting data the site ALREADY collects into decisions. The admin had KPI
numbers scattered across tabs but nothing answered "what should I do right now."
On the real DB this dashboard instantly showed two silent killers:
  - 16/16 releases had NO lossless file → every public Download button 404s.
  - 95 curators but only 3 had emails → outreach is DM-first.
Both were invisible before; now they're the first thing the artist sees, with
a fix link.

## db.py additions (keep each as its own helper + one aggregator)
- `fan_total_count()` — `SELECT COUNT(*) n FROM fans`. (The pre-existing
  `fans_total=len(db.fan_completed_releases("x"))` was a BUG — passing literal
  "x" always returned 0; replace with this.)
- `pitch_funnel()` — `GROUP BY pitch_status`; init all four buckets to 0 first
  so every status key always exists.
- `followups_due(days=7, limit=50)` — curators `pitch_status IN ('pitched',
  'followed_up') AND last_pitched_at>0 AND last_pitched_at < now-days*86400`,
  `ORDER BY last_pitched_at ASC LIMIT ?`. This is the outreach loop closer:
  pitch → nudge after N days → responded.
- `releases_missing_lossless()` — release is flagged if `lossless_file` is
  empty OR `Path(lf).is_file()` is False (the file vanished from disk).
- `dashboard_stats()` — returns one dict: downloads, fans, subscribers,
  releases_total, releases_featured, releases_missing_lossless, curators_total,
  curators_with_email, funnel, followups_due, emails_sent/total, by_release_top.

## server.py wiring
- `admin_main` context adds `dash=db.dashboard_stats()` and
  `followup_days=int((db.get_setting("followup_days") or 7))`.
- `followup_days` is a normal settings key: add it to the `admin_settings`
  save-loop tuple so POST /admin/settings persists it, and render an editable
  number field in Settings.
- Because `dashboard_stats()` is called inside `admin_main`, a crash there
  500s the ENTIRE admin panel — keep the loader defensive and unit-test the
  aggregation.

## admin.html dashboard section
- Nav: `<a href="#dashboard" data-tab="dashboard" class="{{ 'active' if tab=='dashboard' else '' }}">Dashboard</a>` FIRST (before releases = default landing).
- Section: `<section class="admin-card admin-wide" id="dashboard" data-ttab="dashboard">`.
- KPI row: reuse `.stat-row .kpi-row` with `.stat` cards; add `.stat-ok` /
  `.stat-hit` variants and `.badge-err` (only `.badge-ok`/`.badge-warn` existed).
- Follow-up queue table reuses the EXISTING `.curator-status` dropdown markup
  (`data-status-curator="{{cu.id}}" data-current="..."`) so the existing JS
  handler (`querySelectorAll('[data-status-curator]')`) binds it with zero
  new JS.
- Release-readiness rows deep-link to the fix: `<a href="/admin?edit={{r.id}}#releases">Attach lossless</a>`.

## app.js
- `currentFromHash()`: add `if (h === 'dashboard' || h === '') return 'dashboard';`
  and change the final fallback from `'releases'` to `'dashboard'` so an empty
  hash lands on the dashboard.

## style.css
- `.kpi-row{grid-template-columns:repeat(auto-fit,minmax(120px,1fr))}`
- `.stat-ok` / `.stat-hit` border+numeric-color variants
- `.badge-err{background:rgba(255,43,62,.15);color:#ff2b3e;border:1px solid rgba(255,43,62,.4)}`
- Bump `style.css?v=` and `app.js?v=` cache-busters in base.html.

## Tests added (all in tests/test_site.py)
- `test_dashboard_stats_aggregates` — every key present; funnel has all four;
  `curators_total == sum(funnel.values())`.
- `test_followups_due_only_aging_pitched` — old pitched → flagged; fresh
  pitched → NOT; responded → never (even if old).
- `test_releases_missing_lossless_flags_broken_downloads` — no file → flagged;
  file on disk → not flagged.
- `test_dashboard_tab_renders` — authenticated /admin?tab=dashboard contains
  the section headings.
- `test_followup_days_setting_saved` — POST /admin/settings persists it.

## The two gotchas that bit (each cost a cycle)
1. **sqlite3.Row has no `.get()`.** `db.conn()` sets `row_factory=sqlite3.Row`,
   so `fetchall()` gives Row objects, not dicts. `r.get("title")` on a raw row →
   `AttributeError: 'sqlite3.Row' object has no attribute 'get'` → 500s
   admin_main → whole admin panel down. The aggregation UNIT test still passed
   (it doesn't render the template with full data) while the LIVE /admin 500'd.
   Rule: in db.py, when looping raw rows use `r["col"]`, not `r.get()`.
2. **A running server keeps OLD code after a patch.** Re-verifying against the
   live server before restarting reproduced the original failure and looked
   like the fix didn't work. Kill + relaunch (Python launcher / bg session due
   to the `$`-in-path quirk), wait ~2-5s, confirm the port, THEN verify.
