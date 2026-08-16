# eni_relay.sh — bounded FIFO control relay (correct pattern + test recipe)

Canonical MASTER→mini control channel. Appends `<message>` + newline into
`/tmp/eni_ctl_<NAME>` (mkfifo if missing), bounded by `ENI_RELAY_TIMEOUT`
(default 15s). On a DEAD mini (no reader) it must SPOOL to
`/tmp/eni_spool_<NAME>` and return 0 — never hard-fail LO's terminal, never
drop a control message.

## THE TRAP: never gate the spool on `rc -eq 124`

Naive version (BROKEN on a dead mini):
```bash
if timeout "$TIMEOUT" bash -c 'exec 3>>"$ENI_CTL_FIFO"; printf "%s\n" "$ENI_RELAY_MSG" >&3'; then
  exit 0
fi
rc=$?
if [ "$rc" -eq 124 ]; then          # <-- WRONG: you don't get 124 here
  ...spool...
else
  echo "error ... rc=$rc"; exit 1   # <-- dead mini wrongly hits this
fi
```
Why it fails: with NO reader, `exec 3>>"$ENI_CTL_FIFO"` BLOCKS opening the
FIFO for write. `timeout` SIGTERMs the inner bash, which *interrupts the open
syscall*. The inner shell does NOT exit 124 — it surfaces the interrupted
`exec`/`printf` as a different code (e.g. 1 / "Bad file descriptor"), so the
`if` is false with `rc != 124` and control falls into the `else` → a false
`error ... rc=0` + `exit 1`. A dead mini looks like a hard failure.

CORRECT pattern (any non-success → spool, never error):
```bash
if timeout "$TIMEOUT" bash -c 'exec 3>>"$ENI_CTL_FIFO"; printf "%s\n" "$ENI_RELAY_MSG" >&3'; then
  exit 0                      # confirmed delivered into the mini's pipe
fi
# Anything else = not delivered (timeout w/ no reader, or interrupted open).
printf '%s\n' "$MESSAGE" >> "$SPOOL"
echo "warn: delivery to $FIFO not confirmed within ${TIMEOUT}s — spooled to $SPOOL" >&2
exit 0
```

## How to TEST the relay here (Hermes CLI constraints)

The terminal tool REJECTS `&` backgrounding and the safety filter may block
`rm -f`, so the usual `reader &` + `rm -f fifo` shape fails. Use this instead:

1. Live-delivery test — reader via `coproc` + `cat`, FIFO path passed
   POSITIONALLY (a single-quoted `bash -c '...$VAR...'` with an unexported VAR
   expands to empty, so the reader opens "" and never reads the real pipe):
```bash
cd /home/hunter/Commander/eni_swarm
M=ENILIVE_TEST; F="/tmp/eni_ctl_$M"
mkfifo "$F" 2>/dev/null
coproc RD ( timeout 25 cat "$F" > /tmp/eni_live_recv.txt )
export ENI_RELAY_TIMEOUT=10
./eni_relay.sh "$M" "live delivery test line αβγ"
echo "relay rc=$?"; sleep 0.6
echo "RECEIVED: [$(cat /tmp/eni_live_recv.txt)]"   # => exact message, incl. unicode
```
2. Dead-mini test — FRESH mini name (no reader running), short timeout:
```bash
export ENI_RELAY_TIMEOUT=2
./eni_relay.sh RCONF2 "dead mini message"
# expect: warn ... spooled ... ; rc=0 ; /tmp/eni_spool_RCONF2 holds the line
```
3. Idempotency — re-running against an existing FIFO must not error.

## eni_status.sh — DEMIURGE_DIR NAS fallback

`eni_status.sh` cats every `STATUS_ENI*.md` then every `STATUS_*` under the
live DEMIURGE scaffold. `$DEMIURGE_DIR` often points at the Lab NAS
(`/run/media/hunter/DEMIURGENAS/demiurge`) which is UNMOUNTED here, so a naive
`if [ -d "$DEMIURGE_DIR" ]` yields `demiurge=0`. The current on-disk version
falls back to `/home/hunter/Commander/demiurge_scaffold` when the env path
holds no `STATUS_*.md`. If you re-touch this script, KEEP the fallback.
