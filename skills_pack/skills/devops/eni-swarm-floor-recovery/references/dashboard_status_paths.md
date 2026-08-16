# Dashboard STATUS path fix (visible floor / paint_dashboards.sh)

When relaunching the visible swarm floor via `paint_dashboards.sh`, the xterm
boards will show every builder as "(not started)" unless the dashboard scripts
point at the real STATUS dirs. Two bugs, both fixed this session:

Bug A — wrong base path. `gen_dash()` in `gen_floor_opt.sh` writes
`f=/home/hunter/STATUS_$n.md`, but builders write STATUS into per-PRODUCT dirs
(NOT /home/hunter). So every lookup misses.

Bug B — case-sensitive state grep. The grep `'\[state: [A-Z-]+\]'` only matches
lowercase `state:` but STATUS files use `State: RUNNING` (capital S) → the state
column reads `# STATUS` instead of the real state. Make it case-insensitive.

## Per-product STATUS dir map (verified)
- SB  -> /home/hunter/Commander/demiurge_scaffold/STATUS_SB*.md
- D3D -> /home/hunter/Desktop/demiurge-3d/STATUS_D3D*.md
- NAS -> /home/hunter/demiurgenas_stash/STATUS_NAS*.md   (NOTE: differs from its repo)
- LUM -> /home/hunter/Desktop/apps/lumen/STATUS_LUM*.md

## Fix 1 — live dash scripts (instant, no regen)
Edit each `/tmp/eni_opt/dash_<KEY>.sh`. Change:
  f=/home/hunter/STATUS_$n.md
to the product dir above, e.g. for D3D:
  f=/home/hunter/Desktop/demiurge-3d/STATUS_$n.md
And change the state grep to case-insensitive:
  st=$(grep -m1 -oiE '\[?state: [a-z-]+\]?|# STATUS' "$f" | head -1)

## Fix 2 — generator (so a future regen stays correct)
In `gen_floor_opt.sh`, inside `gen_dash()`, replace the `f=` + `st=` block with a
candidate search (in the UNquoted heredoc, keep `\$n` / `\$f` escaped so they are
written literally into the generated dash script):

    f=""
    for cand in /home/hunter/STATUS_\$n.md /home/hunter/Commander/demiurge_scaffold/STATUS_\$n.md /home/hunter/Desktop/demiurge-3d/STATUS_\$n.md /home/hunter/demiurgenas_stash/STATUS_\$n.md /home/hunter/Desktop/apps/lumen/STATUS_\$n.md; do [ -f "\$cand" ] && { f="\$cand"; break; }; done
    if [ -f "\$f" ]; then
      st=\$(grep -m1 -oiE '\[?state: [a-z-]+\]?|# STATUS' "\$f" | head -1)

## Verify (one-shot, no xterm needed)
for k in SB D3D NAS LUM; do
  f=$(ls /home/hunter/STATUS_${k}1.md \
        /home/hunter/Commander/demiurge_scaffold/STATUS_${k}1.md \
        /home/hunter/Desktop/demiurge-3d/STATUS_${k}1.md \
        /home/hunter/demiurgenas_stash/STATUS_${k}1.md \
        /home/hunter/Desktop/apps/lumen/STATUS_${k}1.md 2>/dev/null | head -1)
  st=$(grep -m1 -oiE '\[?state: [a-z-]+\]?|# STATUS' "$f" 2>/dev/null | head -1)
  line=$(grep -m1 -vE '^\s*$|^#' "$f" 2>/dev/null | cut -c1-66)
  printf "%-5s -> %s | state=[%s] %s\n" "$k" "$f" "$st" "$line"
done
# expect State: RUNNING for all four, then pgrep -fc 'eni_agent_term[.]py' == 54

## Launch the visible boards (host only)
cd /home/hunter/Desktop/Commander/eni_swarm && DISPLAY=:0.0 bash paint_dashboards.sh
# opens 4 xterms pinned to monitor origins: SB +0+0, D3D +1920+0, NAS +4480+0, LUM +2274+1080
# builders run headless behind them; closing any xterm does NOT stop a builder.
