# ENI Enterprise Operational Scripts

Production-ready CLI scripts for managing the ENI Enterprise AI Operating System.
Located at: `enterprise/scripts/`

| Script | Purpose | Exit Codes |
|--------|---------|------------|
| `deploy.sh` | Full deployment: check deps, install, start, verify | 0=success, 10=prereq, 11=build, 12=deploy, 13=health |
| `health_check.sh` | Comprehensive health check across all services | 0=healthy, 1=degraded, 2=unhealthy |
| `run_tests.sh` | Run test suite with pytest flags and coverage | 0=pass, 1=fail, 2=setup error |
| `backup.sh` | Backup configs, data, logs, state | 0=success, 10=backup fail, 2=setup |
| `restore.sh` | Restore from backup archive | 0=success, 10=restore fail, 11=not found |
| `start_all.sh` | Start every service in correct order | 0=success, 10=start fail, 11=health fail |
| `stop_all.sh` | Graceful shutdown of all services | 0=success, 10=stop fail |
| `status.sh` | Quick status overview of the platform | 0=healthy, 1=degraded, 2=down |

---

## Quick Reference

```bash
# Full deployment
./scripts/deploy.sh --yes

# Start everything
./scripts/start_all.sh

# Check status
./scripts/status.sh --short

# Comprehensive health
./scripts/health_check.sh

# Run all tests
./scripts/run_tests.sh --coverage

# Create backup
./scripts/backup.sh --name pre-upgrade --keep 5

# Stop everything gracefully
./scripts/stop_all.sh

# Restore from backup
./scripts/restore.sh backups/eni-enterprise-*.tar.gz
```

---

## deploy.sh

Full platform deployment with dependency verification, installation, and health checks.

```bash
./scripts/deploy.sh                 # Interactive deploy
./scripts/deploy.sh --yes           # Non-interactive (CI/CD)
./scripts/deploy.sh --check-only    # Only verify prerequisites
./scripts/deploy.sh --skip-tests    # Skip pre-deployment tests
./scripts/deploy.sh --env staging   # Target environment
```

### Phases
1. **Prerequisites**: Python 3.11/3.12, pip, directory structure, config files
2. **Environment**: Create `.env`, log/data directories
3. **Dependencies**: pip install from requirements.txt
4. **Tests**: Run pre-deployment test suite
5. **Deploy**: Docker Compose or direct Python deployment
6. **Verify**: Container health + HTTP endpoint checks

---

## health_check.sh

Multi-layer health verification of the entire platform.

```bash
./scripts/health_check.sh               # Full check (filesystem, resources, Python, Docker, HTTP, Redis, logs)
./scripts/health_check.sh --quick       # Fast check (HTTP endpoints + container status only)
./scripts/health_check.sh --json        # Machine-readable JSON output
./scripts/health_check.sh --endpoint http://custom:9090/health  # Check custom endpoint
```

### Check Layers
- **Filesystem**: Directory existence, config files, disk usage, write permissions
- **Resources**: Memory, CPU load, file descriptors
- **Python**: Version, required packages, kernel module importability
- **Docker**: Container states, health status per container
- **HTTP**: Kernel :8000, API Gateway :8080, Dashboard :8421
- **Redis**: Connectivity via redis-cli or Python client
- **Logs**: Existence, recent error counts

---

## run_tests.sh

Flexible test execution with pytest, coverage, and parallel runs.

```bash
./scripts/run_tests.sh                    # Full test suite
./scripts/run_tests.sh --unit             # Unit tests only (-m "unit")
./scripts/run_tests.sh --integration      # Integration tests only (-m "integration")
./scripts/run_tests.sh --module agent_coordination  # Single module
./scripts/run_tests.sh --coverage         # HTML coverage to htmlcov/
./scripts/run_tests.sh --parallel         # Parallel with pytest-xdist (-n auto)
./scripts/run_tests.sh --verbose --fail-fast  # Verbose, stop on first failure
./scripts/run_tests.sh -- -k "test_health"    # Pass extra args to pytest
```

### Test Modes
| Flag | Mode | Targets |
|------|------|---------|
| `--all` (default) | Full suite | tests/, modules/ (excl. safety_governance) |
| `--unit` | Unit only | tests/, modules/ with -m "unit" |
| `--integration` | Integration | tests/integration/, modules/ with -m "integration" |
| `--e2e` | End-to-end | tests/ with -m "e2e" |
| `--module NAME` | Single module | modules/NAME/tests/ |

---

## backup.sh

Creates timestamped, compressed backup archives of the entire platform state.

```bash
./scripts/backup.sh                         # Full backup to backups/
./scripts/backup.sh --name pre-upgrade      # Custom name
./scripts/backup.sh --incremental           # Incremental backup
./scripts/backup.sh --output /mnt/backups   # Custom output directory
./scripts/backup.sh --no-compress           # Skip tar.gz compression
./scripts/backup.sh --keep 5                # Rotate, keep only last 5
./scripts/backup.sh --dry-run               # Preview what would be backed up
```

### Backup Contents
- `configs/` - config.yaml, docker-compose.yml, pyproject.toml, requirements.txt, .env
- `data/` - Full data directory
- `logs/` - Last 1000 lines of each log file
- `inventory.json` - Module listing with file counts
- `git_commit.txt` / `git_status.txt` - Git metadata (if available)
- `MANIFEST.txt` - Backup metadata

---

## restore.sh

Restores from a backup archive with selective options and safety checks.

```bash
./scripts/restore.sh backups/eni-enterprise-full-*.tar.gz               # Full restore
./scripts/restore.sh backups/eni-enterprise-full-*.tar.gz --configs-only # Configs only
./scripts/restore.sh backups/eni-enterprise-full-*.tar.gz --data-only    # Data only
./scripts/restore.sh backups/eni-enterprise-full-*.tar.gz --dry-run      # Preview
./scripts/restore.sh --list                                              # List available backups
./scripts/restore.sh backups/eni-enterprise-full-*.tar.gz --force        # Skip confirmation
```

### Safety Features
- Validates archive integrity before extraction
- Creates `.bak.TIMESTAMP` copies of overwritten files
- Confirmation prompt (override with `--force`)
- Dry-run mode to preview changes
- Supports selective restore (configs-only, data-only)

---

## start_all.sh

Starts all platform services in correct dependency order.

```bash
./scripts/start_all.sh                  # Docker Compose (default)
./scripts/start_all.sh --direct         # Direct Python processes (no Docker)
./scripts/start_all.sh --daemon         # Run as background daemons
./scripts/start_all.sh --no-modules     # Core only (redis, kernel, gateway, dashboard)
./scripts/start_all.sh --skip-health    # Skip post-startup health check
```

### Startup Order
1. **Redis** (if available) → port 6379
2. **Platform Kernel** → port 8000
3. **API Gateway** → port 8080
4. **Dashboard** → port 8421 (direct) / 3000 (Docker)
5. **Modules** (10 enterprise modules, Docker Compose only)

---

## stop_all.sh

Gracefully shuts down all services with cleanup options.

```bash
./scripts/stop_all.sh                   # Graceful stop (SIGTERM, 10s timeout)
./scripts/stop_all.sh --force           # Force kill (SIGKILL)
./scripts/stop_all.sh --direct          # Stop direct processes only
./scripts/stop_all.sh --cleanup         # Full cleanup (PIDs, caches, .bak files)
./scripts/stop_all.sh --timeout 60      # Custom Docker stop timeout
```

### Shutdown Order
1. Docker Compose containers (reverse dependency order)
2. Direct processes via PID files
3. Remaining processes on known ports
4. Verification that all ports are free
5. Optional cleanup of PIDs, __pycache__, .pyc, .pytest_cache, .bak files

---

## status.sh

Quick overview of platform health and service states.

```bash
./scripts/status.sh                    # Full status overview
./scripts/status.sh --short            # One-line compact status
./scripts/status.sh --json             # Machine-readable JSON
./scripts/status.sh --watch            # Live refresh every 5 seconds
./scripts/status.sh --containers       # Docker containers only
./scripts/status.sh --processes        # Direct processes only
```

### Sections
- **Platform Info**: Directory, version, config, hostname, uptime, disk, Python
- **Quick Stats**: Module count, test files, Python files, backup count
- **Docker Containers**: Per-container state, health, ports
- **Processes**: Port bindings for kernel/API/dashboard/redis, PID file status
- **HTTP Endpoints**: Reachability of kernel/API/dashboard health endpoints

---

## Exit Codes

| Range | Meaning |
|-------|---------|
| 0 | Success / Healthy |
| 1 | Degraded (health_check) / Tests failed (run_tests) |
| 2 | Unhealthy / Setup error / Usage error |
| 10-19 | Deployment & backup errors |
| 20+ | Unused, reserved |

---

## Environment

Scripts auto-detect the platform root at `../` from the scripts directory. Key files:

| Path | Purpose |
|------|---------|
| `../config.yaml` | Platform configuration |
| `../docker-compose.yml` | Container orchestration |
| `../pyproject.toml` | Build & tool config |
| `../requirements.txt` | Python dependencies |
| `../.env` | Environment overrides |
| `../logs/` | Log output directory |
| `../data/` | Data storage directory |
| `../backups/` | Backup archive directory |
| `../.pids/` | Direct-mode PID files |

---

## Design Principles

- **Idempotent**: Scripts can be safely re-run without side effects
- **Error handling**: Every script uses `set -euo pipefail`, explicit error handling
- **Exit codes**: Consistent exit codes for CI/CD integration
- **Color output**: ANSI colors for readability; compatible with log files
- **Help flags**: Every script supports `--help` / `-h`
- **JSON output**: health_check.sh and status.sh support `--json` for automation
- **No hardcoded secrets**: All configurable via environment or flags
- **Safe by default**: Destructive operations require confirmation or `--force`