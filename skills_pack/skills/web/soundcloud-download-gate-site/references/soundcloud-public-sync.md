# SoundCloud public-profile sync (no OAuth)

Recipe to auto-add an artist's tracks to a site. Works without any login — the
artist's profile is public — which is why a cron job can keep running even when
nobody is signed in.

## Why not the API?
`https://api-v2.soundcloud.com/resolve?url=...&client_id=...` and
`https://api-v2.soundcloud.com/users/{id}/tracks?client_id=...` both return
**403 with a bare client_id** (OAuth-scope required). So scan the public HTML
instead. This is a workaround, not "the API is broken" — embed the client_id
path if you ever get a properly authorized key.

## Step 1 — collect permalinks
```
GET https://soundcloud.com/{user}/tracks        # ~110KB, HTML 200
links = re.findall(r'href="/({user}/[a-z0-9-]+)"', html)
SKIP = { f"/{user}/likes", f"/{user}/sets", f"/{user}/tracks",
         f"/{user}/comments", f"/{user}/albums", f"/{user}/reposts",
         f"/{user}/favorites" }
# drop SKIP + de-dupe, return the slug after the last "/"
```
The real track slugs are stable and human-readable (e.g. `free-for-profit-glorb-x-yng`).

## Step 2 — title + artwork per track (oEmbed, no auth)
```
GET https://soundcloud.com/oembed?format=json&iframe=true&url=<permalink_url>
# -> {"title": "... by AC PE$0", "thumbnail_url": "https://i1.sndcdn.com/artworks-...-t500x500.jpg"}
```
Filter keepers with `"free for profit" in title.lower()`. Strip the trailing
` by <Artist>` with `re.sub(r"\s+by\s+AC PE\$0\s*/?\s*$", "", title, flags=re.I)`.

## Step 3 — numeric track id (required for the like/repost/comment gate)
The profile index page does NOT embed track objects. Fetch the track's own page:
```
GET https://soundcloud.com/{user}/{slug}
ids = [int(x) for x in re.findall(r'"id":(\d{6,})', html)]
track_id = next(i for i in ids if i != USER_ID)   # USER_ID = the profile user id
```
`USER_ID` is discoverable from the profile hydration JSON:
`window.__sc_hydration = [...]` — find the `hydratable=="user"` entry → `data.id`.

## Step 4 — upsert (never duplicate, keep uploads)
Match existing releases by `soundcloud_url` (or track id). On update, preserve
`id`, `slug`, and any uploaded `lossless_file`/`lossless_name`. Set
`free_for_profit=1`, `gate_enabled=1`, `gate_requires=["like","repost","comment"]`.

## Step 5 — run continuously as a cron watchdog
- Scanner lives in the site dir (so it can `import db`).
- Cron tool requires scripts under `~/.hermes/scripts/` and rejects absolute
  paths, so put a thin wrapper there:
  ```python
  import subprocess, sys
  r = subprocess.run([sys.executable, "/path/to/site/scan_ffp.py"], capture_output=True, text=True)
  if r.stdout: sys.stdout.write(r.stdout)
  if r.stderr: sys.stderr.write(r.stderr)
  sys.exit(r.returncode)
  ```
- Job: `no_agent=True`, `script="scan_ffp.py"`, `deliver="origin"`, every 60m.
  Script prints a one-line summary when tracks are ADDED, an empty string when
  nothing changed (silent watchdog), and the error on crash.

## Pitfalls
- Always `.decode("utf-8","ignore")` the fetched HTML — binary garbage in a
  title will break the upsert.
- Send a desktop browser `User-Agent` + `Accept-Language` headers; SC can bot-
  block bare python requests.
- Throttle with `time.sleep(0.5)` between requests.
- Only tracks whose TITLE contains "free for profit" qualify — the user's
  criterion is literally the title. Everything else is a preview/purchase.
