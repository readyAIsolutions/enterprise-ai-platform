# Recovery Recipe — flooded / corrupted ENI swarm site

When the swarm has produced garbage or the site is broken (chapters empty or
clobbered, search dead, "building but nothing new"), run this in order.

## 1. Stop the swarm + watchdog (kill by PID, never self-matching pkill)
```bash
ps -eo pid,args | grep "swarm_expand" | grep -v grep | awk '{print $1}' > /tmp/sp.txt
while read p; do kill "$p" 2>/dev/null; done < /tmp/sp.txt
# also kill watchdog if present, by PID from the same ps listing
# DO NOT: pkill -f "swarm_expand"  (the pattern is in your own command -> kills shell)
sleep 2
ps -eo pid,args | grep "swarm_expand" | grep -v grep | wc -l   # expect 0
```

## 2. Bulk-move garbage out (non-destructive) — use find -exec, NOT mv glob
`mv lessons/*.html archive/` fails with "Argument list too long" past ~tens of
thousands of files.
```bash
cd ~/Desktop/cookbook_site
mkdir -p archive_lessons
find lessons -maxdepth 1 -name '*.html' -exec mv {} archive_lessons/ \;
echo "lessons/ now: $(find lessons -name '*.html' | wc -l)"   # expect 0
```
Nothing is deleted — archive_lessons/ is fully recoverable.

## 3. Rebuild empty chapter shells + reset index
Build all 34 chapter files with this shape (per cluster, fill CNAME/CHAPTER maps
from the swarm source's CNAME/CHAPTER dicts):
```html
<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{CLUSTER_NAME} — Anarchist Cookbook Remastered</title>
<link rel='stylesheet' href='site.css'><link rel='stylesheet' href='assets/style.css'>
<style> /* :root vars, #navbar fixed 260px, #content margin-left 280px,
  ul.lesson list-none, .idx muted, @media(max-width:820px) navbar static */ </style>
</head><body>
<nav id='navbar'><h2>SITE NAV</h2><a href='index.html'>▲ Home / TOC</a>{NAV_LINKS}<a href='site_index.html'>Master Index</a></nav>
<div id='content'><h1>{CLUSTER_NAME}</h1>
<p class='lead'>Builds generated live by the ENI swarm. Refresh to see new entries.</p>
<div class='acb-search'><input id='q' placeholder='search this chapter…' onkeyup='acbFilter(this.value)'><span id='search-count'></span></div>
<ul class='lesson'>
<!--LESSONS-->
</ul></div>
<div id='fav-view'></div>
<script src='site.js'></script>
</body></html>
```
Then: `json.dump({"items":[],"counts":{},"updated":"fresh"}, open("search_index.json","w"))`

## 4. Fix the generator before relaunch
- Kill cross-cluster title compose. In `pick_title()`, the exhausted-pool branch must
  ONLY do `title = f"{title} — {v} variant"` (v from VARIANTS) — NEVER
  `f"{title} — {v} variant, with {t2...}"` pulling t2 from a different cluster.
- Keep `MAX_LESSONS` (~2000) + no-overwrite guard (`if os.path.exists(fpath): return`).
- Single process default (WORKERS=20), in-process `threading.Lock` around batch flush.
- `python3 -m py_compile swarm_expand.py` MUST pass before launch.

## 5. Relaunch + verify
```bash
# launch as tracked background process (NOT nohup in foreground — harness blocks it)
python3 ~/Desktop/cookbook_site/swarm_expand.py   # via terminal(background=true)
sleep 40
find lessons -name '*.html' | wc -l          # climbing (was 0)
# sample titles clean? no cross-cluster suffix
find lessons -name '*.html' | head -3 | while read f; do grep -o "<title>[^<]*" "$f"; done
curl -s http://127.0.0.1:8080/chapter_1.html | grep -c "lessons/"   # > 0
python3 -c "import json;json.load(open('search_index.json'))" && echo "index OK"
```

## Tor liveness check (do NOT curl the onion)
```bash
grep -i "INTRODUCE2" ~/Desktop/tor-data/notice.log | tail -3
# rising "received N v3 INTRODUCE2 cells" = real clients connecting. SocksPort 0
# means curl --socks5 to the onion returns 000 by design — not a failure.
```
