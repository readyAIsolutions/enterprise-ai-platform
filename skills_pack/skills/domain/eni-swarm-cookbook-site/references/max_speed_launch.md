# Max-Speed Multi-Process Launch (ENI Swarm Cookbook)

Proven on LO's 24-core / 32GB box. Single-process threads = 38 lessons/min (GIL-bound).
Multi-process = ~760 lessons/min. The watchdog keeps N processes alive 24/7.

**⚠ READ FIRST — the unguarded multi-process run CORRUPTED the site.** 7 processes
appending to the same chapter files + rewriting `search_index.json` with no lock ate the
`<!--LESSONS-->` markers, dropped `site.js`, and truncated the index → "chapters don't
exist, can't search." Plus an uncapped variant generator produced 62,000 garbage files.
ONLY do multi-process behind a global fcntl lock + atomic index writes + a MAX_LESSONS
cap (see below). A single capped process is the safe default.

## swarm_launch.sh (spawn N independent processes)
```bash
#!/bin/bash
SITE=~/Desktop/cookbook_site
cd "$SITE" || exit 1
PROCS=${1:-6}
echo "[launch] starting $PROCS swarm processes"
for i in $(seq 1 $PROCS); do
  nohup python3 "$SITE/swarm_expand.py" >> "$SITE/swarm.out" 2>&1 &
  echo "[launch] proc $i pid $!"
done
wait
```

## watchdog.sh (keep N processes alive forever)
```bash
#!/bin/bash
SITE=~/Desktop/cookbook_site
cd "$SITE" || exit 1
TARGET=${1:-6}   # number of swarm processes to keep running
while true; do
  running=$(pgrep -f "python3 $SITE/swarm_expand.py" | wc -l)
  if [ "$running" -lt "$TARGET" ]; then
    need=$((TARGET - running))
    echo "[watchdog $(date)] $running/$TARGET up — starting $need" >> "$SITE/watchdog.log"
    for i in $(seq 1 $need); do
      nohup python3 "$SITE/swarm_expand.py" >> "$SITE/swarm.out" 2>&1 &
    done
  fi
  sleep 15
done
```

## swarm_expand.py constants for overnight MAX
```python
LESSON_SLEEP = 4
WORKERS = 70
MAX_LESSONS = 2000   # MANDATORY — without this the variant generator floods the disk
```
For steady state drop to `WORKERS=20, LESSON_SLEEP=6` (or run 1-2 watchdog procs).

## MANDATORY guards before ANY multi-process run
1. `MAX_LESSONS` cap in `write_lesson`: `if len(os.listdir(LESSONS)) >= MAX_LESSONS: return`.
2. `MAX_LESSONS` cap + no-overwrite guard (`if os.path.exists(fpath): return`) — already
   there, but the CAP is what stops the 62k flood.
3. Wrap chapter appends + index writes in `fcntl.flock` so concurrent processes don't
   clobber each other's writes.
4. `build_search_index()` writes via temp file + `os.replace` (atomic) — never a direct
   `open(...,"w")` on the live `search_index.json`.

## Integrity check AFTER launch (do not skip)
```bash
# chapter still has its marker + script + links?
grep -c "<!--LESSONS-->" ~/Desktop/cookbook_site/chapter_1.html
grep -c "site.js" ~/Desktop/cookbook_site/chapter_1.html
# index parses?
python3 -c "import json; d=json.load(open('~/Desktop/cookbook_site/search_index.json')); print('items', len(d['items']))"
# homepage search loads?
curl -s http://127.0.0.1:8080/index.html | grep -c "globsearch"
```
If marker/script missing or index fails to parse → the race happened; stop the swarm,
repair chapters (restore `<!--LESSONS-->` + inject `site.js`/`site.css`), and rebuild the
index from disk.

## Launch
```bash
# do NOT launch swarm directly — launch the watchdog, it spawns + supervises:
bash ~/Desktop/cookbook_site/watchdog.sh 6 &
```
Note: `pkill -f "watchdog.sh"` can kill its own parent shell (the command string
contains "watchdog.sh"). Use `pkill -f "python3.*swarm_expand"` to stop workers, or
kill the watchdog PID specifically.

## Measure rate
```bash
before=$(ls ~/Desktop/cookbook_site/lessons/*.html|wc -l)
sleep 45
after=$(ls ~/Desktop/cookbook_site/lessons/*.html|wc -l)
echo "rate: $(( (after-before)*60/45 )) lessons/min"
```

## Dedup across processes
`write_lesson` must `if os.path.exists(fpath): return` (hard no-overwrite). Each
process has its own USED set; cross-process uniqueness is guaranteed by the file-exists
guard, not by shared state. **The file-exists guard does NOT protect shared files like
chapter pages or `search_index.json`** — those still need an `fcntl.flock` around the
append/write, or you get the corruption this session hit. Prefer a single capped process
unless you've added the lock.
