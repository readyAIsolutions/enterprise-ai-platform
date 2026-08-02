# ENI Enterprise Platform — Docker Infrastructure

Complete containerization infrastructure for the ENI Enterprise Platform.
Multi-stage production builds, development hot-reload, full orchestration
of 14+ services with health checks, resource limits, and restart policies.

## Architecture

```
docker/
  Dockerfile              Multi-stage production build (builder → runtime)
  Dockerfile.dev          Development build with hot-reload + dev tools
  docker-compose.yml      Full orchestration of 14+ services
  .dockerignore           Build context exclusions for lean images
  Makefile                Build / run / test / deploy automation
  README.md               This file
```

## Services

### Core Platform
| Service | Port | Description |
|---------|------|-------------|
| `kernel` | 8000 | Platform kernel — module registry, event bus, health orchestration |
| `api-gateway` | 8421 | FastAPI REST gateway — auth, rate limiting, OpenAPI docs |
| `dashboard` | 8421 | Enterprise admin dashboard — real-time monitoring UI |
| `event-hub` | 8900 | Central event routing backbone — pub/sub, dead-letter queue |
| `service-mesh` | 8910 | Service discovery, circuit breaking, load balancing |

### ENI Swarm Ecosystem
| Service | Port | Description |
|---------|------|-------------|
| `eni-swarm` | 8420 | ENI Swarm core — 50-builders, master driver, health monitoring |
| `swarm-turbocharger` | 8922 | Connection optimization — 80 concurrent at -48dBm signal |
| `free-router` | 8920 | Intelligent load-aware request routing |

### Claude Code Infrastructure
| Service | Port | Description |
|---------|------|-------------|
| `claude-code-server` | 9120 | FastAPI + WebSocket remote session server |

### Enterprise Modules (10)
| Service | Description |
|---------|-------------|
| `module-knowledge-graph` | Knowledge graph entities and relationships |
| `module-privacy-data` | Data governance and classification |
| `module-safety-governance` | Guardrails, incidents, compliance |
| `module-prompt-context` | Prompt engineering and context management |
| `module-release-change` | Release pipeline and change management |
| `module-agent-coordination` | Multi-agent task distribution |
| `module-customer-experience` | Customer-facing integrations |
| `module-developer-experience` | Developer tooling and SDK |
| `module-innovation-rd` | R&D experimentation framework |
| `module-disaster-recovery` | Backup, restore, failover |
| `module-research-verification` | Claim detection and evidence synthesis |
| `module-enterprise-validation` | Validation engine and compliance |
| `module-eni-compression` | Context compression bridge |
| `module-eni-kb` | ENI knowledge base bridge |

### Infrastructure
| Service | Port | Description |
|---------|------|-------------|
| `redis` | 6379 | Caching, message broker, rate limiting |
| `postgres` | 5432 | Primary relational database |
| `prometheus` | 9090 | Metrics collection and alerting |
| `grafana` | 3000 | Dashboard visualization |

## Quick Start

### Prerequisites
- Docker 24+ and Docker Compose v2
- 4 GB RAM, 10 GB disk space minimum
- Python 3.11+ (for local dev only)

### Production Deployment
```bash
# From enterprise/ root:
cd /home/hunter/Desktop/Eni\ Builder/enterprise

# Build and start everything
make -f docker/Makefile build
make -f docker/Makefile run

# Check health
make -f docker/Makefile status

# View logs
make -f docker/Makefile logs
```

### Development Mode
```bash
# Build dev image with hot-reload
make -f docker/Makefile build-dev

# Start in dev mode
make -f docker/Makefile run-dev

# Shell into container
make -f docker/Makefile shell
```

### Starting Specific Service Groups
```bash
# Core infrastructure only
make -f docker/Makefile run-core

# Swarm ecosystem only
make -f docker/Makefile run-swarm
```

## Dockerfile Details

### Production (`Dockerfile`)
- **Stage 1 (builder):** Installs full Python dependency tree into a virtualenv
- **Stage 2 (runtime):** Copies only venv + source, runs as non-root `eni` user (UID 1000)
- Base: `python:3.11-slim` (~50 MB compressed)
- Health check: `curl http://localhost:$PORT/health` every 30s
- Environment: `ENI_ENV=production`, `PYTHONUNBUFFERED=1`

### Development (`Dockerfile.dev`)
- Single-stage with full dev toolchain (ruff, mypy, pytest, debugpy, watchdog)
- Hot-reload via uvicorn `--reload`
- Non-root user with `/bin/bash`
- All 8 service ports exposed

## Health Checks

Every service has a health check configured:

```yaml
healthcheck:
  test: ["CMD", "curl", "-sf", "http://localhost:<port>/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 15s
```

Services `depends_on` healthy upstreams, ensuring ordered startup:
```
redis/postgres → kernel → api-gateway → dashboard
redis/postgres → kernel → event-hub → service-mesh
redis/postgres → kernel → eni-swarm → swarm-turbocharger → free-router
redis/postgres → kernel → claude-code-server
```

## Resource Limits

| Tier | CPUs Limit | Memory Limit | CPUs Reserve | Memory Reserve |
|------|-----------|-------------|-------------|----------------|
| Heavy | 4 | 1024M | 1 | 512M |
| Standard | 2 | 512M | 0.5 | 256M |
| Light | 1 | 256M | 0.25 | 128M |
| Micro | 0.5 | 128M | 0.1 | 64M |

Heavy: `eni-swarm`, `claude-code-server`
Standard: `kernel`, `api-gateway`, `dashboard`, `event-hub`, `service-mesh`, `swarm-turbocharger`, `free-router`, `module-knowledge-graph`, `module-agent-coordination`, `module-research-verification`
Light: All 10 module services
Micro: `redis`, `prometheus`, `grafana`

## Restart Policies

All services use `restart: unless-stopped`:
- Automatic recovery from crashes
- Survives Docker daemon restarts
- Stops only on explicit `docker compose stop` or `docker compose down`

## Makefile Targets

| Target | Description |
|--------|-------------|
| `build` | Build production Docker image (multi-stage) |
| `build-dev` | Build development image with hot-reload |
| `build-no-cache` | Build without layer cache |
| `run` | Start full platform (detached) |
| `run-core` | Start core infrastructure only |
| `run-swarm` | Start ENI Swarm ecosystem only |
| `stop` | Stop all services |
| `down` | Stop and remove containers + networks |
| `restart` | Fresh restart (down + run) |
| `rebuild` | Full rebuild and restart |
| `test` | Run unit tests in container |
| `test-integration` | Run integration tests |
| `test-health` | Health check all services |
| `deploy` | Production deploy (build + up --force-recreate) |
| `deploy-swarm` | Deploy as Docker Swarm stack |
| `deploy-rolling` | Rolling update with zero downtime |
| `push` | Tag and push to registry |
| `status` | Show platform health with HTTP checks |
| `logs` | Tail all service logs |
| `shell` | Bash shell in kernel container |
| `ci` | CI pipeline (lint + build + test + health) |
| `ship` | Full ship pipeline (build → test → push → deploy) |

## Networking

Two bridge networks:
- `eni-internal`: Inter-service communication (all services)
- `eni-public`: External-facing services (api-gateway, dashboard)

## Volumes

| Volume | Purpose |
|--------|---------|
| `eni-kernel-data` | Kernel runtime data |
| `eni-swarm-data` | Swarm builder state and task rosters |
| `eni-dashboard-static` | Dashboard static assets |
| `eni-claude-code-sessions` | Claude Code session data |
| `eni-redis-data` | Redis persistence |
| `eni-postgres-data` | PostgreSQL data |
| `eni-prometheus-data` | Prometheus TSDB |
| `eni-grafana-data` | Grafana dashboards and config |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KERNEL_PORT` | 8000 | Kernel port |
| `GATEWAY_PORT` | 8421 | API Gateway port |
| `DASHBOARD_PORT` | 8421 | Dashboard port |
| `ENI_SWARM_PORT` | 8420 | ENI Swarm port |
| `TURBOCHARGER_PORT` | 8922 | Swarm Turbocharger port |
| `FREE_ROUTER_PORT` | 8920 | Free Router port |
| `CLAUDE_CODE_PORT` | 9120 | Claude Code Server port |
| `EVENT_HUB_PORT` | 8900 | Event Hub port |
| `SERVICE_MESH_PORT` | 8910 | Service Mesh port |
| `REDIS_PORT` | 6379 | Redis port |
| `POSTGRES_PORT` | 5432 | PostgreSQL port |
| `POSTGRES_PASSWORD` | eni_secure_2024 | PostgreSQL password |
| `PROMETHEUS_PORT` | 9090 | Prometheus port |
| `GRAFANA_PORT` | 3000 | Grafana port |

## Troubleshooting

### Container won't start
```bash
make logs-service SVC=<service-name>
docker inspect eni-<service>
```

### Health check failing
```bash
make shell-service SVC=<service>
curl http://localhost:<port>/health
```

### Port conflicts
Override with environment variables:
```bash
KERNEL_PORT=9000 make run
```

### Rebuild after code changes
```bash
make rebuild  # Full rebuild + restart
# or for faster iteration:
docker compose -f docker/docker-compose.yml up -d --no-deps --build <service>
```