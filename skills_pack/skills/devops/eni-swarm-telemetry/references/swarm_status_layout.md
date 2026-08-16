# Swarm STATUS file layout (truth map for the heartbeat)

The single biggest trap when monitoring the ENI swarm: builders do NOT name STATUS files
after their project. They use module codes under project-specific roots. Matching by
filename token ("STOCKBOT") misses the live files and instead grabs stale root-level
leftovers. Use these exact roots.

## STOCKBOT  (workspace 1, /home/hunter/Commander/demiurge_scaffold)
Live builders write to:
  build/StockBotAppDir/usr/share/stockbot/swarm/{B1_swarm,B2_gate,B3_killswitch,B4_package,
    L1_dashboard,L2_mtf,L3_news,L4_risk,R1_automl,R2_walkfwd,R3_oanda,R4_orderrouter}/STATUS_*.md
Filenames are STATUS_B4_package.md etc. — NO "STOCKBOT" token. Freshest +9 min = actively building.
Root level ALSO has old STATUS_STOCKBOT_B*.md (hours stale) — do NOT scan those for liveness.
IMPORTANT: this build/ tree lives UNDER demiurge_scaffold, so a recursive scan of the
scaffold for "DEMIURGE" would wrongly pick up STOCKBOT's fresh files. Always exclude build/.

## DEMIURGE  (workspace 3, /home/hunter/Commander/demiurge_scaffold)
  - root NON-recursive: STATUS_DEMIURGE_*.md  (e.g. STATUS_DEMIURGE_B05.md, STATUS_DEMIURGE_FX_USB_LOADER.md)
  - demiurge_scaffold/swarm/{B1..B4,L1..L4,R1..R4}/*/STATUS_*.md  (older, ~20h)
Scan root non-recursive + swarm/, EXCLUDE build/. Freshest proper DEMIURGE ~7.6h.

## DEMIURGE3D  (workspace 2, /home/hunter/Desktop/demiurge-3d)
  recursive: STATUS_D3D*.md  (STATUS_D3D12.md freshest ~5.9h; backend/ + AppImage/AppDir copies are older duplicates)

## LUMEN  (workspace 4, /home/hunter/Desktop/apps/lumen)
  recursive: STATUS_LM*.md / STATUS_LUM*.md  (freshest ~18h — the silent-but-alive case)

## HEARTBEAT / PRODUCT_LEAD  (infra, /home/hunter/Commander/eni_swarm)
  STATUS_HEARTBEAT.md, STATUS_PRODUCT_LEAD.md  (freshest ~few min)

## Epoch clock trap (worked example)
`find /home/hunter/Desktop/demiurge-3d -name STATUS_*.md -printf '%TH:%TM %p\n' | sort | tail`
printed `20:59 STATUS_D3D13.md` ABOVE `09:21 STATUS_D3D12.md` — because sort is lexical on
HH:MM only and ignores the date. The file from the prior day at 20:59 sorts after today's
09:21. Epoch math proves D3D12 (09:21) is actually the most recent (~5.9h ago); D3D13's
"20:59" is from yesterday (~16h+). Always use:
  age_min = (time.time() - os.path.getmtime(f)) / 60.0
for any "how stale is this STATUS" computation.

## Proc-count tokens (in `hermes chat` cmdline)
  STOCKBOT   -> "project STOCKBOT "   (trailing space)
  DEMIURGE   -> "project DEMIURGE "   (trailing space — disambiguates from DEMIURGE3D)
  DEMIURGE3D -> "project DEMIURGE3D"
  LUMEN      -> "project LUMEN "
Count matches per token via `pgrep -af 'hermes chat'` + substring grep.
