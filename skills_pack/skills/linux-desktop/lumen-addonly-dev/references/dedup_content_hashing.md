# Dedup content-hashing for the LUMEN wallpaper library

Condensed technique from LM01 cycle 2026-07-11 (`lumen/library_dedup.py`).
Reuse this whenever a LUMEN task needs "find duplicate wallpapers / reclaim
disk from the Steam Workshop library" — it is the safe, headless way.

## Goal
Find duplicate wallpaper packs in `~/.local/share/lumen/wallpapers` WITHOUT
false deletes. A duplicate = two folders that render identically (a renamed
re-import, a re-subscribe of the same Workshop item).

## The hash
- `content_hash` = SHA-256 over the concatenated bytes of EVERY regular file
  in the wallpaper folder EXCEPT:
  - `lumen.json` / `project.json` (the manifest) — it carries the unique
    `id`, so hashing it makes a renamed re-import hash DIFFERENTLY from the
    original even though its shader is byte-identical. This is the #1 trap.
  - `preview.gif` (shared animated placeholder present in many packs;
    including it causes false exact-matches).
- `meta_hash` = SHA-256 over normalized metadata only (name, author, kind,
  sorted tags, description, original_type) — NO id. Drives "near-duplicate"
  detection (same thing described, different bytes, e.g. a re-upload with a
  tweaked shader source).
- If a wallpaper has no local files (pure URL), `content_hash` falls back to
  `meta_hash` and `size_bytes = 0`.

## Why "hash ALL renderable files", not a media-extension whitelist
First attempt used a whitelist (`_MEDIA_EXTS = png/jpg/mp4/...`) to find the
"content" file. That MISSED shader entries: a shader wallpaper's renderable
file is `shader.html` / `index.html` / `.glsl`, none of which are media
extensions. Result: folder had only `shader.html` + `lumen.json` -> empty
file list -> `content_hash` fell back to meta -> every shader falsely matched
by metadata. Fix: enumerate ALL files in the folder, skip only the manifest +
`preview.gif`, hash the rest. This covers `.html`/`.glsl`/`.png`/`.mp4`
uniformly and makes "same folder contents" = duplicate (exactly right for
re-imports), while "shares a shader but differs in any asset" becomes a
near-dup (safe: user reviews, nothing auto-deleted).

## Safety properties to preserve
- `remove()` is `dry_run=True` by default — never deletes, only echoes.
- Every removal target must be `relative_to(root)`; an out-of-root path
  (e.g. `/etc/passwd`) is an ERROR, never executed.
- keeper priority: most-played (`library_stats.StatStore`, duck-typed) >
  Lumen-native folder (`lumen.json`) over WE symlink > newest manifest mtime
  > shortest id (deterministic tie-break).

## Deterministic test recipe (tmp_path, no real library)
- Build a fake lib root; `mkdir` each wallpaper; write `shader.html` + `lumen.json`.
- Two copies with identical `shader.html` but different folder name/id =>
  SAME `content_hash` (proves manifest exclusion works).
- Same name/author but different `shader.html` body => different `content_hash`,
  same `meta_hash` => near-dup.
- Assert `find_duplicates` returns exact group {a,b} and near group including c;
  `total_wasted_bytes == len(body)`.
- Assert `remove(dry_run=True)` leaves folders; `remove(dry_run=False)` deletes
  the non-keeper and spares the keeper; `remove([out-of-root])` records
  "outside library root".

## Where it lives / what NOT to rebuild
`lumen/library_dedup.py` (ADD-ONLY, ~430 LOC, 18 tests). Pairs with
`lumen/library_stats` (keeper = most-used) and `lumen/wallpaper_index`
(search/filter — NOT dedup; that's LM08's claim, don't rebuild it).
