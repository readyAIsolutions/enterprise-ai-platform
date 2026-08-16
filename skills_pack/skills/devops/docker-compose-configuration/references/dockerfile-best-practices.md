# Dockerfile Best Practices

## Multi-stage Builds

Use multi-stage builds to reduce image size and improve security:

```dockerfile
# Build stage
FROM python:3.12-slim-bookworm AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Runtime stage
FROM python:3.12-slim-bookworm AS runtime

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --system --gid 1000 appuser && \
    useradd --system --uid 1000 --gid appuser --no-create-home appuser

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Set working directory
WORKDIR /app

# Copy application code
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Expose port
EXPOSE 8000

# Default command
CMD ["python", "app.py"]
```

## Security Best Practices

1. **Use Official Base Images**: Start with official images from trusted sources
2. **Run as Non-Root User**: Create and use a non-root user
3. **Minimize Layers**: Combine RUN commands to reduce layers
4. **Scan for Vulnerabilities**: Use tools like Trivy or Clair
5. **Sign Images**: Use Docker Content Trust or Notary

## Performance Best Practices

1. **Order Instructions Strategically**: Place frequently changing instructions later
2. **Use .dockerignore**: Exclude unnecessary files from the build context
3. **Leverage Build Cache**: Order COPY instructions to maximize cache hits
4. **Multi-stage Builds**: Separate build-time and runtime dependencies

## Health Checks

Implement proper health checks to ensure containers are running correctly:

```dockerfile
# Simple HTTP health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Database health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD pg_isready -U postgres -d mydb

# Application-specific health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')"
```

## Environment Variables

Properly handle environment variables:

```dockerfile
# Set default values
ENV DATABASE_URL=postgresql://localhost:5432/mydb
ENV REDIS_URL=redis://localhost:6379
ENV PORT=8000

# Document required environment variables
# Required: DATABASE_URL, REDIS_URL
# Optional: LOG_LEVEL (default: INFO)
```

## Labels

Add metadata labels for better image management:

```dockerfile
LABEL maintainer="team@example.com"
LABEL version="1.0.0"
LABEL description="My Application Description"
LABEL org.opencontainers.image.source="https://github.com/example/myapp"
LABEL org.opencontainers.image.licenses="MIT"
```