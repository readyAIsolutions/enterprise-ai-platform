# Partial-staleness live signal — one fresh mtime among a sea of stale

**Scenario:** A fleet monitor run shows 49/50 builder STATUS files with mtimes
from 20+ days ago, but one builder (e.g. BUILDER_37) has a TODAY mtime. This is
a partial-liveness signal — at least one builder checked in recently.

**What it means:**
- The fresh file means a builder process (or its cron/watcher) is still running
  and writing STATUS updates, even if no user-level build work is happening.
- The stale sea around it means the rest of the fleet is either shut down,
  crashed, or its cron/watchers have stopped.
- If the fresh builder reports `[IDLE]` or `# STATE: IDLE`, it's alive but
  has no FIFO control channel and no directive — it's waiting for LO to
  dispatch work to it.

**Diagnostic steps:**

```bash
# 1. Find fresh vs stale
cd /home/hunter/Commander/eni_swarm/builds
find . -name 'STATUS_BUILDER_*.md' -mtime -1 | wc -l  # fresh in last 24h
find . -name 'STATUS_BUILDER_*.md' -mtime +1  | wc -l  # stale

# 2. Check if the fresh builder has a FIFO
ls -la /tmp/eni_ctl_BUILDER_$(ls -1t STATUS_BUILDER_*.md | head -1 | grep -oP '\d+') 2>/dev/null

# 3. Check if any builder processes exist (partial-liveness via proc table)
ps aux | grep -i 'builder\|STATUS' | grep -v grep

# 4. Check all FIFOs vs all STATUS files — which builders have control channels?
for f in STATUS_BUILDER_*.md; do
  num=$(echo "$f" | grep -oP '\d+')
  [ -p "/tmp/eni_ctl_BUILDER_$num" ] && echo "BUILDER_$num has FIFO"
done
```

**Interpretation:** A single fresh STATUS file in a stale fleet = the builder
infrastructure is mostly dead but one instance survived. The surviving builder
may be the best candidate to revive others if dispatched through its FIFO (if it
has one) or after creating its FIFO.