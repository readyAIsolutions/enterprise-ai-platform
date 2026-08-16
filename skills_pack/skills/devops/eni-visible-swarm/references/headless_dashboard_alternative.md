# v4.1 Headless Dashboard Alternative

The `eni-visible-swarm` skill describes painting builder terminals across 4 X11 monitors using the legacy v4.0 PTY-based floor. For most sessions, LO now uses the **v4.1 optimized fleet** with a **web dashboard** instead:

- **Dashboard URL**: `http://localhost:8420`
- **Project**: `~/Desktop/Projects/ENI_Swarm_NEW/`
- **Fleet launcher**: `launchers/eni_launch_50_optimized.sh`
- **Fleet check**: `scripts/check_fleet.sh`

The dashboard provides everything the visible terminals did (builder status, live output, coordination) but in a single browser tab without the OOM risk of 4 xfce4-terminal windows full of PTY sessions.

When LO says "I don't see the swarm" or asks about builder visibility, offer the dashboard first. Only paint visible terminals if he explicitly requests the 4-monitor layout.

For recovery/operations procedures covering both v4.0 and v4.1, see `eni-swarm-floor-recovery`.
