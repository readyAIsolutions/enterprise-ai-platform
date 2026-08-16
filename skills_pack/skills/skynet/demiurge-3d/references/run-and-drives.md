# Demiurge 3D — running the servers + drive visibility

## Booting backend + frontend (sandbox pitfall)

The agent runs in a SANDBOX. Shell-level background wrappers
(`nohup ... &`, `disown`, `setsid`) are REJECTED by the terminal tool
with: "Foreground command uses shell-level background wrappers... Use
terminal(background=true)". Do NOT try them.

Correct pattern — two separate `terminal(background=true)` calls:

    # backend  *** MUST be on :8093 — vite proxies /api -> localhost:8093 ***
    cd /home/hunter/Desktop/Demiurge3D/backend
    source ../.venv/bin/activate
    uvicorn server:app --host 0.0.0.0 --port 8093

    # frontend
    cd /home/hunter/Desktop/Demiurge3D/frontend
    npm run dev -- --host 0.0.0.0 --port 5173

Then verify in a normal foreground terminal (BOTH via the proxy port):
    curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8093/
    curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5173/

- Backend deps verified present in `.venv` (fastapi, uvicorn).
- `CALI_ALLOW_PRINT` gate was REMOVED (2026-07-15): `/api/print/dispatch`
  no longer requires it or a `confirm` token. Printing is armed by default.
  (The gcode audit/repair safety still runs per-job — that stays.)
- Frontend build: `npm run build` in `frontend/` (~5.7s, chunk-size warning
  is cosmetic only).
- Set `notify_on_complete=false` on the background launches (they are
  long-lived servers, never exit).

## CRITICAL PITFALL — port 8093 is the real API port, NOT 8000

The Vite dev server proxies `/api` (and the ws) to **`http://localhost:8093`**
(see `frontend/vite.config.*`). If you start uvicorn on `:8000`, the frontend
will 404 on every API call even though your server "is up". ALWAYS bind 8093.

Worse: a STALE backend can hold 8093 and shadow your fresh edits. Symptom:
you edit `server.py`, restart, but the browser still 404s or returns old
behavior. Root cause: an earlier `server.py` (run via its `__main__` block,
which hardcodes `port=8093`) is still listening — the running instance can
predate your session edits.

Kill-and-restart protocol (do this whenever routes misbehave after an edit):
    # 1. find what holds 8093
    ss -tlnp 2>/dev/null | grep 8093
    #    -> note the PID (e.g. pid=4141418)
    # 2. kill the stale holder (NOT just your own background session)
    kill <PID>
    # 3. clear stale pycache so Python can't load an old compiled route table
    cd /home/hunter/Desktop/Demiurge3D/backend
    rm -rf __pycache__ forge/__pycache__
    # 4. start fresh on 8093 (background=true, notify_on_complete=false)
    # 5. verify with curl on :8093 — NOT :8000

If `ss` shows the port "already in use" when YOU try to start, a stale process
is still alive — go back to step 1 and kill it first. `pkill -f "uvicorn
server:app"` then re-check `ss` is the hammer if PIDs are unclear.

## NTFS / fuseblk internal drive hidden from Thunar sidebar

Symptom: an internal SATA NTFS disk is mounted and fully accessible from
terminal (`ls /mount/point` works) but does NOT appear under Thunar's
"Devices" sidebar. `gio mount -l` DOES list it as a Volume+Mount, so the
OS sees it — only the file-manager display hides it.

Root cause observed on LO's box: mount dir owned `root:root` while sibling
removable drives (e.g. `DEMIURGE`, `TAILS`) are owned `hunter`. Thunar
suppresses device entries whose mountpoint perms aren't user-owned.

Concrete example (LO's 2TB "Backup" disk):
    /dev/sda1  Backup  1.8T  fuseblk  /run/media/hunter/2TB
    stat -c '%U:%G %a' /run/media/hunter/2TB   ->  root:root 777
    sibling:  /run/media/hunter/DEMIURGE        ->  hunter:hunter

Fix A (instant, no reboot) — just fix the mountpoint ownership:
    sudo chown hunter:hunter /run/media/hunter/2TB
    # Thunar usually shows it in the sidebar immediately after.

Fix B (permanent, shows at every boot) — fstab ntfs-3g with uid/gid:
    sudo mkdir -p /mnt/2TB && sudo chown hunter:hunter /mnt/2TB
    UUID=$(sudo blkid -o value -s UUID /dev/sda1)
    echo "$UUID /mnt/2TB ntfs-3g uid=1000,gid=1000,umask=022,defaults 0 0" | sudo tee -a /etc/fstab
    sudo mount -a

Note: the agent sandbox has NO root, so it cannot run `sudo` itself.
Diagnose (lsblk, mount, stat, gio mount -l) is fine; deliver the sudo
one-liner to LO to run on the host. Do not attempt to edit /etc/fstab or
remount from inside the sandbox.

## Drive map (LO's box, as of 2026-07-15)
- /dev/sda1  "Backup"  1.8T NTFS  -> /run/media/hunter/2TB  (internal SATA)
- /run/media/hunter/DEMIURGE  (volatile exfat build volume, label flips)
- /run/media/hunter/TAILS 7.9.1  (live USB)

## CRITICAL — agent sandbox has NO LAN egress to 192.168.x.x

The agent shell CANNOT reach the printers (K2 Plus at 192.168.1.65/.66:7125,
camera ports :8081/:4408). `curl`/`nc`/`python`/`ping` to any 192.168.x.x
address returns EMPTY from the sandbox, even though the printers are up and
LO can reach them from his browser. Only the **server process running on the
box** can talk to the printers.

Consequence — do NOT probe printers from the agent shell to "verify". It will
always look dead and send you down a wrong path. Instead:
- Reach printers ONLY through the running server's endpoints (curl
  `localhost:8093/api/printer/{id}/cameras`, `/status`, etc.) — those run
  inside the box process and DO reach 192.168.x.x.
- To test gcode/object logic against a printer, write a throwaway script that
  `import`s the backend modules and calls `m.command(...)` / `m.query_object(...)`
  — but run it WITH `source ../.venv/bin/activate` from the backend dir on the
  box (a terminal call executes on the box, not the sandbox network). If a
  command touching 192.168.x.x gets BLOCKED by the user/guard, STOP and ask LO
  to run it on the host — don't retry variants.
- When the live endpoint returns a shape that contradicts your on-disk code
  (e.g. you just added a `_debug` dict response but curl still returns a bare
  `[]`), suspect a STALE PROCESS before a logic bug. See next section.

## STALE PROCESS nuance — uvicorn `--reload` spawns a child that holds 8093

`uvicorn server:app --reload` forks a CHILD worker (separate PID) that actually
serves traffic; the parent is just the watcher. If you `kill` only the parent
(after grabbing the PID from `ss`), the child may keep 8093 open and your
"restart" serves the OLD code. Symptom: edit `server.py`, restart, curl still
returns pre-edit behavior.

Robust restart (prefer this over `--reload` for debugging):
    pkill -9 -f 'uvicorn'            # kills parent + children
    sleep 3
    ss -tlnp | grep 8093 && echo STILL || echo FREE   # MUST say FREE
    # then launch fresh WITHOUT --reload:
    uvicorn server:app --host 0.0.0.0 --port 8093   # background=true

If `ss` still shows a holder after `pkill -9`, grab that exact PID and
`kill -9 <PID>` it directly, then re-verify FREE. Never assume one kill cleared
it.

## Frontend changes need a BUILD, not just a backend restart

The backend serves the built SPA from `frontend/dist` (StaticFiles mount in
`server.py`). Editing `.tsx` does NOTHING until you rebuild:
    cd /home/hunter/Desktop/Demiurge3D/frontend && npm run build
Then HARD-REFRESH the browser to bust the cached JS bundle. A backend restart
alone will not surface frontend edits.

K2 camera-stream gotcha: a K2 `?action=stream` URL is NOT a true browser-push
MJPEG — the `<img>` freezes on the first frame if treated as such. Always poll
with a cache-buster (`?t=Date.now()`) for K2 feeds (both nozzle snapshot and
chamber stream). See `references/k2-plus-printer-facts.md`.
