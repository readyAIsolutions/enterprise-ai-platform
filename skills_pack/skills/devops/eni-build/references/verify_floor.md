# Verifying the ENI swarm floor

Run `bash scripts/verify_floor.sh` for an automated check. Manual recipe below.

## 1. Builder windows per X11 workspace (expect 12 each)
for d in 0 1 2 3; do
  echo "ws$((d+1)): $(wmctrl -l | awk -v D=$d '$2==D' | grep -cE '_(B[0-9])')"
done
wmctrl -l | grep -E 'ENI:HEARTBEAT|ENI:PRODUCT_LEAD'   # control present
xprop -id <id> _NET_WM_STATE | grep STICKY              # control sticky

## 2. Builders are ACTUALLY grinding (not idling)
pgrep -fc 'hermes chat -q'        # ~48 looping driver processes
# If ~0, the floor is the OLD single-turn design -> redeploy with the loop driver.

## 3. Fresh file output (proof of work)
find ~/Commander/demiurge_scaffold ~/Desktop/demiurge-3d ~/Desktop/apps/lumen \
  -name 'STATUS*.md' -mmin -5     # should show writes in the last 5 min

## 4. Distinguish swarm from the agent's own hermes
`pgrep -fc 'hermes chat'` reports ~150 — MOST are the Hermes AGENT's own session
processes, NOT swarm. The swarm builders are the `hermes chat -q ...` loops
(pitfall #11). Count those, not the bare `hermes chat` total.

## Reading the result
- 12/12/12/12 builders + control STICKY + `hermes chat -q` ~48 + recent STATUS
  writes => FLOOR HEALTHY and grinding.
- Builders present but `hermes chat -q` ~0 and no recent STATUS => the single-turn
  idle bug (pitfall #11) — redeploy `fleet_deploy_ws.sh`.
- Builder count < 48 or control missing => watchdog self-heals within 10 min, or
  run `fleet_deploy_ws.sh` manually.
