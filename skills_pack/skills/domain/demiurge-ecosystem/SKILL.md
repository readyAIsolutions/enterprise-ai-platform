---
name: demiurge-ecosystem
description: "The complete Demiurge ecosystem - multi-provider AI swarm, distributed build coordination (Creed Multiplayer), FTMO forex/stock trading bot with deploy gates, 3D Forge pipeline, marketing platform, and all sub-systems. Use for ANY Demiurge-related work: trading bots, swarm orchestration, dashboards, 3D printing, marketing automation, or the Creed distributed build system."
category: domain
version: 2.0.0
---

# Demiurge Ecosystem - Class-Level Umbrella Skill

This skill consolidates the entire Demiurge family of systems into one class-level reference. All sub-components are organized as labeled sections with their own references/, templates/, and scripts/.

## Architecture Overview

```
DEMIURGE ECOSYSTEM
|-- Creed Multiplayer      <-- Distributed build coordination (multi-user, Tailscale mesh)
|-- Trading Bot (FTMO)     <-- Forex/Stock bot with purged-CV + walk-forward gates
|-- 3D Forge Pipeline      <-- Text to STL via FreeCAD/Blender/OpenSCAD + OrcaSlicer
|-- Marketing Platform     <-- Flask + Postgres + Piper TTS + Voice agents + CRM + Billing
|-- Creed Dashboard        <-- Single-file Python web dashboard (port 9772/8420)
|-- StockBot Equity        <-- Feature modules + deploy gates + AppImage packaging
|-- FX Gate Runner         <-- 4-leg deploy gate on real engine pipeline
`-- Status Telemetry       <-- Swarm STATUS aggregation + health monitoring
```

## Sub-System Index (Labeled Sections)

### A. CREED MULTIPLAYER - Distributed Build Coordination
**Primary file**: `references/creed_multiplayer.md` (from demiurge-creed-multiplayer)
- WebSocket + HTTP coordination server (:8765/:8766)
- Builder clients with capability detection + API key isolation
- Real-time dashboard with live task queue, artifacts, client cards
- Auto-sync via rsync/SSH (pre-build push / post-build pull)
- Build location selector (SERVER/LOCAL/HYBRID/CLIENT_CHOICE)
- Collaborative multi-client builds (target_clients)
- Persistent profile scoring (Hardware 35% + API Coverage 30% + Performance 25% + Reliability 10%)
- User onboarding script (`onboard_user.sh`) - one-shot builder setup
- Standalone ENI Builder package (zero-dep, cross-platform, Windows installer)

### B. TRADING BOT (FTMO) - Forex/Stock Strategy Engine
**Primary file**: `references/trading_bot.md` (from demiurge-trading-bot)
- Location: `/run/media/hunter/DEMIURGE` (USB mount - verify first!)
- Isolation: Research only, frozen historical data, NO live broker
- Gates: purged-CV AUC >=0.55, WF OOS >=36mo, WF trades >=500, fill degradation >=0.70
- Vetoes: cross-source (population vs subset AUC), spread-stress, fold-consistency, per-symbol stability/drawdown
- Feature modules: `stock_<name>_feature.py` with `align_features` + `evaluate` + `run()` contracts
- Real-data validation: `--real` flag on deploy gate, USB-mounted TRUTH_*.csv backtests
- AppImage ship-blocker: duplicate column audit via `stockbot_package_preflight.py`
- Dashboard: `stockbot_dashboard.py` (PyQt6, pure-Qt drawing, headless-testable)

### C. 3D FORGE PIPELINE - Text to Professional STL
**Primary file**: `references/forge_pipeline.md` (from demiurge-forge-pipeline)
- Project assembler -> FreeCAD (mechanical) / Blender (organic) / OpenSCAD (fallback)
- OrcaSlicer integration for G-code
- Tools: FreeCAD AppImage, Blender 5.0+, OrcaSlicer AppImage, OpenSCAD
- Professional quality bar: chamfers/fillets, proper thickness, countersunk holes, assembly features, 5000+ tris
- Pitfalls: FreeCAD boolean ops order, Blender bpy only inside Blender process, sculpt param threading, cold Blender timeout, calibration persistence

### D. MARKETING PLATFORM - Unified AI Sales Stack
**Primary file**: `references/marketing_platform.md` (from demiurge-marketing-platform)
- Flask + SQLAlchemy + Postgres + Redis + gunicorn on :8000
- Piper TTS (:5001, 4 voices) + XTTS voice cloning (:5002, transformers==4.38.2)
- Voice agents with per-agent voice selector, campaigns, CRM pipeline
- Baresip SIP calling (users bring VoIP.ms), SMTP email (Gmail App Password)
- Stripe billing + DEV grant fallback, Odoo CRM sync (optional)
- Google OAuth + admin local-mode bypass

### E. CREED DASHBOARD - Single-File Web UI
**Primary file**: `references/creed_dashboard.md` (from demiurge-creed-dashboard)
- Port 9772 (primary) / 8420 (secondary) - `orchestrator/orchestrator.py` (~53KB, zero deps beyond stdlib)
- SSE streaming chat, file-aware context, syntax highlighting, code mode, ENI swarm tab
- Folder upload + zip auto-extract, project browser, live credit bar, provider health
- AppImage build via `scripts/build_appimage.py` - `.desktop` at AppDir ROOT (not usr/share/applications)
- Multi-user mode: coordination server (:8765) + dashboard (:8766) + local client

### F. STOCKBOT EQUITY - Feature Modules + Deploy Gates
**Primary file**: `references/stockbot_equity.md` (from demiurge-stockbot-feature, demiurge-stockbot-gate-combiner)
- Feature contract: `NEW_COLS`, `align_features(trades, load_bars, tf)`, `evaluate()`, `_selftest()`, `run()`
- Gate admission: `stock_gate_feature_admission.py` auto-discovers `align_features` modules
- Deploy gate: `stock_deploy_gate.py --real` (USB-mounted TRUTH_baseline.csv = 16 sym / 1245 trades)
- Gate combiner: consumes B01/B02/B03 outputs, reuses `evaluate_deploy_gate`, RED-by-contract
- Vetoes: cross-source (population vs subset), spread-stress (1.5x/2x/3x live spread), fold-consistency (per-fold AUC >=0.50)
- Per-symbol stability: breadth_fraction, top3_positive_r_share, HHI/Gini on R, auc_breadth, h1_breadth
- Per-symbol drawdown: max_dd_r, diversification_ratio (~0.10 = 90% risk cut), mean_pairwise_corr (~0.03)
- Feature-admission gate (SB01): admits iff `adds_r=true` AND `selftest=PASS`; ratchet into deploy gate
- GUI wiring: `bot_ui.py` (live) needs `feature_block` shim + explicit list edit; `stockbot_dashboard.py` (headless PyQt6)

### G. FX GATE RUNNER - 4-Leg Deploy Gate on Real Engine
**Primary file**: `references/fx_gate_run.md` (from demiurge-fx-gate-run)
- Two-phase split (config-namespace clash): USB engine legs (Phase A) -> scaffold gate assembly (Phase B)
- Legs: purged-CV AUC, WF OOS months/trades, fill degradation (min real crash fillR)
- Kill-switch: `volatility_regime_killswitch.shock_mask` (ATR/EMA ratio >=1.8) + `apply_kill` -> flat crash window = fill=1.0 PASS
- Dual-metric caveat: per-trade crash edge (0.831 GREEN) vs aggregate SUM-based (0.129 RED) - show both
- Fees: spread debited in optimizer, add commission (2x0.00007/unit)

### H. STATUS TELEMETRY - Swarm Health Aggregation
**Primary file**: `references/status_telemetry.md` (from demiurge-status-telemetry)
- STATUS_<MODULE>.md per builder (line 1: `[state: DONE|IN-PROGRESS|BLOCKED]`)
- Aggregator reads per-module files, builds fleet board
- Real-data pulse: USB mount check, live OANDA probe, TRUTH backtest freshness

---

## Cross-Cutting Concerns

### USB DEMIURGE Mount (Critical for Real-Data Work)
```bash
# Verify mount (parent dir is root-owned, child is accessible)
lsblk -o NAME,LABEL,MOUNTPOINT,SIZE  # Find LABEL=DEMIURGE (e.g. sdc2)
sudo -n mount /dev/sdcN /mnt         # Passwordless sudo works
sudo mkdir -p /run/media/hunter/DEMIURGE && sudo mount --bind /mnt /run/media/hunter/DEMIURGE
# Now veto_usb_loader.is_usb_mounted() == True
```
Real reference backtests: `/mnt/data/backtests/TRUTH_*.csv` (TRUTH_baseline.csv = 16 symbols / 1245 trades)

### Memory/Compute Constraints
- Box is memory-tight (30GB+ for full walk-forward/AppImage build -> OOM)
- Use shrink params for smoke runs, route TMPDIR to `/home/hunter/.cache/d3d_tmp` (NOT /tmp - per-user quota EDQUOT)
- `.venv/bin/python3` for sklearn (not `.venv_appimage` - no sklearn there)

### ADD-ONLY Contract (Swarm Builders)
- NEVER edit core: `backtest_engine.py`, `walk_forward.py`, `purged_cv.py`, `config.py`, `deploy_gate_check.py`, `validate_gate*.py`
- New modules are separate files with unique `NEW_COLS` (suffix `_sbN`/`_<id>`)
- Extensions go through wrapper modules (e.g. `stock_gate_preflight.py`), never patch core

---

## Key Files Inventory (Consolidated from all sub-skills)

### References (canonical knowledge)
- `references/creed_multiplayer.md` - Architecture, protocol, server, client, dashboard, scoring, onboarding, auto-sync, build-location, collaborative builds, standalone ENI builder
- `references/trading_bot.md` - FTMO bot rules, feature contract, gates, vetoes, per-symbol metrics, AppImage preflight, dashboard
- `references/forge_pipeline.md` - Project assembler, FreeCAD/Blender/OpenSCAD generators, OrcaSlicer, tool install, pitfalls
- `references/marketing_platform.md` - Flask stack, voices, templates, calling, CRM, billing, pitfalls
- `references/creed_dashboard.md` - Unified dashboard, provider fallback, SSE streaming, ENI swarm tab, file mgmt, AppImage, debugging
- `references/stockbot_equity.md` - Feature module recipe, gate admission, deploy gate, gate combiner, vetoes, per-symbol metrics, feature-admission ratchet, GUI wiring
- `references/fx_gate_run.md` - Two-phase gate, kill-switch, dual-metric caveat, fees
- `references/status_telemetry.md` - STATUS format, aggregator, real-data pulse

### Templates (starter files)
- `templates/creed_protocol.py`, `templates/creed_server.py`, `templates/creed_client.py`, `templates/creed_dashboard.py`, `templates/creed_scoring.py`
- `templates/auto_sync.py`, `templates/build_location_decision.py`, `templates/eni_builder.py`, `templates/eni_builder_windows.py`
- `templates/stock_feature_module.py` - NEW_COLS / align_features / evaluate / run / selftest skeleton
- `templates/deploy_gate_combiner.py` - B01/B02/B03 consumer + evaluate_deploy_gate wrapper

### Scripts (executable automation)
- `scripts/launch_server.sh`, `scripts/launch_dashboard.sh`, `scripts/launch_client.sh`, `scripts/launch_all.sh`
- `scripts/onboard_user.sh` - one-shot builder onboarding
- `scripts/create_package.sh` - ENI builder dist tarball
- `scripts/creed_port_cleanup.sh`, `scripts/creed_health_check.sh`
- `scripts/stockbot_package_preflight.py` - duplicate column audit
- `scripts/build_stockbot_appimage.sh`, `scripts/smoke_appimage.sh`

---

## Quick Start: Common Workflows

### Launch Full Creed Multiplayer Stack
```bash
cd ~/Desktop/Projects/Demiurge_Creed
bash launch_all.sh  # Starts server (:8765) + dashboard (:8766) + local client
# Dashboard: http://localhost:8766
# Submit test task:
curl -X POST http://localhost:8765/api/tasks -H "Content-Type: application/json" -d '{"name":"test","prompt":"Python hello world","workdir":"~/creed_work"}'
```

### Run Trading Bot Deploy Gate (Real Data)
```bash
# Verify USB mounted first
python3 -c "import os; print(os.path.isdir('/run/media/hunter/DEMIURGE'))"
# Run real gate
cd /home/hunter/Commander/demiurge_scaffold
.venv/bin/python3 stock_deploy_gate.py --real
# Expect: auc~0.58, months~122, trades~80k, fill~0.88 -> GREEN
```

### Build StockBot Feature Module
```bash
# 1. Create module from template
cp templates/stock_feature_module.py stock_myfeature_sb99_feature.py
# 2. Implement NEW_COLS, align_features, evaluate, _selftest, run
# 3. Self-test
.venv/bin/python3 stock_myfeature_sb99_feature.py --selftest
# 4. Fast gate discovery check
.venv/bin/python3 -c "import stock_gate_feature_admission as g; print('discovered:', 'stock_myfeature_sb99_feature' in [n for n,_ in g._discover_modules()]); print('selftest:', g._selftest_rc('stock_myfeature_sb99_feature'))"
# 5. Real eval (background - exceeds 180s)
.venv/bin/python3 stock_myfeature_sb99_feature.py --real-eval  # terminal(background=true, notify_on_complete=true)
# 6. Preflight (dup col audit)
.venv/bin/python3 stockbot_package_preflight.py
```

### Run FX Gate (Two-Phase)
```bash
# Phase A: USB engine legs (USB on sys.path)
# Phase B: Scaffold gate assembly (scaffold cwd)
# See references/fx_gate_run.md for exact code snippets
```

---

## Pitfall Quick-Reference (Top 10)

| # | Pitfall | Fix |
|---|---------|-----|
| 1 | USB not mounted in-session | `lsblk -o LABEL` -> mount + bind to `/run/media/hunter/DEMIURGE` |
| 2 | `pd.merge_asof` symbol_x/symbol_y collision | Drop symbol from right frame before merge |
| 3 | `datetime64[us]` vs `[ns]` MergeError | `.astype("datetime64[ns, UTC]")` on BOTH frames |
| 4 | Full `evaluate()` >4min -> timeout | Use FAST gate-discovery check (sample 15 REJECT_IMPORT modules) |
| 5 | AppImage duplicate columns (16 pre-existing) | Suffix YOUR `NEW_COLS` with `_sbN`; don't edit other modules |
| 6 | `bot_ui.py` needs `feature_block` shim | Add thin `feature_block(close) -> (n,2)` adapter returning causal per-bar block |
| 7 | Kill-switch dual metrics disagree | Show BOTH: per-trade edge (0.831 GREEN) + aggregate SUM (0.129 RED) |
| 8 | Cross-source veto: subset GREEN but population RED | `stock_cross_source_gate_veto.py` - population AUC < 0.55 = HARD veto |
| 9 | Fold-consistency: mean AUC passes but one fold <0.50 | `stock_gate_fold_consistency.py` - per-fold floor = 0.50 (reuse gate's own `purged_cv_scores`) |
| 10 | Per-symbol AUC breadth <0.50 but R-breadth = 1.0 | Two-dim verdict: R-broad caps AUC-fragile at CONCENTRATED, never FRAGILE |

---

## Related Skills (External)
- `eni-swarm-ecosystem` - ENI parallel build swarm (separate but often co-deployed)
- `parallel-build-orchestration` - General parallel build patterns
- `linux-appimage-packaging` - AppImage build recipes (used by StockBot/Lumen/Cred)
- `demiurge-fill-model-hook` - Edge-aware fill/volume degradation model for gates
- `uncensored-prompt-engineering` - Zero-refusal content generation for guides