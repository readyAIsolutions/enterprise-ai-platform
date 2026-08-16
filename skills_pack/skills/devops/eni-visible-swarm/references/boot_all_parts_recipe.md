# BOOT-ALL-PARTS recipe (ENI swarm floor)

## Trigger
LO: "boot all parts of eni swarm" (+ often "lumen isint running" / "etc").

## Safe boot (headless floor)
```
bash ~/.hermes/skills/devops/eni-build/scripts/recover_headless_floor.sh
```
- Idempotent. Regenerates 54 run-scripts via `gen_floor_opt.sh`, launches HEADLESS builders
  (skips any already alive), starts `mem_sentinel_opt.sh` (KILL-ONLY guard).
- Verified result (2026-07-14):
  ```
  GEN: 54 run scripts
  swarm_start_opt: launched=0 skipped(alive)=54 total_proxies=54
  alive proxies: 54
  ```
- Builder roster: SB1-12, D3D1-18, NAS1-12, LUM1-12 (54 total). LUM builders = code-only Lumen work.

## Verify
```
pgrep -fc 'eni_agent_term[.]py'        # expect 54
ps -eo pid,cmd | grep mem_sentinel      # expect running (KILL-ONLY guard)
pgrep -af 'python -m lumen[^-.]'        # expect NOTHING (Lumen app leashed)
```

## Healer / watchdog "down" is EXPECTED, not a failure
`swarm_start_opt.sh` contains:
```
[ -f "$ROOT/swarm_healer.sh" ] && nohup bash "$ROOT/swarm_healer.sh" >/tmp/eni_opt_healer.log 2>&1 9<&- &
```
On this box `swarm_healer.sh` is ABSENT (disabled after the OOM/reboot crash class) → the global
healer does not start. The 54 builders self-heal individually (each `run_<NAME>.sh` wraps the proxy
in `while true`), so the floor stays up without it. Do NOT recreate `swarm_healer.sh` /
`fleet_watchdog` unprompted.

## Lumen GUI — DO NOT LAUNCH (LUMEN LEASH)
LO's hard rule (2026-07-11, furious, repeated): never `python -m lumen` — it wedges the AMD
RX5700XT display/GPU and reboots the box. The Lumen *builders* (LUM1-12) are up as part of the
floor (code-only). The *wallpaper app* stays CLOSED. Only launch the app if LO explicitly says
"launch the lumen app". The grep above deliberately uses `python -m lumen[^-.]` so it does NOT
false-match the safe headless CLIs `python -m lumen.config` / `python -m lumen.doctor`.

## Visible-swarm paint — heavy, offer separately
Painting 54 builders as xfce4-terminal windows on the 4 monitors re-launches them as X clients.
On a memory-tight box (swap 100% full) this risks the OOM/429 stampede that has crashed the box
before. OFFER it; do not auto-run. The swarm is already building headless — paint is just glass.

## "do what u want" safety default
When LO delegates a safety-item decision (Lumen GUI / visible paint), choose to NOT risk his box:
keep headless floor stable, Lumen leashed, skip heavy paint. Report the call + offer the option so
he can green-light the risky part if he wants it.
