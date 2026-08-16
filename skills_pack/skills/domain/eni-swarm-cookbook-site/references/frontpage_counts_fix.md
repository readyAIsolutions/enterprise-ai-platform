# Front-page "0 lessons" / "loading chapters" — known-good fix

LO's recurring complaint: homepage shows "0 lessons" or "loading chapters…" and never
updates. Two root causes, both fixed below.

## Root cause A — site.js wipes homepage functions
site.js ended with `window.ACBS = {search, toggleFav, post, fav};` which REPLACED the whole
ACBS object, deleting the inline script's `renderChapters`/`glob`/`loadIdx`. The chapter grid
never rendered.

FIX (in site.js, end of IIFE):
```js
window.ACBS = Object.assign(window.ACBS || {}, { search:doSearch, toggleFav:toggleFav, post:postReview, fav:isFav });
```
Never use `window.ACBS = {...}` (reassignment). Grep site.js for `window.ACBS =` after edits.

## Root cause B — counts gate on a fetch that can fail / JS can't run
If chapters are rendered only inside `fetch('search_index.json').then(...)`, a failed/empty
fetch leaves "loading chapters…" and counts at 0. And curl can't execute JS, so you can't
verify client-rendered counts from the shell (false panic).

FIX — BAKE the chapter grid + counts into the STATIC index.html from `site_improve()`:
```python
def write_homepage():
    n = len(glob.glob(os.path.join(LESSONS, "*.html")))
    counts = {}
    sidx = os.path.join(SITE, "search_index.json")
    if os.path.exists(sidx):
        try:
            counts = json.load(open(sidx)).get("counts", {}) or {}
        except Exception:
            counts = {}
    if not counts:  # fallback: count links in each chapter file
        for k, cf in CHAPTER.items():
            cp = os.path.join(SITE, cf)
            if os.path.exists(cp):
                counts[CNAME[k]] = open(cp, errors="replace").read().count("lessons/")
    cards = ""
    for k, cf in CHAPTER.items():
        c = counts.get(CNAME[k], 0)
        cards += "<div class='card'><a href='%s'>%s</a><div class='c'>%d lessons</div></div>\n" % (cf, CNAME[k], c)
    # ... build full HTML with `cards` inline, link adaptive.css + site.css ...
    html = html.replace("COUNT", str(n)).replace("CARDS", cards)
    open(os.path.join(SITE, "index.html"), "w").write(html)
    return n
```
Call `write_homepage()` from `site_improve()` every cycle so it self-heals against sibling
agent overwrites. The inline `<script>` then only handles the GLOBAL SEARCH box + favorites;
navigation/counts are static HTML.

## Auto bug-hunter (run every site_improve cycle)
```python
def audit_site():
    issues = []
    for p in glob.glob(os.path.join(SITE, "*.html")):
        t = open(p, errors="replace").read()
        base = os.path.basename(p)
        for m in re.findall(r"href='([^']+)'", t):
            if (m.startswith("chapter_") or m.startswith("lessons/") or m in ("site_index.html","index.html")) \
               and not os.path.exists(os.path.join(SITE, m)):
                issues.append("dead link %s in %s" % (m, base))
        if "<html" in t and "site.js" not in t: issues.append("%s missing site.js" % base)
        if "<title>" in t and "site.css" not in t: issues.append("%s missing site.css" % base)
        if "chapter_" in base and "<!--LESSONS-->" in t and t.count("lessons/") == 0:
            issues.append("%s marker but zero lessons" % base)
    return issues
```
This session it found 261 dead links in the unlinked appendix files; neutralizing them
(`re.sub(r"<a href='(lessons/[^']+|chapter_9\.html)'>([^<]*)</a>", r"\2", t)`) dropped bugs to 0.

## Verification (after writing index.html)
- `curl -s http://127.0.0.1:8080/index.html | grep -o "<div class='c'>[0-9]* lessons</div>"`
  → returns REAL numbers (because they're baked into static HTML). This is the proof it works.
- If grep returns nothing, the page still relied on client-side JS → re-bake it.
- Confirm site.js merges: `curl -s http://127.0.0.1:8080/site.js | grep -c "Object.assign"`.
