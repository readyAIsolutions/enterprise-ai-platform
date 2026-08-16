# xfce4-terminal 2-Tab Limit — Proof (2026-07-10)

## Finding
On LO's Ubuntu 26.04 + XFCE, `xfce4-terminal` via CLI supports **exactly 2 tabs per window**. A 3rd `--tab -e` makes the window **silently never appear** while its `while true` proxy children survive SIGHUP as windowless processes.

## Proof Commands (run on LO's box)

```bash
# 1. 2 tabs → window appears
xfce4-terminal --disable-server -e "sleep 30" --tab -e "sleep 30" --geometry 80x24+100+100
sleep 2
wmctrl -l | grep sleep  # shows 1 window

# 2. 3 tabs → NO window appears
xfce4-terminal --disable-server -e "sleep 30" --tab -e "sleep 30" --tab -e "sleep 30" --geometry 80x24+500+100
sleep 2
wmctrl -l | grep sleep  # shows ONLY the 2-tab window, NOT a 3-tab window

# 3. Check orphan proxies
pgrep -fa 'sleep 30'  # shows 5 sleep processes (2 + 3) but only 1 window
```

## Impact on Swarm Design

| Component | Tabs | Window Count |
|-----------|------|--------------|
| ENI1–ENI16 (per WS) | 2 (MASTER:ENIx + ENI:ENIx) | 16 |
| HEARTBEAT (per WS) | 1 (single tab) | 1 |
| PRODUCT_LEAD (per WS) | 2 (MASTER:PL + ENI:PL) | 1 |
| **Total per workspace** | | **18 windows** |

## Workaround Applied
- `paint_LO_new.sh` (WS1): heartbeat = single tab, PL = separate 2-tab window stacked below
- `paint_all_workspaces_v3.sh` (WS0–3): same pattern per workspace
- NEVER attempt 3+ tabs in any xfce4-terminal launch

## Version Info
- `xfce4-terminal --version` → 0.8.9.2 (or similar)
- Ubuntu 26.04 LTS, XFCE 4.18, X11 (not Wayland)
- This limit may be XFCE version / GTK version specific

## Related
- `eni-visible-swarm` skill §Pitfalls: "xfce4-terminal 2-TAB LIMIT"
- `scripts/paint_LO_floor.sh` / `paint_all_workspaces_v3.sh` — canonical painters
- `references/eni_visible_swarm_session_20260710.md` — full session findings