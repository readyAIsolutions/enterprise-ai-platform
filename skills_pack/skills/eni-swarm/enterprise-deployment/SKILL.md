---
name: enterprise-deployment
description: Deploy the ENI Enterprise Platform end-to-end — Docker, scripts, monitoring, documentation. Load when deploying, containerizing, monitoring, or packaging the enterprise platform for production.
---

# Enterprise Platform Deployment

Location: `/home/hunter/Desktop/Enterprise Builder/enterprise/`

## Quick Deploy

```bash
cd /home/hunter/Desktop/Enterprise\\ Builder/enterprise
```
# Option A: Docker (recommended for production)
cd docker && make run

# Option B: Direct Python
bash scripts/start_all.sh

# Option C: Development with hot-reload
cd docker && make run-dev

# Verify
curl http://localhost:8421/api/v1/health/live
bash scripts/health_check.sh --quick
bash scripts/status.sh --short
```

## Deployment Options

### Docker (14+ services)
```bash
cd enterprise/docker
make run              # Start all services
make status           # Show container health
make logs             # Tail all logs
make stop             # Graceful shutdown
make test-health      # Run health checks against containers
```

Services: api-gateway (:8421), dashboard (:8421), eni-swarm (:8420), claude-code-server (:9120), swarm-turbocharger (:8922), free-router (:8920), event-hub (:8900), service-mesh (:8910), redis (:6379), postgres (:5432), prometheus (:9090), grafana (:3000), + 7 module containers.

### Bare Metal
```bash
cd enterprise/scripts
bash deploy.sh        # Full deployment pipeline (prereqs → env → deps → tests → deploy → verify)
bash start_all.sh     # Ordered startup
bash stop_all.sh      # Graceful shutdown
bash status.sh -w     # Watch mode dashboard
```

### Development
```bash
cd enterprise/docker
make build-dev && make run-dev  # Hot-reload with debugpy (:5678)
```

## Scripts Reference

All scripts in `enterprise/scripts/`. All executable. All support `--help`.

| Script | Purpose | Notable Flags |
|--------|---------|---------------|
| `deploy.sh` | Full deployment pipeline | `--docker`, `--direct`, `--skip-tests` |
| `health_check.sh` | 7-layer system health | `--quick`, `--json`, `--watch` |
| `start_all.sh` | Ordered service startup | `--direct`, `--daemon` |
| `stop_all.sh` | Graceful shutdown | `--force`, `--cleanup` |
| `status.sh` | Full status dashboard | `--short`, `--json`, `--watch` |
| `backup.sh` | Backup configs/data/logs | `--full`, `--keep N`, `--dry-run` |
| `restore.sh` | Restore from backup | `--list`, `--dry-run`, `--configs-only` |
| `run_tests.sh` | Test suite runner | `--module NAME`, `--coverage`, `--parallel` |

Exit codes: 0=healthy/success, 1=degraded, 2=unhealthy/error, 10-19=operational errors.

## Monitoring Stack

```bash
# Start monitoring services (included in docker-compose)
# Prometheus: http://localhost:9090
# Grafana:    http://localhost:3000 (admin/admin)

# Python monitoring API
python3 -c "
from enterprise.monitoring import (
    MonitoringMetricsCollector, AlertManager, HealthDashboard, LogAggregator
)
# 122 tests, all passing
"

# Quick metrics via API
curl http://localhost:8421/api/v1/metrics/current
curl http://localhost:8421/api/v1/alerts
```

## Networking Requirements

Before deploying, ensure the Swarm Turbocharger is running:

```bash
# Check
curl http://localhost:8922/health
# → {"status":"ok","concurrency":50,"signal":-59}

# Start if not running
python3 ~/.hermes/scripts/swarm_turbocharger.py --port 8922 &
# Or via systemd
systemctl --user start swarm-turbocharger

# Configure Hermes
hermes config set delegation.max_concurrent_children 50
```

## Health Verification

```bash
# After deployment, verify everything:
bash scripts/health_check.sh --json | python3 -m json.tool

# Expected output includes:
# - filesystem: healthy
# - resources: cpu < 80%, mem < 90%
# - docker: all containers running (if using Docker)
# - http: 8421 responding 200
# - modules: 19/19 healthy (swarm_network not yet implemented)

# Run full test suite
bash scripts/run_tests.sh --quick
# Expected: ~1,982 pytest tests passed, 0 failed
# Validation engine: 3,135 tests across 22 modules → 157/100 Singularity
```

### Validation Engine (Enterprise Grade)

```bash
# Run full validation (produces Singularity score)
python3 dashboard/run_validation.py

# Expected output:
# - base_score: 100.0 (all tests passing)
# - transcendent_bonus: +57.0 (8 singularity axes)
# - final_score: 157.0 → Certification: "Singularity"
# - module_count: 22
# - total_sloc: ~78,392
# - total_tests: 3,135
```

## Git Repository Setup

```bash
# Initialize local repo (run from enterprise/ directory)
cd /home/hunter/Desktop/Enterprise\\ Builder/enterprise
git init
git config user.email "your@email.com"
git config user.name "Your Name"
git add .
git commit -m "Initial platform import"
git branch -M main

# Add remote when GitHub org/repo created (HTTPS)
git remote add origin https://github.com/your-org/enterprise-ai-platform.git
git push -u origin main
```

### SSH Key Setup (Recommended for CI/CD)

```bash
# Generate ed25519 key for this project
ssh-keygen -t ed25519 -C "your@email.com" -f ~/.ssh/enterprise_ai_platform -N ""

# Add to SSH config (creates github.com-enterprise host alias)
cat >> ~/.ssh/config << 'EOF'

# Enterprise AI Platform
Host github.com-enterprise
    HostName github.com
    User git
    IdentityFile ~/.ssh/enterprise_ai_platform
    IdentitiesOnly yes
EOF

# Add public key to GitHub: Settings → SSH and GPG keys → New SSH key
cat ~/.ssh/enterprise_ai_platform.pub

# Verify connection (accept host key on first run)
ssh-keyscan github.com >> ~/.ssh/known_hosts
ssh -T git@github.com-enterprise
# → "Hi username! You've successfully authenticated..."

# Switch remote to SSH
cd /home/hunter/Desktop/Enterprise\\ Builder/enterprise
git remote set-url origin git@github.com-enterprise:your-org/enterprise-ai-platform.git
git push -u origin main
```

### GitHub Repository Creation (Prerequisite)

**Create the repository on GitHub BEFORE pushing:**

1. Go to https://github.com/organizations/your-org/repositories/new
2. Repository name: `enterprise-ai-platform`
3. Private ✓
4. **Do NOT** initialize with README, .gitignore, or license (we have those)
5. Create repository

Then run the push commands above.

### Branch Protection (Configure on GitHub)

After first push, enable on repository: Settings → Branches → Add rule for `main`:
- ✅ Require a pull request before merging
- ✅ Require approvals (1+)
- ✅ Require status checks to pass (e.g., CI workflow)
- ✅ Require branches to be up to date before merging
- ✅ Include administrators

## Authoring a New Module (autonomy / tooling layer)

The kernel auto-discovers modules — **no kernel edits needed** to add a capability. Steps that worked for the 2026-08-02 autonomy-layer build:

1. Create `modules/<name>/__init__.py` + `modules/<name>/<name>.py` (core logic) + `modules/<name>/tests/`.
   - `__init__.py` sets `__version__`, `__all__`, and a `@module(name="<name>", version="1.0.0")` class extending `Module`.
   - Import from `enterprise.platform_kernel`: `Module, module, HealthStatus, EventBus, EventPriority`.
   - Implement the abstract `async initialize()`, `async health_check() -> HealthStatus`, `async shutdown()`; add `def set_event_bus(self, eb)` storing `self._event_bus`. (name/version/status/config/module_id come from base — don't redefine.)
2. Keep core logic in sibling file(s), **stdlib-only**, and wrap any third-party import in try/except so imports never crash. Dependency-inject external adapters (HTTP opener, embedder) so tests run hermetically with zero network.
3. Register in `config.yaml` under `modules.<name>`: enabled/priority/required/startup_timeout_sec/health_check_interval_sec/config.
4. Test via pytest: `python3 -m pytest modules/<name>/tests -q` (pyproject: `asyncio_mode=auto`, `pythonpath=["."]`, `--strict-markers`). Convention: 30-60 real tests per module, `tmp_path` for all IO, no fake data.
5. Integration check: `python3 -m pytest -q -p no:cacheprovider` (full suite) + confirm the ModuleRegistry logs "Discovered N modules" including the new one.

Reference: `references/module-authoring.md` — exact kernel API, the parallel swarm-delegation recipe, and the 4-module build (skill_factory, task_harness, gateway, semantic_memory).

## Pitfalls

- **Port conflicts**: Dashboard and API gateway both bind :8421 in some configs. Verify only one service uses :8421 (the gateway serves both HTML and API).
- **urllib3 required**: The swarm turbocharger needs `pip install urllib3`. If missing, install before starting.
- **pytest anyio**: Always use `-p no:anyio` flag. Already in pyproject.toml addopts.
- **Import from parent dir**: Never run Python from inside `enterprise/`. Use `cd ~/Desktop/Enterprise\\ Builder && python3 -c "import sys; sys.path.insert(0,'enterprise'); from enterprise..."` or set `PYTHONPATH=/home/hunter/Desktop/Enterprise\\ Builder:$PYTHONPATH`
- **Turbocharger port bind**: Port 8922 can get stuck in TIME_WAIT. The script has `SO_REUSEADDR` set. If port is stuck, wait 60s or use `fuser -k 8922/tcp`.
- **Docker on MT7921e**: When running multiple Docker services that make API calls, ensure the turbocharger is running FIRST — otherwise the initial burst of container health checks can trigger a deauth cycle.
- **Test import paths**: Some module tests have hardcoded paths (e.g., `/home/hunter/Desktop/Eni Builder/...` instead of `/home/hunter/Desktop/Enterprise Builder/...`). Fix before running: `sed -i 's|Eni Builder|Enterprise Builder|g' modules/*/tests/*.py`
- **Test counts**: pytest collects ~1,982 tests; validation engine reports 3,135 (includes integration/functional suites). Both should be 0 failures.
- **`PlatformOS.initialize()` is SYNC** (not async) — call `p.initialize(config_path=Path(...), modules_path=Path(...))` WITHOUT `await`; only `await p.start()` is async. Awaiting it throws `TypeError: 'NoneType' object can't be awaited`. Also `ConfigurationLoader` expects a `Path` object, not a `str`, or it fails with `'str' object has no attribute 'exists'`.
- **Push to `main` rejected (GH013) = branch protection**: if the repo enforces "Changes must be made through a pull request," direct `git push origin main` is declined. Commit locally, then `git branch -M feature/<name>` and push the feature branch (`git push origin feature/<name>`); the remote prints the PR creation URL. Creating the PR via `gh` requires auth (often not set on the box — `gh pr create` fails with "gh auth login"); hand LO the printed `pull/new/...` link instead.

## Documentation Package

For client/investor presentations:

| Document | Path | Audience |
|----------|------|----------|
| Business Proposal | `enterprise/docs/BUSINESS_PROPOSAL.md` | CTO, VP Eng, Investors |
| Presentation | `enterprise/docs/PRESENTATION.md` | Clients, partners, board |
| Technical Reference | `enterprise/docs/TECHNICAL_REFERENCE.md` | Engineers, DevOps |
| Validation Report | `enterprise/Enterprise_Validation/VALIDATION_REPORT.md` | Auditors, Compliance |