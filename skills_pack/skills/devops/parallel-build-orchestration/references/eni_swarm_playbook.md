# ENI parallel-build swarm — proven playbook (LO's 9-mini + MASTER)

End-to-end recipe that actually worked for a 10-tab swarm across 4 monitors.
Companion to SKILL.md Step 2b. Read this before launching a new swarm.

## Files (on Desktop, reusable)
- `~/Desktop/eni_build_tasks.json` — task defs: `{"tasks":[{"name","title","workdir","task","model"}]}`. Each `task` MUST end with "Write STATUS_<NAME>.md in <workdir> ..." so the master can read it.
- `~/Desktop/eni_parallel_build.sh` — host launcher: TABBED xfce4-terminal, MASTER as first tab of the primary-monitor window, ~4 tabs/window, geometry from `xrandr --listmonitors`, creates `mkfifo /tmp/eni_ctl_<NAME>`, runs the PTY bridge per tab.
- `~/.local/bin/eni_agent_term.py` — PTY bridge (spawns `eni chat`, pre-types task after REPL banner, bridges `/tmp/eni_ctl_<NAME>`).
- `~/Desktop/eni_master_driver.py` — contextual MASTER driver (the fix, not a nag loop).

## Critical corrections LO demanded (embed in every swarm)
1. MASTER MUST BE CONTEXTUAL. Read each mini's STATUS_<NAME>.md and reply to THAT agent only — never the same canned line to all. First contact = a distinct brief per agent derived from its task + live facts. Dedupe so identical text is never resent.
2. NEVER DROP H4 / ANY TF. Use ANY/ALL timeframes (M1..W1) as STRUCTURE/bias filters. The old h4_dead_weight.py was a badly-trained H4 ENTRY model, not proof H4 structure is useless.
3. REAL OANDA. LO has a real OANDA test+live. Creds `OANDA_TOKEN`/`OANDA_ACCOUNT_ID` live in `/run/media/hunter/DEMIURGE/.env` (USB) or env. Build the REAL live-vs-sim fill/volume gap report — not a simulated feed.
4. DEMIURGE code + ref backtests are on the USB; the STOCK-BOT scaffold is on Desktop `~/Desktop/Commander/demiurge_scaffold`. USB is often unmounted in-container → agents scaffold + report blocker until mounted.

## Launch
```bash
cp ~/.hermes/.env ~/.hermes/profiles/eni/.env        # or agents die "not configured"
cp ~/.hermes/config.yaml ~/.hermes/profiles/eni/config.yaml
bash ~/Desktop/eni_parallel_build.sh                 # from a REAL host terminal (xfce4-terminal is D-Bus)
python3 ~/Desktop/eni_master_driver.py               # terminal(background=true)
```

## Liveness (proxy is 1:1 with hermes)
- all agents: `pgrep -fc 'hermes -p eni chat --y[o]lo'`
- per-agent: `pgrep -fc 'eni_agent_term[.]py.*KEYWORD'` (KEYWORD is a string in that agent's TASK TEXT; the `task_X.txt` path is command-substituted away, only the text remains)
- real activity: `find ~/.hermes/profiles/eni/sessions -name 'request_dump_*.json' -newermt '-2 min' | wc -l`

## Pitfalls hit this session
- Minis write STATUS into their OWN workdir, NOT `~/Desktop/eni_out`. Driver reads from workdir.
- A driver that repeats a FOCUS string to every agent = rejected as a "nag loop". Make it read+think+reply per agent.
- USB not mounted → OANDA creds + DEMIURGE ref data unreachable; tell agents to scaffold + block, then repoint on mount.
