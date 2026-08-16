# SLICE A — Cooperative Multi-Player Builder (SERVER + PROTOCOL)
Build into: /home/hunter/Desktop/Enterprise Builder/enterprise/multiplayer/

Goal: a real cross-machine cooperative build coordination system. THIS IS THE
KILLER SELLING FEATURE. Must actually run end-to-end.

Files to CREActE (pure-python, stdlib only: asyncio, websockets if available OR
fall back to a plain TCP/JSON line protocol with a tiny HTTP health endpoint —
PREFER stdlib-only is REQUIRED; no pip installs):
- protocol.py      : JSON message schemas + message_type factory + validate()
     types: hello, welcome, task, work_start, work_log, artifact, work_result,
            heartbeat, ack, requeue, error. State machine RUgl = QUEUED -> ASSIGNED
            -> RUNNING -> COMPLETED | FAILED(retry once).
- server/server.py : async coordination server (asyncio + websockets). Endpoints:
    WS `ws://host:PORT/ws`   (clients)
    GET /health -> {"status":"ok","uptime":...,"clients":N,"queue":N}
    GET /api/board -> {clients[], queue[], active[], done[], ledger[]}
    POST /api/submit {goal, repo, prompt, artifacts, model_hint...} -> queues task
    GET /api/ledger
    Server assigns tasks round-robin by client load (fewest RUNNING first), respects
    each client's max_concurrent_tasks + model/provider/tag capabilities.
- server/broker.py    — task queue + assignment + requeue-on-miss/heartbeat-timeout
  (60s) + retry-once policy. Persist queue to data/multiplayer_queue.json (append
  JSONL) so a server restart resumes. (json persistence, keep simple)
- server/workspace_merge.py — given a canonical dir + a client's returned diff/artifacts,
  apply them; if a 3-way conflict, emit a resolver event and do NOT clobber. For v1,
  accept whole-file artifact write + a simple .MERGE ledger log line. Gate: if dir is a
  git repo, run `git status --porcelain` before/after and record.
- server/state.py — Board dataclasses + thread-safe (or async) state store for
  clients/tasks/ledger; used by /api/board and /api/stream.
- client/client.py — light per-machine client: read machine profile (cpus,ram,gpu,
  models via optional env), connect, send hello, receive tasks, run them via a WORKER
  command line (default: invoke `echo` + write an artifact file to prove IPC), stream
  logs, submit work_result, heartbeat every 15s. MUST NOT send any API keys (never).
- client/runner.py — pluggable "Worker" contract: class Worker(cmd=None, cwd=None):
    async run(task, on_log) -> result dict. Provide a built-in `shell_worker` that runs
    `sh -lc "<prompt as a shell command>"` in a task work dir and captures stdout/artifacts,
    and a `python_worker` that runs a .py artifact. A real Hermes worker can be added later.
- dashboard /api/stream uses server sent events (SSE) to push board updates.

CONSTRAINTS:
- Stdlib only. asyncio. No numpy. If you must pick, use http.server for health/api and
  a single long-lived TCP reader for WS-ish framing, OR if websockets module is already
  available on the machine use it. DO NOT pip install (sandbox may lack network).
- Every artifact file gets a small docstring header.
- Ports: server on 8787 (avoid 8765 which the old skill template used; pick 8787).
- Own tests: tests/ (use unittest or pytest) proving: broker assigns to capacity-capable
  client, heartbeat timeout requeues, merge applies artifacts + detects a conflict,
  protocol validates types. Run them, FIX until green, record real PASS numbers.
- The client must print cleanly to stdout so it can run headless.

DELIVERABLE: you must (a) write all files, (b) install the files into the multiplayer/
tree, (c) ACTUALLY RUN an end-to-end smoke: start server, start one client with a tiny
task, confirm it completes and shows on /api/board, capture the real output, then stop.
(f) write /home/hunter/Desktop/Enterprise Builder/enterprise/STATUS_MULTIPLAYER.md with
   explicit PASS/FAIL board using real numbers, "what adds R / what to drop", and an
   UNVALIDATED section. English-only output.