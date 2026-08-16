# Owner's Daily Briefing — upgrade #7 recipe (AC PE$0, 2026-08-02)

A self-sending morning digest that watches the whole artist operation and
emails the owner what to do. Reuses everything already in the site (data +
Gmail + free-router), so it's ~120 lines and fully testable via dry-run.

## Files
- `briefing.py` (new, site root) — compose + send.
- `server.py` — two routes + `owner_email` settings key.
- `templates/admin.html` — briefing card in the Command Center dashboard +
  "Daily briefing recipient" field in Settings.
- `static/app.js` — Preview / Dry-run / Send handlers.
- Cron job `acpeso-daily-briefing` (08:00 daily) runs `python3 briefing.py --send`.

## Module shape (mirror newsletter.py)
```python
def owner_email():            # owner_email setting else gmail from
def _ai_leadline(dash, followups, missing):  # best-effort AI one-liner
def build_briefing(ai_lead=True):   # -> (subject, plain, html)
def _settings():              # gc_* + smtp_* + signature keys for send_email
def send_briefing(dry_run=True, to_override="", ai_lead=True):  # -> dict
# CLI: python3 briefing.py [--send] [--to x] [--no-ai]
```

## Key data (all via db.dashboard_stats())
- KPIs: downloads, fans, subscribers, releases_total, releases_featured
- funnel: not_pitched/pitched/followed_up/responded
- followups_due (stalled > followup_days)
- releases_missing_lossless (the 404 gap)

## Server routes
```python
# GET  /admin/briefing-preview  (JSON, auth-gated, ai_lead=False)
# POST /admin/briefing-send     (dry_run=1 preview else real; 303 -> ?tab=dashboard)
```
Register both in the route table. Add `owner_email` to the `admin_settings`
save-loop tuple so Settings can persist it.

## Dashboard UI
Buttons: `data-briefing-preview` (fetch GET, render JSON into a pre-wrap box),
`data-briefing-send` with `data-dry="1"` for dry-run (POST; on 302/303/redirect
just `window.location.href='/admin#dashboard'` so the flash message shows).

## Tests (add to tests/test_site.py)
- build_briefing(ai_lead=False) -> subject/plain/html contain KPIs + "NEEDS ATTENTION"
- owner_email() default vs setting override
- send_briefing(dry_run=True) -> sent 0, no side effect
- /admin/briefing-preview 401 unauth, 200+JSON+`to` for admin

## Pitfall: `\$` is NOT a Python escape
`"AC PE\$0 · Daily briefing — {day}"` leaves a literal backslash + emits
`SyntaxWarning: invalid escape sequence`. Write `$` plainly in Python strings
(`$` is bash-special, never Python-special). Fix a file with
`sed -i 's/\\\$/\$/g' briefing.py`.

## Pitfall: sqlite3.Row has no .get()
If a new helper loops raw `c.execute().fetchall()` rows and calls `r.get(...)`,
the live `/admin` 500s (`AttributeError: 'sqlite3.Row' object has no attribute
'get'`) even though unit tests pass (the aggregation test used helper-returned
dicts). Use `r["col"]` on raw rows. (See upgrade #6 in SKILL.md.)
