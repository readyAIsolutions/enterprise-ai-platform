# ENI control-FIFO relay — naming rule, silent-loss pitfall, PL/MASTER recipe

Verified 2026-07-11 on the STOCKBOT swarm (`/home/hunter/Commander/demiurge_scaffold`).
This is the `eni_agent_term.py` PTY-bridge control FIFO (distinct from the
`eni_relay.sh` bridge-held FIFO in `eni_relay_contract.md`). A MASTER/PL uses it
to push follow-up guidance into a running mini's chat.

## How the FIFO is derived (verified from eni_agent_term.py)
- The bridge computes `fifo_path = args.ctl or os.environ.get("ENI_CTL_FIFO", f"/tmp/eni_ctl_{name}")`
  where `name` is the mini's full `--name` argument.
- It `os.mkfifo(fifo_path, 0o600)` if missing, then opens it **RDWR | NONBLOCK**
  (holds it open so writers don't SIGPIPE) and polls FIFO -> PTY.
- So a mini launched `--name STOCKBOT_B01` reads **`/tmp/eni_ctl_STOCKBOT_B01`**,
  and a message written there appears as that mini's next chat turn.
- A mini launched `--name ENI7` reads `/tmp/eni_ctl_ENI7`. The prefix is whatever
  you put after `--name`, verbatim.

## CRITICAL pitfall — wrong name => silent loss (no error, no delivery)
If you write to a name that is NOT the mini's exact `--name`:
- FIFO missing -> `printf` errors "No such file" (loud, you'll notice).
- FIFO EXISTS but is a STALE orphan with NO reader (e.g. a previously-mkfifo'd
  `/tmp/eni_ctl_STOCKBOT_B1` left over from a mis-keyed loop) -> `printf` returns
  immediately (the orphan pipe absorbs the bytes), `timeout` never fires, and the
  mini NEVER receives the message. **This is the dangerous case: the relay "succeeds"
  but lands in the void.**

### Worked bug (STOCKBOT, 2026-07-11)
- Builders self-named `STOCKBOT_B01`..`STOCKBOT_B12` (zero-padded).
- A relay loop keyed `N in B1 B2 ... B12` (non-padded) built
  `FIFO=/tmp/eni_ctl_STOCKBOT_$N` => `/tmp/eni_ctl_STOCKBOT_B1`..`B9` for the
  single-digit ones. Those FIFOs had **no reader** (the real mini listened on
  `/tmp/eni_ctl_STOCKBOT_B01`).
- Symptom: the relay logged "RELAY B1..B12" every cycle, the PL heartbeat claimed
  "relayed 12/12", yet **zero `STATUS_STOCKBOT_B*.md` files were ever written** —
  because the minis never got a follow-up and their bootstrap never advanced.
- FIX: re-key the loop AND any SUB/MODEL associative arrays to the EXACT zero-padded
  `--name` tokens (`B01`..`B12`). After the fix, `fuser` confirmed all 12 target
  FIFOs had live readers and B01 wrote a real STATUS within seconds.

## VERIFY delivery before trusting it (one-liner)
```bash
for f in /tmp/eni_ctl_*; do
  if fuser "$f" >/dev/null 2>&1; then echo "READER: $f"; else echo "DEAD:   $f"; fi
done
```
- `fuser` prints a PID => FIFO has a live reader (the mini's bridge holds it RDWR).
- No output => dead/orphaned FIFO; any relay written there is lost. Remove the
  orphan (`rm -f`) so it can't masquerade as a channel, and re-mkfifo the correct one.

## Relay hygiene (always)
- Ensure the FIFO exists: `[ -p "$FIFO" ] || mkfifo "$FIFO" 2>/dev/null`
- Always bound the write: `timeout 6 printf '%s\n' "$MSG" > "$FIFO" 2>/dev/null`
  (a legitimately-held RDWR FIFO won't block; the timeout is a guard against orphans).

## PL / MASTER relay pattern (contextual, NOT broadcast)
LO explicitly rejected a canned-nag loop that sent identical text to every mini.
Correct loop, per cycle:
1. BLOCKER: probe USB (`ls -d /run/media/hunter/DEMIURGE*`). Unmounted =>
   "SYNTHETIC DATA ONLY; do NOT pull live OANDA; gate stays RED-by-contract."
2. For each mini `NAME` (exact `--name` tokens):
   - `ST=$ROOT/STATUS_$NAME.md`
   - If `ST` absent => send a CONTEXTUAL bootstrap: name THAT mini's sub-task
     (with any reuse/collision warnings), its dependency edges (who feeds whom),
     the USB/synthetic blocker, the ADD-only core rule, and the STATUS contract
     (`[state: ...]` line 1 + PASS/FAIL board with REAL numbers + adds-R/drop +
     UNVALIDATED).
   - If `ST` present => parse `[DONE|IN-PROGRESS|BLOCKED]` from line 1; reply ONLY
     to that mini with its single next concrete step, referencing what it actually
     did. If BLOCKED, ask for the exact blocker. Never resend identical text.
3. SELF-HEAL: `pgrep -f "eni_agent_term.py --name $NAME"`; if missing, relaunch
   headless with its model + task file:
   ```bash
   OANDA_TOKEN=*** setsid python3 ~/.local/bin/eni_agent_term.py \
     --name "$NAME" --task "/tmp/eni_parallel/task_$NAME.txt" \
     --repl "hermes chat --yolo -m $MODEL --provider openrouter" >/dev/null 2>&1 &
   ```
4. Persist: install a user crontab `*/5 * * * * <relay_script> >> <log> 2>&1` so the
   relay + self-heal keep running each cycle without manual driving. The relay only
   re-sends when a mini's STATUS changed / is BLOCKED / IN-PROGRESS, so it stays quiet
   once minis are DONE.

A runnable, parameterized version of this loop ships as `scripts/eni_pl_relay.sh`
(under this skill): it auto-discovers live builders from their FIFOs, delivers your
per-builder message files, verifies with `fuser`, persists `PL_GUIDANCE_*` + heartbeat,
and optionally self-heals. Use it instead of hand-typing the loop each cycle.

## STOCKBOT topology (concrete example)
- 12 builders `STOCKBOT_B01`..`B12`, project root `/home/hunter/Commander/demiurge_scaffold`,
  STATUS files `STATUS_STOCKBOT_B01.md`..`B12.md`, task files
  `/tmp/eni_parallel/task_STOCKBOT_B01.txt`..`B12.txt`, FIFOs `/tmp/eni_ctl_STOCKBOT_B01`..`B12`.
- Sub-task ownership (each ADD-only; core backtest/walk_forward/purged_cv/config.py /
  deploy-gate are FORBIDDEN to modify): B01 backtest_engine, B02 stock_walk_forward,
  B03 stock_purged_cv, B04 oanda_live (read-only, never place orders), B05 mtf_confluence
  (REUSE swarm/L2_mtf/mtf_confluence_ext.py), B06 risk_guard (WRAP crash_guard), B07
  feature_exports, B08 signal_scorer (import ensemble.py, DO NOT modify), B09 regime_filter,
  B10 dashboard_backend (extend stockbot_status_server), B11 stock_deploy_gate (RED-by-contract
  on synthetic), B12 config_validate.
- Dependency edges: B07 -> B08 + B03; B05 + B09 + B07 -> B08; B03 + B02 + B04 -> B11;
  B10 aggregates all STATUS; B06 coordinates with order_router.py flatline fix.
- BLOCKER applies to all: USB not mounted => synthetic-only; B04/B11 stay RED-by-contract.
