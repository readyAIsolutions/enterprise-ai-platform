# AI release auto-tagging + promo kit — implementation detail

Reference build: AC PE$0 site (`~/Desktop/ac pe$0`, Starlette :8533). Companion to the
SKILL.md section "AI release auto-tagging + promo kit (upgrade #3, free-router)".

## Purpose
SoundCloud FFP tracks arrive with messy all-caps titles and `genre='Free For Profit'`
placeholder + empty bpm/key/description. The AI tags fill these from the title using the
local free-router (`http://127.0.0.1:8920/v1/chat/completions`, model `free-router`,
zero-cost). Goal: clean public cards + real genres so AI-curator-match has signal.

## Files touched (this build)
- `aiwriter.py` — `tag_release()`, `_parse_json_object()`, `_genre_hint()`, `_clean()`
- `server.py` — `admin_ai_tag_release`, `admin_ai_tag_all`, `admin_ai_promo_kit`,
  `_sanitize_tags()`, `_normalize_genre()`, `GENRE_WHITELIST`; route registration
  `/admin/ai-tag-release`, `/admin/ai-tag-all`, `/admin/ai-promo-kit` (all POST, JSON out)
- `db.py` — `clean_title` column via idempotent `_migrate` ALTER; `update_release_fields()`
  partial-update helper; `upsert_release` now persists `clean_title`
- `templates/*.html` — `{{ r.get('clean_title') or r.title }}` in index/releases/
  free_for_profit/release pages; admin edit form gains clean_title input + per-release
  "⚡ Tag" and "⚡ Promo kit" buttons + "⚡ AI tag all" toolbar
- `static/app.js` — handlers for `data-ai-tag`, `data-ai-tag-all`, `data-promo-kit`,
  `showPromoKit()` modal (Copy + Insert-into-editor)
- `static/style.css` — `.row-msg`, `.promo-overlay`, `.promo-box`, `.promo-piece`

## `_sanitize_tags()` contract (the load-bearing guard)
Never mirror AI output into the DB unvalidated. Live-caught failures: `bpm='Can'`,
and a CoT sentence as the genre value.
```
bpm:     accept only if numeric float in (0, 300]; store int when whole
genre:   _normalize_genre() -> whitelist match ONLY (else drop)
songkey: free text, cap 80 chars
clean_title: cap 80 chars
description: cap 500 chars
empty/whitespace strings are always dropped
```

## `_normalize_genre()` / GENRE_WHITELIST
Compact known labels: trap, drill, pluggnb, plugg, rage, phonk, cloud rap, detroit,
jersey club, boom bap, lo-fi hip hop / lofi, hip hop, rap, electronic, edm, dubstep,
house, ambient, instrumental, trap metal, hardstyle, uk drill, afrobeat.
- exact lowercase match first, then longest-substring match (so "trap metal" wins over "trap")
- return "Lo-Fi" for the `lofi` alias; `.title()` the rest
- return "" if nothing matches (garbage never lands in the DB)

## `tag_release()` parse strategy
1. `_chat_raw(prompt, max_tokens=700)` asking for a compact JSON object.
2. `_parse_json_object()` — scan for balanced `{...}` spans; keep the LAST that
   `json.loads` cleanly (reasoning model narrates earlier). Never trust the first `{`.
3. Fallback: marker-mode `_chat()`, then regex `key:value` pairs, then `_genre_hint(title)`
   + `_clean(title)`.

## Routes & JS shape
- Each route: `_need_admin` guard → read `release_id` from form → call generator →
  `_sanitize_tags` → `db.update_release_fields(rid, **save)` → `JSONResponse({ok, ...})`.
- Never 303-redirect from an AI route — the JS needs the JSON to fill textareas.
- JS: `URLSearchParams` POST, `credentials:'same-origin'`,
  `Content-Type: application/x-www-form-urlencoded`, disable button + show loading while
  the ~5-10s generation runs, inline `.form-msg ok/err`.
- Promo kit: `_try(name, fn)` per generator so one failure doesn't kill the bundle; return
  `{ok, kit:{pitch,social,tiktok,blog,newsletter}, errors:{}}`; render with `escHtml()`.

## Tag-all skip logic (do not copy the naive version)
`needs_tag = force OR (not genre) OR genre.lower() in ('free for profit','ffp') OR not (bpm and songkey)`
Checking `not (genre and description)` alone skips everything because the FFP sync pre-fills both.

## Deployment quirk (the `$` in the path)
`~/Desktop/ac pe$0` — Bash expands `$0` inside double-quoted `cd "..."`, corrupting it to
`~/Desktop/ac pe/usr/bin/bash...`. Use `subprocess.Popen(["python3","server.py"], cwd=wd,
start_new_session=True)` via a neutral-path launcher, or escape with `~\Desktop\ ac\ pe\$0`.
The terminal tool rejects a `workdir` containing `$`. Give the fresh listener ~2-5s before
probing; an immediate restart can hit `address already in use` if the old pid's port didn't
release. Test plan: create an admin session row directly in the DB, use its token as the
`acpeso_admin` cookie to call the JSON routes, then `pytest` (18 pass).
