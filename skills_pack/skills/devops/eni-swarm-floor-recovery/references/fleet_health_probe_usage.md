# fleet_health_probe.sh — correct invocation & plaintext output

Session-verified usage notes for the ENI fleet-status cron probe. Read this before
running any ENI monitor/probe from a Hermes session — two traps are non-obvious.

## 1. The script's ABSOLUTE path (has a `/devops/` segment)

Invoke by absolute path. The umbrella lives under the `devops/` category directory,
so the correct path is:

```
bash /home/hunter/.hermes/skills/devops/eni-swarm-floor-recovery/scripts/fleet_health_probe.sh
```

It is NOT at the top-level skills dir. Guessing
`/home/hunter/.hermes/skills/eni-swarm-floor-recovery/...` (dropping `/devops/`)
fails with "No such file or directory". If unsure, locate it first:

```
search_files(target='files', pattern='fleet_health_probe.sh', path='/home/hunter/.hermes')
```

The skill description historically printed the path truncated as
`bash /home/hunter/.he...` — always confirm the full path rather than assuming the
top-level skills dir.

## 2. Use `env -u PYTHONPATH` to get PLAINTEXT, not <ENI-COMPRESSED> carriers

This box has an ENI compression hook wired into PYTHONPATH. When run through the
Hermes terminal (or via skill_view), large outputs — including the probe output, the
skill body, and even `monitor_fleet.py`'s ledger — come back wrapped as:
`<ENI-COMPRESSED ratio=Nx carrier=.../carrier_xxxx.png (recover via decompress)>`.
That carrier is not trivially decodable mid-session (no obvious `decompress` entry
point in the compression dir).

The fix is to unset PYTHONPATH for the call so output returns as raw text:

```
env -u PYTHONPATH bash /home/hunter/.hermes/skills/devops/eni-swarm-floor-recovery/scripts/fleet_health_probe.sh
```

The probe script already applies `env -u PYTHONPATH` internally for its sub-commands
(`monitor_fleet.py`, `fleet_pulse.py`), but the wrapper call itself and the final
echoed output still need the same treatment from your side.

## 3. Interpreting a healthy-but-idle fleet (don't panic-trigger)

From a clean 2026-08-16 run (representative steady state):
- Ledger: ~40 DONE / 8 IN-PROGRESS / 1 BLOCKED; most rows are
  `verified=unknown blocker=unknown next=unknown` (terse status files — normal).
- :8420 dashboard may be DOWN (health=000, not bound) while :8922 turbocharger and
  the MASTER_STATUS controller are UP — the axes are independent; one being down is
  NOT system-down.
- Pulse: `windows=0 | stalls: none | gate=RED` == floor IDLE/dormant, not down.
  Only relaunch against real queued work.