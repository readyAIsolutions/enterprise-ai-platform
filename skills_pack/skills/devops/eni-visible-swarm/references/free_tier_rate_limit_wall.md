# FREE-TIER RATE LIMIT = HARD WALL for concurrent builder swarms (2026-07-11)

## The wall
OpenRouter's **free tier is ~8 requests/minute, ACCOUNT-WIDE** (not per-model, not
per-slug). Any swarm of N builders that each fork `hermes chat` and call the API
concurrently CANNOT exceed ~8 genuinely-progressing builders on the free tier.

Observed this session at N=64 (4 WS × 16 builders, all on hy3:free):
- 64 windows opened fine; ~56 of them got `HTTP 429: Rate limited after 8 retries`
  on the boot wave.
- The 429 retry storm (hermes retries 8×, `while true` restarts, retries again)
  SPAMMED each builder's log so hard that **`/tmp` hit its disk quota**
  (`OSError: [Errno 122] Disk quota exceeded`) → all 64 went black/idle because
  even the logs couldn't be written.
- This is distinct from the earlier watchdog-OOM crashes: here the floor came up
  but froze + filled the disk. Both are "too many API calls too fast."

## Why model rotation did NOT fix it
- qwen3-coder:free + llama-3.3-70b-instruct:free are ALSO throttled to ~8/min → 429.
- Switching ALL to hy3:free → still 429, because the limit is ACCOUNT-WIDE, not
  per-model. Rotating models just moves the stampede to the next slug.
- A global semaphore (only ~8 active at once) stops the crash + disk fill, BUT
  the other 56 still sit idle waiting their turn → you STILL see mostly black
  windows. There is no way to make 64 builders genuinely "all working" on free.

## The ONLY real options (presented to LO, 2026-07-11)
1. Cap to what the free tier allows (~8 active builders, rotating). Floor stays
   visible (64 windows) but only ~8 build at a time. No crash, no disk fill.
2. Reduce to a smaller real-working floor (e.g. 8–12 builders) that ALL build.
   Still 4 WS / 4-per-screen, just fewer per screen.
3. LO supplies a PAID OpenRouter key (or higher free-tier limit) → all 64 can run.
4. Keep 64 visible but do LOCAL work (code edits / tests / file writes) that
   doesn't need the API every cycle; call the model only occasionally.

## Detection / diagnosis recipe
```
# 1) Are builders 429'ing right now?
grep -l "429\|Rate limited" /tmp/eni_logs/*.log | wc -l      # how many stuck
ls -lt /tmp/eni_logs/*.log | head -5                          # are 429s recent?
# 2) Is the disk quota the wall?
df -h /tmp | tail -1
grep -rl "Disk quota exceeded\|Errno 122" /tmp/eni_logs/*.log # true if disk full
```
If 429 mtimes are >60s old and 0 in the last 60s, self-heal already recovered
those few — do NOT kill. If `Errno 122` appears, the disk is FULL: kill the
builders, `: > /tmp/eni_logs/*.log` to truncate, then relaunch with a cap.

## Crash-safe run-script pattern (what finally stopped the storm)
Per builder, in the self-heal `while true` loop:
- ONE-TIME random pre-boot `sleep $(( (RANDOM % 240) + 5 ))` BEFORE the loop
  (spreads 64 boots over ~4 min — NOT inside the loop, or every restart delays).
- On `429|Rate limited` in the proxy log: `sleep $(( (RANDOM % 120) + 90 ))`
  (90–210s jittered backoff) before retrying — never a tight 30s loop.
- RAM guard: `while [ "$(free -m|awk '/Mem:/{print $7}')" -lt 3000 ]; do sleep 15; done`
- LOG CAP: rotate each log to keep it under ~200KB so a 429 storm can't fill /tmp:
  `if [ "$(stat -c%s "$LOG")" -gt 204800 ]; then tail -c 150000 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"; fi`
- KILL-ONLY memory sentinel (separate daemon, never launches anything): when
  `free -m|awk '/Mem:/{print $7}'` < 1500, `pkill -9 -f 'hermes chat --yolo'`
  (biggest chat first) — a VALVE, not a relauncher, so it cannot runaway.

## The meta-rule LO set (verbatim preference — see SKILL.md pitfall)
Do NOT keep relaunching into the same known-failure wall (429 / disk quota /
OOM). If a launch produces black/idle terminals, DIAGNOSE the wall first
(rate limit? disk full? OOM?), explain it to LO, and present the real options
(model cap / smaller floor / paid key / local-only) instead of silently
re-running the same command and crashing his box again.
