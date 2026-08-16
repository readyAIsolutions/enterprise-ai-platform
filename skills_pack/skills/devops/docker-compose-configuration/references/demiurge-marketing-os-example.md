# Demiurge Marketing OS Docker Compose Example

This reference shows a complete Docker Compose configuration for the Demiurge Marketing OS v2.0, which includes:

- PostgreSQL database with persistent storage
- Redis cache with AOF persistence
- Fonoster voice/SIP platform
- useSend email platform
- Odoo 19 CRM
- App server (Demiurge Marketing OS)

## Complete docker-compose.yml

```yaml
version: '3.8'

# Demiurge Marketing OS v2.0 — Self-Hosted Stack
#
# Services:
#   - postgres: Shared PostgreSQL for all services
#   - redis: Cache/session store
#   - fonoster: Voice/SIP platform (Fonoster gRPC API + SIP + Autopilot)
#   - usesend: Email platform (SMTP server + Web UI + Webhooks)
#   - odoo19: CRM (Odoo 19 Community Edition)
#   - app: Demiurge Marketing OS API + Unified Web Server
#
# Network: All services on 'demiurge-net' bridge
# Volumes: Persistent data in named volumes
#
# Usage:
#   docker compose -f docker/docker-compose.yml up -d
#   docker compose -f docker/docker-compose.yml logs -f

services:
  postgres:
    image: postgres:16-alpine
    container_name: demiurge-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: demiurge_mkt
      POSTGRES_USER: demiurge
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-changeme}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init-scripts:/docker-entrypoint-initdb.d:ro
    networks:
      - demiurge-net
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U demiurge -d demiurge_mkt"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: demiurge-redis
    restart: unless-stopped
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    networks:
      - demiurge-net
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

  fonoster:
    image: fonoster/fonoster:latest
    container_name: demiurge-fonoster
    restart: unless-stopped
    environment:
      FONOSTER_API_KEY: ${FONOSTER_API_KEY}
      FONOSTER_API_SECRET: ${FONOSTER_API_SECRET}
      FONOSTER_ACCESS_KEY_ID: ${FONOSTER_ACCESS_KEY_ID}
    networks:
      - demiurge-net
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  usesend:
    image: usesend/usesend:latest
    container_name: demiurge-usesend
    restart: unless-stopped
    environment:
      USESEND_API_KEY: ${USESEND_API_KEY}
    networks:
      - demiurge-net
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  odoo19:
    image: odoo:19.0
    container_name: demiurge-odoo19
    restart: unless-stopped
    environment:
      HOST: postgres
      USER: demiurge
      PASSWORD: ${POSTGRES_PASSWORD:-changeme}
    volumes:
      - odoo_data:/var/lib/odoo
      - ./odoo-addons:/mnt/extra-addons
    networks:
      - demiurge-net
    depends_on:
      postgres:
        condition: service_healthy

  app:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    container_name: demiurge-app
    restart: unless-stopped
    environment:
      DEMIURGE_MKT_POSTGRES_URL: postgresql://demiurge:***@postgres:5432/demiurge_mkt
      DEMIURGE_MKT_REDIS_URL: redis://redis:6379
      DEMIURGE_MKT_FONOSTER_API_KEY: ${FONOSTER_API_KEY}
      DEMIURGE_MKT_FONOSTER_API_SECRET: ${FONOSTER_API_SECRET}
      DEMIURGE_MKT_FONOSTER_ACCESS_KEY_ID: ${FONOSTER_ACCESS_KEY_ID}
      DEMIURGE_MKT_USESEND_API_KEY: ${USESEND_API_KEY}
      DEMIURGE_MKT_ODOO_URL: http://odoo19:8069
    volumes:
      - ../config:/app/config:ro
      - ../data:/app/data
    networks:
      - demiurge-net
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      fonoster:
        condition: service_started
      usesend:
        condition: service_started
      odoo19:
        condition: service_started

networks:
  demiurge-net:
    driver: bridge

volumes:
  postgres_data:
  redis_data:
  fonoster_data:
  usesend_data:
  odoo_data:
```

## Key Features of This Configuration

1. **Service Dependencies**: Each service properly depends on its required services
2. **Health Checks**: All services have appropriate health checks
3. **Persistent Storage**: Named volumes for all data that needs to persist
4. **Environment Variables**: Proper use of environment variables with default values
5. **Network Isolation**: All services on a single bridge network for secure communication
6. **Proper Restart Policies**: Services restart unless explicitly stopped
7. **Read-Only Volumes**: Configuration files mounted as read-only where appropriate

## Validation Commands

```bash
# Validate the configuration
docker compose -f docker/docker-compose.yml config

# Start all services
docker compose -f docker/docker-compose.yml up -d

# Check service status
docker compose -f docker/docker-compose.yml ps

# View logs
docker compose -f docker/docker-compose.yml logs -f
```