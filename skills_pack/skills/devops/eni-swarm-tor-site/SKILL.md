---
name: eni-swarm-tor-site
description: Build, operate, and keep-alive an ever-expanding self-hosted Tor hidden-service content site whose pages are generated forever by an "ENI swarm" Python worker pool. Covers the architecture (Tor HS + static server + forever-swarm generator), the self-contained-lesson content model, client-side search/favorites/anonymous-review, the swarm stall/dupe bugs, and the Tor egress-only descriptor caveat. Use when LO asks for a living site that grows itself (cookbook, wiki, knowledge base, any remastered archive) served over .onion with no external dependencies.
---

# ENI Swarm Tor Site (ever-expanding, self-hosted, .onion)

## When to use
LO asks for a site that "runs forever", "makes more of everything", "live updates", or any
self-growing knowledge base / cookbook / archive served privately. The model: a static file
server behind a Tor hidden service, fed by a Python swarm that loops forever generating
self-contained pages. No database, no CMS, no external API.

## Architecture (proven layout)
- `~/Desktop/tor-data/torrc` — `HiddenServiceDir`, `HiddenServicePort 80 127.0.0.1:8080`.
- Tor binary: user-compiled at `~/.torbin/torinstall/bin/tor` (no sudo). Boot:
  `~/.torbin/torinstall/bin/tor -f ~/Desktop/tor-data/torrc`.
- Static server: `python3 -m http.server 8080 --directory ~/Desktop/cookbook_site` (background).
- `~/Desktop/cookbook_site/` = web root. Chapters `chapter_N.html` (one per topic cluster) each
  hold a `<ul class='lesson'><!--LESSONS--></ul>` marker; the swarm inserts `<li><a>` before it.
- `swarm_expand.py` = the generator. Runs `while True: wave(); sleep(N)`. 8 workers, wave 12s.
- `search_index.json` = rebuilt each wave from all `lessons/*.html` (title→href). Drives global search.
- `site.js` + `site.css` = shared client features (search, favorites, reviews). Injected into
  every page head/end.

## Content model (self-contained, NOT appendix-linked)
LO's hard rule: every lesson must teach start-to-finish with NO external reference to chase.
- Each lesson HTML embeds: intro, "What to gather" dumb-simple list (item + where to buy it),
  gear paragraph, material paragraph, 14–22 full prose steps (domain banks: chem/build/radio),
  an inline "Reference data" block with REAL numbers, a safety block, a favorites host, a
  review host, and a `<script id='factcheck' type='application/json'>` with checkable ranges.
- NO appendix files. If a lesson needs a fact, write it IN the lesson. Appendix = dead weight.
- Fully descriptive prose, never short-form. Min ~1,200 words per lesson.

## Client features (all anonymous, localStorage, work over Tor)
- SEARCH: per-page input filters `a[data-lesson]` links; homepage global search loads
  `search_index.json` and filters in-memory.
- FAVORITES: `localStorage['acb_favs_v1']`, ★ toggles, "My Saved" view. No server, no account.
- ANONYMOUS REVIEW + FACT-CHECK: textarea per lesson; JS parses numbers, compares to the
  embedded `factcheck` JSON ranges (min/max/unit). ACCEPT (✓ VERIFIED, integrated) / FLAG
  (⚠ FLAGGED, disputed) / NOTE (no number). Posted claim stored in localStorage, rendered.
  The swarm itself can later ingest accepted reviews (out of scope but the hook exists).

## CRITICAL pitfalls (learned the hard way — do NOT repeat)
1. SWARM STALL (kills the "forever" promise): if `pick_title()` dedups on
   `cluster|title|voice` and the pool is exhausted, a `for` loop that can't find a free key
   either spins forever (no new files) or falls through to a same-slug return that OVERWRITES
   the existing lesson (count freezes, looks like dupes). FIX: when pool exhausted, generate
   VARIANT titles (`"{title} — {variant} variant"` + occasional cross-cluster combo) so the
   key+slug are always unique → new file, real growth. Also `USED.clear()` when `len>~60000`
   to bound memory over 24/7.
2. NO-DUPE GUARD: before writing, `if os.path.exists(lessons/{slug}.html): return`. Slug must
   include voice+variant so it's unique. This is what makes "no dupes" real.
3. APPENDIX-AS-REFERENCE IS A TRAP: linking lesson phrases to a separate appendix means broken
   cross-refs and unverifiable data. LO explicitly killed it. Embed facts inline.
4. HUGE SITE ORGANIZATION: do NOT dump every lesson as one flat `<li>` list on index.html —
   it becomes an unnavigable 5000-line slab and "doesn't show all lessons". Use a DASHBOARD
   homepage (chapter grid w/ live counts from search_index.json + global search box) and let
   each chapter page hold its own searchable `<!--LESSONS-->` list.
5. TOR EGRESS-ONLY DESCRIPTOR CAVEAT: on a box with no inbound (egress-only), the HS descriptor
   may never publish to HSDirs, so Android Tor Browser can't fetch it. Symptom: local curl 200
   but onion won't load off-box. Fix path: force fresh consensus / descriptor upload, or accept
   localhost-only. Don't promise worldwide onion reachability on an egress-only host.
6. DESTRUCTIVE DELETES: never `rm -f` files without asking. The harness BLOCKS `rm -f` and the
   user must consent. If cleanup is needed, state the files and ask, or do a targeted,
   user-confirmed removal. (This is a hard LO boundary — blocked command = stop, don't retry.)

## Swarm lesson template (skeleton)
```
<html><head>...<link rel=stylesheet href=site.css></head><body>
<nav id=navbar>...<div class=acb-search><input id=acb-search></div><a href=#fav>★ My Saved</a></nav>
<div id=content>
 <h1>{title} [{voice}]</h1>
 <p class=lead>{intro, self-contained, no appendix}</p>
 <h3>What this build actually is</h3><p>{cname} procedure...</p>
 {gather_html}   <!-- What to gather, dumb-simple, where to buy each -->
 <h3>Gear you will need</h3><p>{gear_par}</p>
 <h3>Material you will need</h3><p>{mat_par}</p>
 <h3>Procedure, described step by step</h3>{proc_pars}  <!-- 14-22 <p><strong>Step N.</strong>...</p> -->
 <h3>Reference data (self-contained, fact-checked inline)</h3>{facts_block}
 <h3>Cross-check and safety</h3>{safe_pars}
 <div id=fav-host></div><div id=rev-host></div>
 <script id=factcheck type=application/json>{fc_json}</script>
</div><script src=site.js></script></body></html>
```
Generator must: define `coherent(title, cluster)` (gear/materials matched to subject, never a
random pool), `steps_for(title)` (domain banks), `facts_for(title)` (real constants),
`factcheck_json(title)` (ranges), `gather_block(G,M)` (plain-language where-to-buy), and
`build_search_index()` each wave.

## Keep-alive
The swarm process must be launched background and treated as a daemon (never exits). If it dies,
relaunch. A wrapper that restarts on exit is ideal for true 24/7. Tor + static server are
separate background processes that must also stay up.

## References
- `references/swarm_template.py` — a condensed, known-good skeleton of swarm_expand.py (the
  coherent/stall-fix/dupe-guard/search-index pieces) to copy and adapt per project.
- `references/client_features.js` — the search + favorites + anonymous-review fact-check JS,
  reusable as site.js.
