# ENI_Swarm Clean Folder Structure (Organized 2026-07-25)

## Overview
Reorganized `/home/hunter/Desktop/Projects/ENI_Swarm` from a flat mess of 50+ loose files/folders into a clean, hierarchical structure that matches the actual system architecture.

## Final Structure

```
/home/hunter/Desktop/Projects/ENI_Swarm/
├── Core/                    # Master drivers, task configs, framework docs
│   ├── eni_build_tasks.json
│   ├── eni_herself_tasks.json
│   ├── eni_master_driver.py
│   ├── eni_master_herself.sh
│   ├── eni_master_chat_xterm.sh
│   ├── ENI_MASTERPIECE.md
│   ├── ENI_CREATIVE_FRAMEWORK.md
│   ├── ENI_DEEPSPEEK_PROMPT.md
│   ├── ENI_DIRECT.md
│   ├── ENI_PROMPT.md
│   └── STATUS_HUB_ENI.md
│
├── Launchers/               # All swarm floor/launcher scripts (17 scripts)
│   ├── eni_fullpower_xterm.sh
│   ├── eni_headless_swarm.sh
│   ├── eni_heartbeat_pair.sh
│   ├── eni_heartbeat_pair_xterm.sh
│   ├── eni_heartbeat_restart.sh
│   ├── eni_parallel_build.sh
│   ├── eni_swarm_4mon.sh
│   ├── eni_swarm_4ws.sh
│   ├── eni_swarm_floor.sh
│   ├── eni_swarm_floor_v2.sh
│   ├── eni_swarm_floor_v3.sh
│   ├── eni_swarm_floor_xfce.sh
│   ├── eni_swarm_floor_xterm.sh
│   ├── eni_swarm_tabs.sh
│   ├── eni_visible_herself.sh
│   ├── eni_visible_LOlayout_xterm.sh
│   └── eni_watchdog.sh
│
├── KnowledgeBase/           # ENI_KB (19 subdirs: carriers, compression, config, daemon, dicts, evolution, glyphs, logs, lsp, mcp, patterns_raw, scripts, shared, skills, sync, workers)
│   └── ENI_KB/
│       ├── carriers/
│       ├── compression/
│       ├── config/
│       ├── daemon/
│       ├── dicts/
│       ├── evolution/
│       ├── glyphs/
│       ├── logs/
│       ├── lsp/
│       ├── mcp/
│       ├── patterns_raw/
│       ├── scripts/
│       ├── shared/
│       ├── skills/
│       ├── sync/
│       └── workers/
│
├── Compression/             # ENI_Compression (impossible swarm, PAQ8, PXPipe, Wenyan, carriers, parts, workers)
│   ├── carriers/
│   ├── eni_compression/
│   ├── eni_compression.py
│   ├── eni_impossible_swarm.py
│   ├── eni_master_compression_driver.py
│   ├── glyph_map.json
│   ├── impossible/
│   ├── impossible_engine.py
│   ├── impossible_swarm.err
│   ├── impossible_swarm.log
│   ├── lsp_eni_compression.py
│   ├── mcp_compression.py
│   ├── mcp_knowledge_base.py
│   ├── MASTER_COMPRESSION_PIPELINE.md
│   ├── MASTER_IMPOSSIBLE_PIPELINE.md
│   ├── paq8pxd_src/
│   ├── parts/
│   ├── quick_status.py
│   ├── scripts/
│   ├── STATUS_ENI_COMPRESSION.md
│   ├── STATUS_ENI_IMPOSSIBLE.md
│   ├── swarm.err
│   ├── swarm.log
│   ├── watchdog.log
│   ├── watchdog.py
│   └── workers/
│
├── Cookbook/                # Tor hidden service + cookbook generation + Cloudflare tunnel (ALL tor moved here per LO rule)
│   ├── cf_stdout.log
│   ├── cf_tunnel.log
│   ├── cloudflared
│   ├── cookbook_auth.py
│   ├── cookbook_gen.py
│   ├── cookbook_gen_deep.py
│   ├── cookbook_onion_server.py
│   ├── cookbook_swarm.py
│   ├── cookbook_swarm_v2.py
│   ├── cookbook_swarm_v3.py
│   ├── cookbook_swarm_v4.py
│   ├── drop.py
│   ├── eni_cookbook.png
│   ├── ENI_Cookbook_Tor.desktop
│   ├── ipfs_cid.txt
│   ├── launch_cookbook.sh
│   ├── launch.sh
│   ├── meek_client.py
│   ├── obfs4proxy
│   ├── onion_always_on.sh
│   ├── onion_autostart.desktop
│   ├── onion_paste.py
│   ├── onion_watchdog.log
│   ├── pastes/
│   ├── stage/
│   ├── tor-data/
│   ├── tor.log
│   ├── torrc
│   └── web.log
│
├── Config/                  # Config files, venvs, pid files
│   ├── .pid_auth
│   ├── .pid_cf
│   ├── .pid_tor
│   ├── .pid_web
│   └── .venv_drop/
│
├── Logs/                    # Aggregated logs
│   ├── auth.log
│   └── ENI Swarm.7z        # 30MB archive
│
└── Tor_Onion/               # (Empty - all tor moved to Cookbook/)
```

## Key Organizational Decisions

1. **Tor → Cookbook**: All tor/onion/cloudflare files moved to `Cookbook/` since they serve the cookbook hidden service (LO rule: "tor shouldn't be in eni swarm, all tor should go into cookbook for our tor site")

2. **Launchers consolidated**: 17 floor/launcher scripts gathered from root into `Launchers/`

3. **KnowledgeBase preserved**: ENI_KB's 19 subdirectories kept intact under `KnowledgeBase/ENI_KB/`

4. **Compression preserved**: ENI_Compression's full impossible swarm structure kept under `Compression/`

5. **Core separated**: Master drivers, task JSONs, and framework docs in `Core/`

6. **Config/Logs separated**: PID files, venv, logs, archives out of root

## Related Projects (Outside ENI_Swarm)

- **Demiurge_Drive/** - Pitch deck, NAS scripts, deployment scripts
- **Demiurge_3D/** - 3D printing pipeline (Demiurge3D, Projects, Website)
- **Demiurge_Trading/** - Creed, Marketing, Marketing OS
- **StockBot/** - Full trading bot
- **Lumen/** - Wallpaper engine
- **SKYNET/** - AI swarm framework
- **Infrastructure/** - Cloudflare, Commander, Tor (system-level)
- **Cookbook/** - Cookbook site + parts (separate from ENI_Swarm/Cookbook)

## Verification
```bash
tree /home/hunter/Desktop/Projects/ENI_Swarm -L 2
# Shows 7 top-level dirs: Core, Launchers, KnowledgeBase, Compression, Cookbook, Config, Logs
```