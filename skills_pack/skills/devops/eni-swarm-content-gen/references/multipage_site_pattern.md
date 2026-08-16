# MULTI-PAGE SITE PATTERN (STEP 4c of eni-swarm-content-gen)

LO: "use the builders to make the website" / "make the appendix clickable like HTML".
A single 14MB `.html` is a monolith, not a site. Split into addressable pages.

## Files emitted into SITE_DIR
- `index.html` — home + live TOC (per-chapter lesson counts), links to every page.
- `chapter_NNN.html` — one page per cluster (split part file on `\n## [`).
- `appendix_A.html` / `appendix_B.html` — appendix builders' output as pages.
- `site_index.html` — master index across all chapters.
- `serve.sh` — `cd "$(dirname "$0")" && exec python3 -m http.server 8000`.

## Core helpers (put near stitcher)
```python
CSS = """<style>
:root{--bg:#0d0d0d;--fg:#e8e8e8;--acc:#c8a24a;--mut:#888;--box:#161616;}
*{box-sizing:border-box;}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 'Liberation Serif',Georgia,serif;}
#navbar{position:fixed;top:0;left:0;width:250px;height:100vh;overflow-y:auto;background:#111;padding:18px 14px;border-right:1px solid #222;}
#navbar h2{font-size:13px;color:var(--acc);letter-spacing:1px;margin:14px 0 6px;}
#navbar a{display:block;color:var(--mut);text-decoration:none;padding:3px 0;font-size:13px;}
#navbar a:hover{color:var(--acc);} #navbar .here{color:var(--acc);font-weight:bold;}
#content{margin-left:250px;padding:40px 48px;max-width:900px;}
h1{color:var(--acc);font-size:28px;border-bottom:1px solid #222;padding-bottom:10px;}
h2{color:#fff;font-size:21px;margin-top:36px;}
h3{color:var(--acc);font-size:16px;margin-top:24px;border-left:3px solid var(--acc);padding-left:10px;}
.lesson{background:var(--box);border:1px solid #222;border-radius:6px;padding:14px 18px;margin:14px 0;}
ol{margin:6px 0;padding-left:22px;} li{margin:3px 0;}
strong{color:#fff;} .idx{color:var(--mut);font-size:13px;}
hr{border:none;border-top:1px solid #222;margin:30px 0;}
a{color:var(--acc);}
</style>"""

def page(title, nav_html, body_html):
    return (f"<!DOCTYPE html>\n<html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{title} — Anarchist Cookbook v2</title>{CSS}</head>"
            f"<body><nav id='navbar'>{nav_html}</nav>"
            f"<div id='content'>{body_html}</div></body></html>")

def site_nav(current):
    links = [("<a href='index.html'>Home / TOC</a>", current == "index")]
    n = 0
    for name, _t in chapters:
        n += 1
        links.append((f"<a href='chapter_{n}.html'>{n}. {esc(CLUSTER_TITLES.get(name, name.upper()))}</a>",
                      current == f"chapter_{n}"))
    links.append((f"<a href='appendix_A.html'>Appendix A</a>", current == "appendix_A"))
    links.append((f"<a href='appendix_B.html'>Appendix B</a>", current == "appendix_B"))
    links.append((f"<a href='site_index.html'>Master Index</a>", current == "site_index"))
    out = ["<h2>SITE NAV</h2>"]
    for href, is_here in links:
        out.append(href.replace("<a ", f"<a class='{'here' if is_here else ''}' ", 1) if is_here else href)
    return "".join(out)
```

## Per-chapter loop
```python
n = 0
for name, txt in chapters:
    n += 1
    cbody = f"<h1>CHAPTER {n}: {esc(CLUSTER_TITLES.get(name, name.upper()))}</h1><hr>"
    for les in re.split(r"\n## \[", txt)[1:]:
        les = "## [" + les
        hm = re.match(r"## \[(\w+)\] (.+?) — lesson \d+ \(([^)]+)\)\n", les)
        hdr = f"{hm.group(2)} <span class='idx'>[{hm.group(3)}]</span>" if hm else "Lesson"
        content = les.split("\n", 1)[1] if "\n" in les else ""
        content = re.sub(r"Appendix A", "<a href='appendix_A.html'>Appendix A</a>", content)
        content = re.sub(r"Appendix B", "<a href='appendix_B.html'>Appendix B</a>", content)
        cbody += f"<div class='lesson'><h3>{esc(hdr)}</h3>{md_to_html(content)}</div>"
    cbody += "<hr><p class='idx'><a href='index.html'>Back to Table of Contents</a></p>"
    open(os.path.join(SITEDIR, f"chapter_{n}.html"), "w").write(page(f"Ch{n}", site_nav(f"chapter_{n}"), cbody))
```

## Verify
- `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/index.html` → 200
- same for `chapter_1.html`, `appendix_A.html` → all 200
- `grep -o "class='here'" chapter_1.html` → present (you-are-here marker)
- `grep -o "href='index.html'" chapter_1.html` → back-link present

## Pitfall
SINGLE-FILE-ONLY IS NOT A SITE. LibreOffice/old browsers choke on 14MB and there's no
per-chapter nav. The multi-page split is the fix. Build `page()` + `site_nav()` once.
