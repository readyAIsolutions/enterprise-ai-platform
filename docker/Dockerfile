# =============================================================================
# ENI Enterprise Platform — Multi-stage Production Docker Build
# python:3.11-slim base, non-root execution, production-grade
# Serves: api-gateway, dashboard, eni-swarm, claude-code-server,
#         swarm-turbocharger, free-router, event-hub, service-mesh,
#         + 20 enterprise modules + supporting services
# =============================================================================

# ── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy dependency manifests first for layer caching
COPY requirements.txt pyproject.toml ./

# Install dependencies into a virtualenv for clean copy to final stage
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip setuptools wheel && \
    /opt/venv/bin/pip install -r requirements.txt 2>/dev/null || \
    /opt/venv/bin/pip install fastapi uvicorn[standard] websockets \
        redis httpx pydantic pydantic-settings pyyaml python-dotenv \
        psutil structlog prometheus-client aiohttp

# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    ENI_ENV="production" \
    TZ="UTC"

# Create non-root user and group
RUN groupadd --system --gid 1000 eni && \
    useradd --system --uid 1000 --gid eni --no-create-home --shell /sbin/nologin eni

# Runtime system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        libmagic1 \
        procps \
    && rm -rf /var/lib/apt/lists/*

# Copy virtualenv from builder
COPY --from=builder /opt/venv /opt/venv

# Create app directory with proper ownership
WORKDIR /app

# Copy entire enterprise source tree
COPY . .

# Ensure non-root user owns the app directory
RUN chown -R eni:eni /app

# Drop privileges
USER eni

# Health check (overridable per service via docker-compose)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:${PORT:-8000}/health || exit 1

EXPOSE 8000

# Default command — platform kernel entrypoint (overridden per service)
CMD ["python", "-m", "kernel"]