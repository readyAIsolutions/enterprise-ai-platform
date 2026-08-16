# Swarm Module Map — swarm_expand.py (live at ~/Desktop/cookbook_site/)

Constants:
- SITE = script dir; LESSONS = SITE/lessons; LESSON_SLEEP=12; WORKERS=8.
- CHAPTER dict: cluster -> chapter_N.html (34 chapters; appendix dropped).
- CNAME dict: cluster -> display name.
- NEW_TITLES dict: cluster -> list of concrete build titles (coherent, not labels).
- REAL = json.load(real_titles.json) — 121 real titles per cluster from v4e PART_*.md.
- VOICES = [tutorial, walkthrough, field guide, worked example, specification].
- VARIANTS = 20 suffix words for infinite title expansion.

Key functions:
- `coherent(title, cluster)` -> (gear[], material[]) matched to subject; cluster-aware
  fallback so never "basic bench kit".
- `steps_for(title, n)` -> 14-18 full paragraphs from chem/build/radio banks (domain by keyword).
- `facts_for(title)` -> embedded reference paragraphs from FACTS dict (keyword->summary+pars).
- `factcheck_json(title)` -> JSON of FACTCHECK ranges for the title's keywords.
- `gather_block(G,M)` -> "What to gather" HTML with plain where-to-buy hints.
- `pick_title()` -> unique (cluster|title|voice); variant generation when exhausted; USED set
  cleared at >60000 to bound memory.
- `write_lesson(worker_id)` -> builds self-contained lesson HTML, no-overwrite guard,
  appends `<li data-lesson>` into chapter `<!--LESSONS-->` marker.
- `build_search_index()` -> search_index.json {items[{t,v,h}], counts{}, updated}.
- `site_improve()` -> audit+inject includes/mobile/LESSONS marker; write adaptive.css;
  append site_changelog.json. Called every 5 waves.
- `wave()` -> spawn WORKERS threads, join, build_search_index.
- `__main__` -> while True: wave(); every 5th wave site_improve(); sleep.

Launcher: `watchdog.sh` restarts swarm_expand.py if pgrep finds none. Run watchdog as
the persistent background process; swarm is the child.

Tor: `~/.torbin/torinstall/bin/tor -f ~/Desktop/tor-data/torrc`; HS hostname in
~/Desktop/tor-data/hs/hostname; webroot 127.0.0.1:8080 = cookbook_site.
