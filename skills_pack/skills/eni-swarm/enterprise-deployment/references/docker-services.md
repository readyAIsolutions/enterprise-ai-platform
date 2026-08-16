# Docker Compose Service Reference

All services defined in `enterprise/docker/docker-compose.yml`. 14+ containers.

| Service | Port | Image/Context | Health Check | Resources |
|---------|------|--------------|-------------|-----------|
| kernel | 8000 | eni-enterprise | curl :8000/api/health | heavy (2 CPU, 4GB) |
| api-gateway | 8421 | eni-enterprise | curl :8421/api/v1/health/live | heavy (2 CPU, 2GB) |
| dashboard | 8421 | eni-enterprise | curl :8421/api/health | standard (1 CPU, 1GB) |
| eni-swarm | 8420 | eni-enterprise | curl :8420/health | heavy (2 CPU, 4GB) |
| swarm-turbocharger | 8922 | python:3.11-slim | curl :8922/health | light (0.5 CPU, 512MB) |
| free-router | 8920 | python:3.11-slim | curl :8920/health | light (0.5 CPU, 512MB) |
| claude-code-server | 9120 | eni-enterprise | curl :9120/health | standard (1 CPU, 2GB) |
| event-hub | 8900 | eni-enterprise | curl :8900/health | light (0.5 CPU, 512MB) |
| service-mesh | 8910 | eni-enterprise | curl :8910/health | light (0.5 CPU, 512MB) |
| redis | 6379 | redis:7-alpine | redis-cli ping | light (0.5 CPU, 256MB) |
| postgres | 5432 | postgres:16-alpine | pg_isready | standard (1 CPU, 1GB) |
| prometheus | 9090 | prom/prometheus | curl :9090/-/healthy | light (0.5 CPU, 512MB) |
| grafana | 3000 | grafana/grafana | curl :3000/api/health | light (0.5 CPU, 512MB) |
| knowledge-graph | 8101 | eni-enterprise | curl :8101/health | standard |
| privacy-data | 8102 | eni-enterprise | curl :8102/health | standard |
| safety-governance | 8103 | eni-enterprise | curl :8103/health | standard |
| prompt-context | 8104 | eni-enterprise | curl :8104/health | light |
| release-change | 8105 | eni-enterprise | curl :8105/health | light |
| agent-coordination | 8106 | eni-enterprise | curl :8106/health | light |
| + 4 more modules | 8107-8110 | eni-enterprise | curl :81XX/health | light |

**Resource tiers:** heavy (2 CPU, 2-4GB), standard (1 CPU, 1-2GB), light (0.5 CPU, 256-512MB), micro (0.25 CPU, 128MB).

**Restart policy:** `unless-stopped` on all services.

**Networking:** All services on `eni-network` bridge. External ports mapped for api-gateway (8421), dashboard (8421), eni-swarm (8420), claude-code-server (9120), turbocharger (8922), free-router (8920), prometheus (9090), grafana (3000).

**Dependencies:** kernel starts first → api-gateway/dashboard/event-hub/service-mesh depend on kernel → module containers depend on api-gateway.
