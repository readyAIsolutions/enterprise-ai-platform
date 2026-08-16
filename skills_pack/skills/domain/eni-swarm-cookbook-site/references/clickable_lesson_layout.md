# Clickable 4-Section Lesson Layout (lesson_render.py)

LO's final format: ONE page, ONE coherent example, four clickable accordion sections.

## The four sections
- `[1] Tutorial` (open by default, `checked`): gather list + gear + material + numbered DO-IT steps.
- `[2] Field Guide`: tools + sourcing, materials + sourcing, environment notes, reference data.
- `[3] Walkthrough`: one narrated example build ("First, … then … finally …").
- `[4] Specification`: `<table class='spec'>` of hard numbers (from factcheck JSON) + safety block.

## Accordion mechanics (CSS inside render_lesson `<style>`)
```
.acc{border:1px solid #222;border-radius:8px;margin:14px 0;background:#161616;overflow:hidden}
.acc>input{display:none}
.acc>label{display:block;cursor:pointer;padding:14px 18px;font-size:17px;color:#c8a24a;font-weight:bold;background:#1b1b1b;border-left:3px solid #c8a24a}
.acc .body{max-height:0;overflow:hidden;transition:max-height .35s ease;padding:0 18px}
.acc>input:checked~.body{max-height:9000px;padding:14px 18px}
.acc>label::after{content:'+';float:right;color:#888}
.acc>input:checked~label::after{content:'–'}
```
Section block shape:
```
<div class='acc'><input type='checkbox' id='s1' checked><label for='s1'>[1] Tutorial — step by step, how to build it</label><div class='body'> … </div></div>
```
Pure CSS checkbox-toggle (no JS) — works even if site.js fails. Labels use PLAIN TEXT TAGS
(`[1] Tutorial`), never emoji/unicode, to avoid the `\ud83d` literal corruption.

## render_lesson signature
```
lesson_render.render_lesson(title, voice, cluster, worker_id, today, G, M, steps,
                             facts_block, fc_json, safe_pars, nav_links,
                             chapter_file, cname, bill_of_materials)
```
- Split `steps` → `tool_lines` (start with `TOOLS:`/`SOURCE:`) and `build_steps` (rest).
- `proc_pars` + `walkthrough_text(build_steps)` use build_steps ONLY.
- `tool_lines` rendered into Field Guide (after env note), NOT as numbered steps.
- Keep `<div id='fav-host'>` + `<div id='rev-host'>` + `<script src=site.js>` for favorites/reviews.

## Bulk-clean literal \uXXXX corruption (run when inheriting broken files)
```python
import glob, os
repl = {"\\u2014":"—","\\u2013":"–","\\u25b2":"▲","\\u2190":"←","\\u00b7":"·",
        "\\ud83d\\udcdc":"[1]","\\ud83e\\udead":"[2]","\\ud83d\\udede":"[3]","\\ud83d\\udccf":"[4]"}
for f in glob.glob("lessons/*.html"):
    s=open(f,encoding="utf-8",errors="replace").read(); n=s
    for k,v in repl.items(): n=n.replace(k,v)
    if n!=s: open(f,"w",encoding="utf-8").write(n)
```
Match key is `"\\u2014"` (one backslash) — the on-disk literal is a single backslash + `u2014`.
After cleaning, re-run `rewrite_existing_lessons` so TOOLS-filter + Walkthrough fixes apply.
