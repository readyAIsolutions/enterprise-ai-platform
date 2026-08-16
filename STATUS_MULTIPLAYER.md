# STATUS: Multiplayer Cooperative Build System (SLICE A)
**Repo:** /home/hunter/Desktop/Enterprise Builder/enterprise/multiplayer/
**Date:** 2026-08-16
**State:** v1 working end-to-end

## What this is
The horizontal cooperative build floor — the product's killer feature. N team
machines, each running a builder client (their Hermes/worker + their API keys),
coordinate through one server over WebSocket. The server brokers goals into tasks,
assigns each to the least-loaded capable machine, merges returned artifacts into a
canonical workspace with conflict-safety, and exposes a live board + merge ledger.

## Files
- protocol.py            — JSON message schemas, `make_message`, `validate`, anti-secret guard
- server/server.py       — WS server (8787) + HTTP API (8788): /health /api/board /api/ledger /api/submit
- server/broker.py       — queueing, capability-aware round-robin assignment, heartbeat requeue, retry-once, JSONL persistence
- server/state.py        — Board (clients/tasks/ledger) + TaskRecord/ClientRecord
- server/workspace_merge.py — artifact apply, 3-way conflict detection (no clobber), .MERGE ledger
- client/client.py       — per-machine builder client (WS connect, hello, heartbeats, task execution)
- client/runner.py       — pluggable workers: shell_worker, python_worker
- tests/test_multiplayer.py

## PASS / FAIL board (real numbers)
| Check | Result | Evidence |
|---|---|---|
| protocol schema validate/envode/decode | ✅ PASS | 3/3 protocol tests |
| anti-secret guard refuses credentials | ✅ PASS | test_protocol_refuses_secrets |
| broker submit -> QUEUED | ✅ PASS | test_broker_submit_creates_queued_task |
| capability-aware assignment | ✅ PASS | test_broker_assigns_to_capacity_capable_client |
| heartbeat-timeout requeue | ✅ PASS | test_broker_heartbeat_timeout_requeues |
| merge applies artifacts | ✅ PASS | test_merge_applies_artifacts (file written to workspace) |
| merge detects conflict, no clobber | ✅ PASS | test_merge_detects_conflict_and_does_not_clobber |
| board snapshot shape | ✅ PASS | test_board_snapshot_shape |
| **unit suite total** | ✅ PASS | **9 passed, 0 failed, 0.03s** |
| **live end-to-end smoke** | ✅ PASS | see below |

## Live end-to-end smoke (REAL output)
Ran: `python3 -m enterprise.multiplayer.server.server 8793` +
`python3 -m enterprise.multiplayer.client.client --host 127.0.0.1 --port 8793 --id smoke-builder-1 --worker shell`

Submitted two tasks via `POST /api/submit`:
- goal="create buildproof" prompt=`echo VERIFIED_MP_BUILD >> buildproof.txt && printf coop >> buildproof.txt`
- goal="create hello" prompt=`printf hello_world > hello.txt`

Observed on disk (authoritative, not printed — the client stdout is buffered):
```
client on board: client_id=smoke-builder-1, running=['t-f4be417eb2a2','t-2f1f51e53f20'], load=2
merge ledger (data/multiplayer/wspace): 
  [ts] APPLIED task=t-f4be417eb2a2 client=smoke-builder-1 applied=buildproof.txt skipped= conflicts=0
  [ts] APPLIED task=t-2f1f51e53f20 client=smoke-builder-1 applied=hello.txt skipped=buildproof.txt conflicts=0
workspace files: buildproof.txt (contents: VERIFIED_MP_BUILD \n coop), hello.txt (hello_world)
```
Health: `GET /health` -> {"status":"ok","clients":1}

## Bugs found & fixed in this pass
1. Broker was constructed WITHOUT the `on_send` callback -> assigned tasks were
   never delivered over the socket. Fixed by wiring `on_send=self._broker_deliver`.
2. Assignment ran in a worker-thread loop; delivery to a main-loop websocket failed.
   Fixed by running the broker's `run_assign_loop` on the main event loop.
3. `protocol.validate` called `.items()` on `schema["optional"]` which is a `set` for
   some types → AttributeError. Fixed to accept dict or set.
4. Server's `_hello` didn't set `ClientRecord.transport`, so the broker's
   `assign()` client filter (`transport is not None`) excluded every client → nothing
   ever assigned. Fixed to `transport="ws"`.

## Security posture
The protocol's anti-secret guard refuses `api_key/apikey/secret/authorization/bearer/
password/token=` in prompt/content/summary/stdout/message payloads. Clients send only
capability tags (model names, provider names, hardware) — never keys. Placeholder refs
(`{KEY:name}`) are resolved client-side by the local controller, never transmitted.

## What adds R (keep) / what to drop
- KEEP: async Board/Broker (single writer thread via run_assign_loop), conflict-safe
  merge, heartbeat requeue, anti-secret guard, JSONL persistence, pluggable workers.
- DROP/DEFER: HTTP API lives on port+1 (separate from WS). Better: unify ports via a
  single gateway. A WebSocket *dashboard push* (`/api/stream` SSE/WS) is a natural next
  slice. `psutil` import is optional/guarded for RAM detection (absent = graceful).

## UNVALIDATED
- Real **cross-machine**, cross-IP operation (both server+client ran on this one box).
- A genuine Hermes/LLM worker backend (workers are currently shell/python stubs that
  prove the wiring; wiring the local controller's planner to drive them is the next
  slice).
- Real agent-side git merge (3-way is emulated by non-clobber conflict detection) — does
  not yet parse git merge conflicts from a live repo.
- TLS / auth / multi-tenancy on the server (all plain local) — needed before public SaaS.