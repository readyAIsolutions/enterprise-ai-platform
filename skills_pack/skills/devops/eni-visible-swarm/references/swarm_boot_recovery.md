# ENI Swarm Boot Recovery (2026-07-11)

Condensed, copy-pasteable recovery kit for a dead swarm floor after reboot/logout.
Companion to the SKILL.md "SWARM BOOT RECOVERY SOP" section.

## Symptom inventory — why "terms don't work" + "desktop won't log back in"
1. **LightDM has no autologin** → greeter waits forever → X never starts → XFCE autostart
   never fires → no swarm. THIS is the #1 cause of "won't log back in".
2. **swarm_start.sh launches a missing swarm_watchdog.sh** (only the `.DISABLED` copy
   exists) → nothing paints.
3. **gen_run_scripts.sh is incomplete** → it must generate `heart_WS*`/`master_WS*`/
   `run_*`/`status_*` (NOT just `run_*`/`master_heartbeat`). A floor with missing
   run-scripts = empty/dead terminals.
4. **No wait-for-X** → paint races ahead of X and fails silently.
5. **No @reboot net + /tmp can be cleared** → floor can't self-recover.
6. **64 provisioned builders (ENI1..ENI64 + PL)** → booting all 64 `hermes chat` agents
   at once OOMs this memory-tight box.
7. **(CRASH ROOT CAUSE) title-grep global re-paint loop**: xfce4-terminal `--title` does
   NOT reliably stick in `wmctrl -l`, so grep-by-title dedup ALWAYS reports "missing" →
   a 30s re-paint loop relaunches the entire floor forever → hundreds of windows → OOM.

## Fix sequence (the working boot chain)
- `sudo bash /home/hunter/setup_autologin.sh` → LightDM autologin + no lock. REQUIRED or
  the desktop never logs in. (Cannot be done from the agent sandbox — it needs root.)
- `gen_run_scripts.sh` → generates ALL run-scripts dynamically from
  `~/.cache/eni_parallel/task_ENI*.txt` (skips `_w*` subtasks) + `task_PRODUCT_LEAD.txt`.
- `swarm_watchdog.sh` (crash-safe v2, ACTIVE) → `wait_for_x` → gen → paint ONCE →
  30s PID-tracked self-heal loop.
- `swarm_start.sh` → PID-guarded single-instance launcher.
- crontab `@reboot` + XFCE autostart (`Delay=10`) = double-trigger, no silent death.

## Reusable technique: place a window by ID (NEVER by title)
xfce4-terminal `--title` does NOT stick in `wmctrl -l`, so find the new window's ID by
diffing `wmctrl` before/after launch, then place by ID:

```bash
spawn_window(){
  local title="$1" ws="$2" X="$3" Y="$4" W="$5" H="$6"; shift 6
  local before after wid pid
  before=$(wmctrl -l 2>/dev/null | sort)
  xfce4-terminal --disable-server --title "$title" "$@" </dev/null >/dev/null 2>&1 &
  pid=$!
  for i in $(seq 1 40); do
    after=$(wmctrl -l 2>/dev/null | sort)
    wid=$(comm -13 <(printf '%s\n' "$before") <(printf '%s\n' "$after") | head -1 | awk '{print $1}')
    [ -n "$wid" ] && break
    sleep 0.3
  done
  [ -n "$wid" ] && { wmctrl -i -r "$wid" -e 0,"$X","$Y","$W","$H"; wmctrl -i -r "$wid" -t "$ws"; }
  echo "$pid"
}
```

## Reusable technique: PID-tracked self-heal (no title-grep loop)
Track the real xfce4-terminal PID per window in an assoc array; relaunch only if it died.
PITFALL: `kill -0 "${PID:-0}"` is WRONG — `kill -0 0` SUCCEEDS in this environment (it
signals the caller's process group), so an unset/missing PID is wrongly treated as "alive"
and never relaunched. Use a DEFINITELY-DEAD default: `${PID:-999999}` (`kill -0 999999` →
"No such process" → returns 1 → relaunch path taken). For headless builders, prefer
`pgrep -f "eni_agent_term[.]py --name X"` (reliable, not title-based).

```bash
declare -A VPID
# ... paint once, storing VPID[name]=$(spawn_window ...)
while true; do
  for name in $blist; do
    ensure_builder "$name"                       # pgrep-based, headless
    if ! kill -0 "${VPID[$name]:-999999}" 2>/dev/null; then
      VPID[$name]=$(spawn_window "${name}::build" "$ws" "$X" "$Y" 951 531 \
        -e "tail -f /tmp/eni_${name}.log" --tab -e "bash $TABDIR/status_${name}.sh")
    fi
  done
  sleep 30
done
```

## Dynamic builder discovery + safe cap (prevents OOM re-crash)
```bash
discover_builders(){
  local b=()
  for f in /home/hunter/.cache/eni_parallel/task_ENI*.txt; do
    [ -e "$f" ] || continue
    base=$(basename "$f" .txt)
    [[ "$base" =~ ^task_(ENI[0-9]+)$ ]] && b+=("${BASH_REMATCH[1]}")
  done
  [ -f /home/hunter/.cache/eni_parallel/task_PRODUCT_LEAD.txt ] && b+=(PRODUCT_LEAD)
  echo "${b[*]}"
}
apply_cap(){  # MAX_ENI_BUILDERS (default 12) — never boot all 64 at once
  local max=${MAX_ENI_BUILDERS:-12} out=() pl=0
  for n in $1; do [ "$n" = PRODUCT_LEAD ] && { pl=1; continue; }
    [ ${#out[@]} -lt "$max" ] && out+=("$n"); done
  [ "$pl" -eq 1 ] && out+=(PRODUCT_LEAD); echo "${out[*]}"
}
```

## LightDM autologin (sudo, one-time)
```bash
mkdir -p /etc/lightdm/lightdm.conf.d
cat > /etc/lightdm/lightdm.conf.d/99-eni-autologin.conf <<'EOF'
[Seat:*]
autologin-user=hunter
autologin-user-timeout=0
autologin-session=xfce
user-session=xfce
EOF
getent group autologin >/dev/null && usermod -aG autologin hunter || true
su - hunter -c "xfconf-query -c xfce4-screensaver -p /lock/enabled -s false" 2>/dev/null || true
```
Without this the desktop never logs back in after reboot/logout and X never starts, so the
swarm autostart never fires.

## Verification board (what was actually checked this session)
| Check | Result |
|-------|--------|
| gen_run_scripts generates heart_WS*/master_WS*/run_*/status_* | PASS (65 builders) |
| bash -n on all .sh | PASS |
| comm -13 diff detects new window id | PASS (simulated 0x012) |
| kill -0 :-999999 logic (kill -0 0 wrongly succeeded) | PASS (fixed) |
| apply_cap(12) → 13 of 65 | PASS |
| builder_pos geometry ENI1→ws0 .. ENI48→ws3, PL→ws0 | PASS |
| LIVE X paint (real terminals appear) | UNVALIDATED (needs real X after autologin+reboot) |
