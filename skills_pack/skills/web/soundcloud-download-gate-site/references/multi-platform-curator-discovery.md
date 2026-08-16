# Multi-platform curator discovery (SoundCloud + Deezer)

Tested live 2026-08-02 on the AC PE$0 site. Goal: find playlist curators /
labels / producers for cold outreach across ALL platforms, not just SoundCloud.

## What is actually reachable (public, no API key)

### 1. SoundCloud — source 1 (works)
Public profile pages embed the follower count in JSON (`"followers_count":N`).
Search /followers /following pages are JS-rendered (no embedded data). Discovery
bounded by seed list + repost/creator links in profile-page HTML. Yield ~10-20
new real >=5000-follower profiles per run.

### 2. Deezer — source 2 (works, open API, no key)
- `GET https://api.deezer.com/search/playlist?q=<term>&limit=50` → playlist
  `id`, `title`, and `fans` (which is **always null** in search results).
- `GET https://api.deezer.com/playlist/{id}` → the **full object** with the real
  `fans` count. You MUST fetch the full object to get followers.
- Treat playlist `fans` as the curator's `followers` for the threshold filter.
- **Rate limit:** Deezer throttles by IP after a short burst. A ~10-fetch loop
  succeeds on a fresh window; a 30+ burst returns valid JSON with empty/erroring
  data. Cap full-object fetches per run (~30) and sleep ~0.1s between them.
- **Honest yield:** Deezer playlists rarely clear 5,000 fans (mostly small
  personal lists), so it adds ~1-3/day at the 5000 threshold — real but small.

### 3. NOT scrapeable without API keys (tested, don't retry blindly)
- **YouTube:** search is JS-rendered. `ytInitialData` channelRenderer JSON came
  back empty for a search; `/oembed?url=https://www.youtube.com/@Handle` returned
  404. Channel subscriber counts not reliably extractable publicly.
- **Instagram / TikTok:** login-walled.
- **Spotify:** needs an OAuth client credential for API access.

## Deezer scanner snippet (known-good shape)
```python
DEEZER_API = "https://api.deezer.com"
DEEZER_QUERIES = ["type beat", "trap", "hip hop playlist", "instrumental", "free beats", "drill"]
DEEZER_FETCH_CAP = 30

def _dz_json(path):
    return json.loads(fetch(DEEZER_API + path, JSON_UA))  # urllib, UA Mozilla/5.0

def deezer_candidates():
    out, seen, fetched = [], set(), 0
    for q in DEEZER_QUERIES:
        if fetched >= DEEZER_FETCH_CAP: break
        try:
            p = _dz_json("/search/playlist?q=" + urllib.parse.quote(q) + "&limit=50")
        except Exception:
            continue
        for pl in p.get("data", []):
            if fetched >= DEEZER_FETCH_CAP: break
            pid, name = pl.get("id"), (pl.get("title") or "").strip()
            if not pid or not name or name.lower() in seen: continue
            seen.add(name.lower())
            try:
                full = _dz_json(f"/playlist/{pid}")
            except Exception:
                continue
            fetched += 1
            out.append(((full.get("title") or name).strip(),
                        full.get("link") or "",
                        int(full.get("fans") or 0), "deezer"))
            time.sleep(0.1)
    return out
```

## CRITICAL dedup bug (silently zeroes Deezer output)
DO NOT `seen.add(search_title)` before fetching the full object and then re-check
`nm.lower() in seen` after, where `nm = full.get("title")`. The full title == the
search title, so EVERY candidate is already in `seen` and gets skipped → the
function returns 0. Only dedup against the pre-fetch name, or drop the post-fetch
check entirely. Symptom: identical inline loop works, but the function returns 0.
Add a fetch-call counter / print the number of `_dz_json` calls to spot it fast.

## Roster tagging
Add a `found_via` column (soundcloud|deezer|manual) + a Source column in the
admin roster so LO sees multi-platform coverage. Backfill old rows:
```sql
UPDATE curators SET found_via='soundcloud'
WHERE source='found' AND (found_via IS NULL OR found_via='')
  AND contact_url LIKE '%soundcloud.com%';
```
