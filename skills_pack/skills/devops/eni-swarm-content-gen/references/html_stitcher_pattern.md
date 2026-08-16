# HTML stitcher pattern for ENI swarm content-gen (clickable book)

LO wants big generated docs readable AND clickable. LibreOffice opens HTML
(File > Open) and renders anchor links; browsers too. Replace the markdown
stitcher concatenation with an HTML assembler.

## Key-map trap (cost a relaunch this session)
`CLUSTER_TITLES` keys MUST equal `TOPICS` keys. A `moderntrades` title key
mismatched the real `modern` topic key → TOC showed raw "MODERN". Assert at
startup:
```python
assert set(CLUSTER_TITLES) == set(TOPICS), (set(CLUSTER_TITLES) ^ set(TOPICS))
```

## Minimal markdown → html (no deps)
```python
import re as _re, html as _html
def md_to_html(md):
    out, in_ol = [], False
    for line in md.splitlines():
        s = line.rstrip()
        if s.startswith("**") and s.endswith("**"):
            out.append(f"<p class='lead'>{_html.escape(s[2:-2])}</p>"); continue
        if _re.match(r"^\d+\.\s", s):
            if not in_ol: out.append("<ol>"); in_ol = True
            out.append(f"  <li>{_html.escape(s.split('.',1)[1].strip())}</li>"); continue
        if in_ol: out.append("</ol>"); in_ol = False
        if not s.strip(): continue
        out.append(f"<p>{_html.escape(s)}</p>")
    if in_ol: out.append("</ol>")
    return "\n".join(out)
```

## Assembler skeleton (in the stitcher loop)
```python
nav = ["<nav id='navbar'>", "<h2>THE BOOK v2</h2>",
       "<a href='#top'>Top</a>", "<a href='#toc'>Table of Contents</a>"]
body = ["<a id='top'></a>", "<h1>TITLE</h1>", "<p class='lead'>intro</p>", "<hr>"]
body.append("<a id='toc'></a><h2>Table of Contents</h2><ul>")
for i,(name,txt) in enumerate(chapters,1):
    cid=f"ch{i}"; title=CLUSTER_TITLES[name]
    nav.append(f"<a href='#{cid}'>{i}. {_html.escape(title)}</a>")
    body.append(f"<li><a href='#{cid}'>{i}. {title}</a></li>")
body.append("</ul><hr>")
for i,(name,txt) in enumerate(chapters,1):
    cid=f"ch{i}"; body.append(f"<a id='{cid}'></a><h2>CHAPTER {i}: {title}</h2>")
    for les in _re.split(r"\n## \[", txt)[1:]:
        les="## ["+les
        hm=_re.match(r"## \[(\w+)\] (.+?) — lesson \d+ \(([^)]+)\)\n", les)
        hdr=hm.group(2) if hm else "Lesson"
        content=les.split("\n",1)[1] if "\n" in les else ""
        content=_re.sub(r"Appendix A","<a href='#appa'>Appendix A</a>",content)
        body.append(f"<div class='lesson'><h3>{_html.escape(hdr)}</h3>{md_to_html(content)}</div>")
    body.append("<hr>")
# appendices: id='appa' / id='appb', split on "\n## Appendix A — " etc.
html_doc = (f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<style>#navbar{{position:fixed;left:0;top:0;width:260px;height:100vh;background:#111;padding:18px}}"
            f"#content{{margin-left:260px;padding:40px}}"
            f".lesson{{background:#161616;border:1px solid #222;border-radius:6px;padding:14px}}"
            f"a{{color:#888;text-decoration:none}} a:hover{{color:#c8a24a}}</style></head>"
            f"<body>{''.join(nav)}<div id='content'>{''.join(body)}</div></body></html>")
open(MASTER.replace('.md','.html'),'w').write(html_doc)
```

## Verify
- `grep -o "href='#ch1'"` and `grep -o "id='ch1'"` both return hits.
- `grep -c "class='lesson'"` is rising across re-stitches.
- First bytes are `<!DOCTYPE html>`.
- Open in LibreOffice (File > Open) to confirm links render.
