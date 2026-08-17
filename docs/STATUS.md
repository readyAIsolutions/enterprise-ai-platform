# STATUS — B4 fleet onboarder / B5 CI bridge / C1 live benchmark harness

Date: 2026-08-16
Repo: enterprise/  (scripts/)
Scope: NEW scripts only — no existing modules/eni_cli/boot_all/sidebyside edited.

## What was delivered

| ID | File | Purpose | Runnable |
|----|------|---------|----------|
| B4 | scripts/fleet_install.sh | One-command, idempotent fleet onboarder | `bash scripts/fleet_install.sh --dry-run` |
| B5 | scripts/ci_bridge.py | Deterministic goal->step ICM planner + CLI | `python3 scripts/ci_bridge.py --goal 'x'` |
| C1 | scripts/benchmark.py | submit_plan benchmark (live or offline sim) | `python3 scripts/benchmark.py` |
| B5 | scripts/tests/test_ci_bridge.py | Tests for build_plan | `python3 -m pytest tests/test_ci_bridge.py` |

## B4 — fleet_install.sh
- Idempotent: safe to rerun; installs python deps only if a requirements file
  is present (scripts themselves are stdlib-only), else skips.
- Detects hardware: CPU count (nproc/getconf), RAM GB (/proc/meminfo), GPU
  presence via `nvidia-smi` then `rocm-smi` -> prints `nvidia` / `amd-rocm` /
  `none`.
- Prints a capability profile (cpu_cores, ram_gb, gpu, server) plus a
  parseable `capability cpu_cores=.. ram_gb=.. gpu=..` fingerprint line.
- Starts a builder client pointed at MP_HOST/MP_PORT (defaults
  127.0.0.1:8787): runs benchmark.py's submit_plan handshake for live
  connectivity proof, or does a TCP probe if no python client exists.
- `--dry-run` prints the profile and exits without installing/starting.
  Verified on this host: `cpu_cores=24 ram_gb=30 gpu=nvidia`.

## B5 — ci_bridge.py
- `build_plan(goal) -> list[Step]` — deterministic decomposition of a goal
  into exactly 5 ICM-stage steps in canonical order:
  intake -> research -> drafting -> verification -> output.
- Each Step carries step#, stage, title, task/prompt, feature, test_hint and a
  linear dependency chain (each depends on the step before it). Same goal =>
  identical output everywhere (CI-cacheable).
- `build_plan_id(goal)` returns a stable sha256 fingerprint.
- CLI: `--goal` required; `--json` for machine-readable output.

## C1 — benchmark.py
- Pushes the SAME goal through `POST /api/submit_plan` against a configurable
  server (--host/--port, default 127.0.0.1:8787).
- Configurable concurrency: `--concurrency N` for a single N, or a sweep over
  [1,4] by default. Since N real workers aren't always available here,
  concurrency is simulated as N sequential submit rounds (one logical
  "machine" each) — a faithful wall-time/artifacts proxy.
- Reports wall time per round, cumulative time, and total artifacts scheduled,
  and prints a simple "X machines vs time" table.
- `--dry-run` runs an offline deterministic simulation with no server.
- Checks `/health` first and exits cleanly if the server isn't up.

## Live proof (C1)
Brought up the MultiplayerServer locally (ws 8899 / http API 8900) and ran the
benchmark in LIVE mode against it:
```
machines (N)  wall time   artifacts   cumulative
1             0.003       6           0.003
4             0.004       24          0.007
```
Each machine's plan fanned out to 6 task_ids via /api/submit_plan. Server was
then shut down and test data dirs removed.

## Tests
`scripts/tests/test_ci_bridge.py` — 7 tests, all green:
- returns 5 ICM stages in canonical order
- linear dependency chain (root + chain)
- determinism (same goal => same prompts + same plan_id)
- goal embedded in drafting task; feature/test_hint present
- empty goal handled
- CLI --json emits valid plan (count, stages, plan_id)
- CLI human output prints all 5 stages

Run: `python3 -m pytest scripts/tests/test_ci_bridge.py -q`  =>  7 passed

## Issues / notes
- MultiplayerServer puts the HTTP API on `port+1` (ws=8787 => http=8788), so
  the benchmark/fleet client should point MP_PORT at the HTTP API port.
- No existing requirements.txt target in scripts/, so install_deps is a no-op
  by design (all three scripts use only the Python stdlib + urllib).
- fetch shown: services were shut down after the live proof; nothing left
  running.
