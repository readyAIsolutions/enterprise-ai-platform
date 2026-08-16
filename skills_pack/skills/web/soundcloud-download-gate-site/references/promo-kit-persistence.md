# Promo kit persistence — save / reopen / new + full "Insert into editor"

The AI promo kit (one `/admin/ai-promo-kit` call that generates pitch + IG caption +
TikTok caption + blog blurb + newsletter blurb for a release) was originally a
throwaway modal: closing it lost everything, and "Insert into editor" only wired
`pitch`, `blog`, and `newsletter` — so `social`/`tiktok` silently did nothing.
This upgrade made the kit persistent and made insert work for every piece.

## DB layer (db.py)
- New table (idempotent in `_migrate`, with a `_table_exists(c, name)` helper):
  ```
  promo_kits(id TEXT PRIMARY KEY, release_id TEXT, name TEXT DEFAULT '',
             pitch TEXT DEFAULT '', social TEXT DEFAULT '', tiktok TEXT DEFAULT '',
             blog TEXT DEFAULT '', newsletter TEXT DEFAULT '', created_at REAL, updated_at REAL)
  ```
  Note: kit pieces are stored as **columns**, not one JSON blob — simpler to read/update
  per-piece and to query.
- Helpers: `get_promo_kit(kid)`, `promo_kits_for(release_id=None)`,
  `delete_promo_kit(kid)`, and `save_promo_kit(data)` which **upserts by id**
  (create when no id, UPDATE when the same id is passed — that's how "re-save
  overwrites" works). `promo_kit_fields(data)` extracts the 5 piece fields + name + release_id.
- **Auto-name when blank:** in the save route, if no `name` was given, generate
  `"<clean_title> — <Mon DD HH:MM>"` from the release + timestamp and re-save so the
  Load list shows a readable label, not "Draft ".

## Routes (server.py)
- `POST /admin/promo-kit/save` — body is **JSON** (`await request.json()`), read:
  `{release_id, name?, id?, pitch, social, tiktok, blog, newsletter}` → `{ok, kit_id, name}`.
- `GET /admin/promo-kits?release_id=...` — returns `{ok, kits:[...]}` (omit release_id to get all).
- `GET /admin/promo-kit/{kid}` — `{ok, kit:{...}}`.
- `POST /admin/promo-kit/{kid}/delete` — `{ok}`.
- Register all four (and keep `/admin/ai-promo-kit`). Note the `{kid}` path param
  routes: `save` is a distinct path (`/admin/promo-kit/save`), so no conflict with the `{kid}` capture.

## Front-end (app.js) — the drawer rewrite
- On "⚡ Promo kit" click: call `/admin/ai-promo-kit`, then `showPromoKit(rid, j.kit, null)`
  (third arg = saved kit id, null for a fresh unsaved kit).
- `showPromoKit` builds a modal with a **controls bar** (Kit name input + Save kit /
  Start new kit / Load saved… + status span) and, on Load, a saved-kits `<select>`
  with Open / Cancel / Delete. Module globals track `currentKit`, `currentKitId`,
  `currentRelId`.
- **Keep edits in sync** with an `overlay.addEventListener('input', ...)` that writes
  every `[data-kp-key]` textarea's value back into `currentKit`, so Save always
  captures what the user edited.
- **Save** reads the textareas into a payload, adds `id` if `currentKitId`, POSTs JSON
  to `/admin/promo-kit/save`, sets `currentKitId = j.kit_id` and fills the name input.
- **New** clears `currentKit`/`currentKitId`/name and the textareas.
- **Load** GETs `/admin/promo-kits?release_id=`, fills the select, and **Open** GETs
  `/admin/promo-kit/{id}` and writes the kit's pieces back into the textareas.

## "Insert into editor" MUST have a target for EVERY piece
The old code only handled `pitch` (release `textarea[name="body"]`), `blog`
(`#blog textarea[name="body"]`), and `newsletter` (`[data-ttab="settings"] textarea[name="body"]`)
— `social` and `tiktok` had no editor and silently no-op'd.
- **Add real target editors:** the release pitch panel (`templates/admin.html`,
  `data-release-pitch="{{ r.id }}"` form) now has `Instagram caption`
  (`<textarea name="social">`) and `TikTok caption` (`<textarea name="tiktok">`)
  rows so every kit piece has somewhere to land.
- The insert handler maps by `data-kp-key`: pitch→`textarea[name="body"]`, social→`name="social"`,
  tiktok→`name="tiktok"`, blog→`#blog textarea[name="body"]`, newsletter→`[data-ttab="settings"] textarea[name="body"]`,
  all scoped under the release's `pitch-row-{rid}` (fall back to the first `[data-release-pitch]` form).
- After inserting pitch, also un-hide the pitch row + flip its toggle so the artist
  can see/send it. If no matching editor is found, show "No editor found — copied instead"
  instead of silently doing nothing.
- Always `escHtml()` AI text before injecting into `innerHTML`.

## Verify
- POST save → 200 `{ok, kit_id, name}`; GET list returns it; GET item returns the pieces.
- Re-POST the same `id` → overwrite confirms (`pitch` comes back edited).
- DELETE → list count returns to 0.
- Render `/admin?tab=releases` and assert `name="social"` and `name="tiktok"` exist in
  the pitch panels.
- Clean up test kits + admin sessions afterward (they create rows / sessions in the DB).
- Bump `app.js?v=` + `style.css?v=`.
