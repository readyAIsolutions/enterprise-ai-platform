STATUS — Upgrade A2: Live Real-Time Board
=========================================
Owner: subagent (enterprise) · English · scope: scripts/sidebyside.html only

DONE
----
Rewrote scripts/sidebyside.html from a 3s-polling iframe page into a live
real-time dashboard. No build step, no npm — plain HTML/CSS/JS only.

What the new page does
----------------------
1. LIVE HUB STATUS — polls /api/status every 2s (was 3s). Hub returns JSON
   with per-service {up, port}. Pills for Hermes / ENI / Multiplayer /
   Controller render as up/down/unknown with colored dots and port.
2. LIVE MULTIPLAYER BOARD — polls http://127.0.0.1:8788/api/board every 2s
   and renders the board as real cards (task id, status badge, goal,
   worker/assigned_client, steps/step, repo/model tags, summary) instead of
   raw JSON. Sections: Active / Queued / Done with per-section counts and a
   stat row (active/queued/done/workers).
3. PER-TASK PROGRESS BARS — animated width based on status (queued 5%,
   assigned 20%, running animated by step capped 95%, done/failed 100%),
   color-coded (running amber→blue, done green, failed red).
4. WORKER LIST with up/down — grid of worker cards showing connected state
   (disconnected flag), hostname, models, task load (running/max) and a load
   bar. Count shown in header.
5. TABS KEPT — ENI / Hermes / Multiplayer / One-Prompt. Multiplayer tab is
   now the rendered cards view; other three tabs remain iframes.
6. Live dot + "last sync" timestamp for at-a-glance liveness.

Service URLs / API compatibility — UNCHANGED
---------------------------------------------
- ENI iframe        http://127.0.0.1:8421
- Hermes iframe     http://127.0.0.1:8765/docs  (dash 9119 auto-switch preserved)
- One-Prompt iframe http://127.0.0.1:8913/health
- Board API         http://127.0.0.1:8788/api/board
- Hub status        /api/status (same origin, relative)
- Open-in-new links updated to reflect live up/down coloring.

Verification
------------
- node --check on extracted <script> block: JS SYNTAX OK.
- python3 http.server headless serve + curl: HTTP 200, size 16456.
- curl confirmed presence of new JS (pollBoard, cardHTML, renderWorkers,
  setInterval(pollBoard,2000)) and the /api/board URL + 4 tabs.

Files
-----
MODIFIED: /home/hunter/Desktop/Enterprise Builder/enterprise/scripts/sidebyside.html
(15KB -> 16.4KB, rewritten)
No other workstream files touched. No edits to multiplayer/server/*.py.

Notes / assumptions
-------------------
- Board JSON from server.py board_snapshot(): keys clients/queue/active/done/
  stats, tasks carry task_id, status, goal, step, assigned_client, repo,
  model_hint, summary, attempt. Rendered accordingly.
- "steps" shown via task.step (build-phase progress source); no build steps
  array exists in the record, so step is used for both chip + progress math.
- Worker up/down derived from client.disconnected flag (true = down).
