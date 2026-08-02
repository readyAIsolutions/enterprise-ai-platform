# =============================================================================
# ENI Enterprise Platform — Multi-stage Docker Build (ROOT WRAPPER)
# This file delegates to docker/Dockerfile.
# Use: docker build -f docker/Dockerfile .
# Or:  make -f docker/Makefile build
# =============================================================================

FROM python:3.11-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl git && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --upgrade pip setuptools wheel && /opt/venv/bin/pip install -r requirements.txt

FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/opt/venv/bin:$PATH" ENI_ENV="production"
RUN groupadd --system --gid 1000 eni && useradd --system --uid 1000 --gid eni --no-create-home --shell /sbin/nologin eni
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl libmagic1 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY . .
RUN chown -R eni:eni /app
USER eni
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 CMD curl -f http://localhost:8000/health || exit 1
EXPOSE 8000
CMD ["python", "-m", "kernel"]