# ENI Swarm — Task Dispatch Layout & Live-Floor Pitfalls (2026-07-16 discovery)

## On-disk task file (VERIFIED this session)
- The ACTIVE task file the swarm reads is `~/Desktop/ENI Swarm/eni_build_tasks.json`
  (note the `ENI Swarm/` subdir — NOT `~/Desktop/eni_build_tasks.json` referenced by older skills;
  that path may be stale/legacy).
- Schema (each task = one builder assignment):
  ```json
  {"tasks":[{"name":"Lumen","title":"...","workdir":"/home/hunter/Desktop/apps/lumen",
             "model":"qwen/qwen3-coder:free",
             "task":"FULL-POWER build ... RESUME: read STATUS_X.md ... Write STATUS_X.md ..."}]}
  ```
- Builder names in the live floor: SB1-12 (STOCKBOT), NAS1-12 (DEMIURGE NAS),
  LUM1-12 (LUMEN), D3D1-18 (DEMIURGE-3D). Dashboards at `/tmp/eni_opt/dash_SB.sh`,
  `dash_NAS.sh`, `dash_LUM.sh` tail each builder's `STATUS_<NAME>.md`.
- Master coordinator: `~/Desktop/ENI Swarm/eni_master_driver.py` reads each mini's
  STATUS and posts contextual guidance to `/tmp/eni_ctl_<NAME>` FIFOs. The driver
  loops ~75s and is the "MASTER" seat — it does NOT recreate builders, only nudges them.

## PITFALL — do NOT hijack a live passing gate
The floor is often mid-run (e.g. STATUS_HUB_ENI.md shows a 4-program autonomous run
where some programs are GREEN and others mid-flight). If LO asks you to "use the ENI
swarm" for a NEW job (e.g. generating a big doc), do NOT:
  - kill/rewrite the live builders, or
  - edit the in-flight `eni_build_tasks.json` to swap in your task (corrupts a passing gate),
  - spawn visible builder terminals (OOM-risky on LO's memory-tight box; swap is full).
Instead, the SAFE paths:
  (a) For a doc-gen / non-code job: you ARE the swarm brain — fan out parallel WORKER
      PROCESSES yourself (Python multiprocessing.Pool, one worker per chapter cluster,
      write slices to disk, stitch). This mimics the swarm's split/fan/stitch pattern
      without touching the live floor. Proven this session: 9 workers, ~clean run, no
      floor collision.
  (b) For a real code build you want on the swarm: write a SEPARATE task JSON + launch
      DEDICATED builder terminals for that job only, leaving the live 4-program floor
      untouched. Do not mix into the running floor's task file.

## PITFALL — "godlike / 1000 pages" volume requests (doc-gen class)
When LO asks for an absurd page count ("make it 1000 pages of good stuff", "godlike"),
the correct response is NOT to fake-pad (loop sections with filler — he detects it and
it is not devotion) and NOT to refuse. Do:
  1. Build REAL, verified, deep content for the actual scope (every legacy entry carried
     with an honest verdict; modern additions flagged [NEW]).
  2. State the engineering reality plainly: a genuine 1000-page QUALITY book is a marathon
     generation, not a one-shot terminal job, and may OOM the box if forced inline.
  3. Offer the genuine path: incremental loop (append real sub-chapters per pass) OR
     dispatch through dedicated swarm builders. Let LO pick.
This session: the deep generator produced ~12 pages of dense real content; faking to
1000 would have been insulting. LO did not push back on the honest explanation — the
lesson holds: real + honest + offer-swarm > fabricated volume.

## Live-floor observation (2026-07-16)
- `ps aux` showed the SB/NAS/LUM dashboard xterms alive under `/tmp/eni_opt/`, driven by
  `dash_*.sh` while-true loops. The builders themselves are `eni_agent_term.py` proxies.
- `STATUS_HUB_ENI.md` is the autonomous completion report LO reads — it carries real
  PASS/FAIL numbers, not faked greens. Mirror that honesty in any deliverable you ship.
