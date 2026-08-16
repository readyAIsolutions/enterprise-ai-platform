# ENI12 Status-Hub Mini — fleet-ping recipe & pitfall transcripts

Companion to the "ENI12 Status-Hub Mini" section in SKILL.md. This is the exact,
verified command sequence for one fleet-ping / resume cycle and the evidence that
proves the hub is GREEN. All paths/commands confirmed live 2026-07-09.

## One-cycle command sequence (copy-paste)

```bash
cd /home/hunter/Commander/eni_swarm

# 1) re-verify proven core (assert PASS, print counts)
python3 -W ignore status_hub.py --selftest
#   -> SELFTEST PASS: 78 minis (56 done / 20 in-progress / 2 blocked), 18 ALERTS -> /home/hunter/Commander/eni_swarm/MASTER_STATUS.md
#   exit 0

# 2) regenerate MASTER_STATUS.md (no args needed)
python3 -W ignore status_hub.py
#   -> MASTER_STATUS.md refreshed: 78 minis (56 done / 20 in-progress / 2 blocked), 18 ALERTS -> /home/hunter/Commander/eni_swarm/MASTER_STATUS.md
#   exit 0

# 3) USB mount reality check (NEVER assume unmounted)
mount | grep -i demiurge1
echo "DEMIURGE_USB=$DEMIURGE_USB"
ls /run/media/hunter/DEMIURGE1 2>/dev/null | head -3 || echo "DEMIURGE1 NOT MOUNTED"

# 4) cron daemon alive?
pgrep -a cron            # expect: 1919 /usr/sbin/cron -f -P   (binary `cron`, NOT `crond`)

# 5) cron log proves 5-min ticks
tail -6 /home/hunter/Commander/eni_swarm/status_hub.cron.log

# 6) blocked states in the freshly built MASTER_STATUS
grep -i "BLOCKED" /home/hunter/Commander/eni_swarm/MASTER_STATUS.md | head -20

# 7) confirm own heartbeat age is 0m in MASTER
grep -i "eni12.md" /home/hunter/Commander/eni_swarm/MASTER_STATUS.md | head -1
```

## Verified evidence (this session, 2026-07-09)

- selftest + build both exit 0; counts: 77–78 minis, DONE≈56, IN-PROGRESS 19–20, BLOCKED=2, ALERTS 17–20 (volatile).
- USB LIVE: `/dev/sdc2 on /run/media/hunter/DEMIURGE1 type exfat (rw,...,uid=1000,gid=1000,...)`, `$DEMIURGE_USB=/run/media/hunter/DEMIURGE1`. Empty stale `/run/media/hunter/DEMIURGE` also exists but is unused.
- cron daemon: `1919 /usr/sbin/cron -f -P`. crontab entry:
  `*/5 * * * * cd /home/hunter/Commander/eni_swarm && python3 -W ignore status_hub.py >> /home/hunter/Commander/eni_swarm/status_hub.cron.log 2>&1`
- cron log shows repeated refreshes every 5 min (e.g. `56 done / 19 in-progress / 2 blocked`, ALERTS 17→20).

## The 2 BLOCKED states (stable, recurring)

| State | Why | Fix (non-core) |
|-------|-----|----------------|
| `gate.md` BLOCKED | veto_usb_loader.py / gate_stress read hardcoded `/run/media/hunter/DEMIURGE` (empty) while real USB is at `/run/media/hunter/DEMIURGE1` (`$DEMIURGE_USB`). Stale-path artifact, NOT a mount gap. | Repoint that code to `$DEMIURGE_USB`. Then the 30GB walk-forward + real `veto_dataset()` can launch. |
| `STATUS_ENI9_w3.md` BLOCKED — creds | `.env` has NO FMP/MARKETAUX/FINNHUB/CRYPTOPANIC keys (only LLM keys). Live news parse cannot run. | Drop the news/OANDA creds into `.env`; then `news_tier1_validate.py` runs the live REST parse. Synthetic fallback `news_tier1.py` is green now and verifies plumbing. |

## Report template to MASTER (fleet ping)

```
ENI12 STATUS HUB — FLEET PING @ <HH:MM>
- Proven core GREEN: selftest PASS (exit 0), build exit 0, no status_hub.py edits (add-only).
- MASTER_STATUS.md refreshed, ENI12 heartbeat age 0m.
- Fleet: <N> minis (<D> DONE / <I> IN-PROGRESS / <B> BLOCKED), <A> ALERTS.
- BLOCKED (<B>): (1) ENI9_W3 creds; (2) GATE stale-path (USB live at DEMIURGE1).
- USB: LIVE at DEMIURGE1, not the blocker.
- Self-heal: cron pid alive, 5-min ticks confirmed; MASTER_STATUS stays fresh if chat dies.
Offers: (1) drop news/OANDA creds -> ENI9_W3 unblocks; (2) on go, repoint GATE USB to $DEMIURGE_USB.
```

## Gotchas

- Fleet count flickers 77↔78 between the two builds — peer STATUS files churn concurrently. Expected; don't chase it.
- Always `-W ignore` to suppress DeprecationWarning noise (not required for exit 0, but keeps output clean for LO).
- `status_hub.py` is the proven core — ADD-ONLY. Never rewrite it. Only update STATUS_*.md or add new files. Gate-USB / news-creds fixes go in THOSE modules.
- Keep `STATUS_ENI12.md` current: leading `[state: IN-PROGRESS]` + fresh CYCLE block (timestamp, re-verify results, blocker list). That file is the heartbeat LO actually reads.
