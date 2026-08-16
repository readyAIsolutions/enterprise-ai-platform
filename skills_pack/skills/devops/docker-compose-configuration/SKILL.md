---
name: docker-compose-configuration
description: Build, validate, and maintain Docker Compose configurations for multi-service applications with proper networking, volumes, health checks, and service dependencies
tags: [docker, compose, devops, configuration, testing]
related: [python-app-packaging, local-llm-serving]
references:
  - references/demiurge-marketing-os-example.md
  - references/dockerfile-best-practices.md
templates:
  - templates/docker-compose-test-template.py
---

# Docker Compose Configuration Management

## Purpose
Build, validate, and maintain Docker Compose configurations for multi-service applications with proper networking, volumes, health checks, and service dependencies. Covers the complete lifecycle from initial setup to production deployment.

## When to Use
- Setting up Docker Compose for new multi-service applications
- Adding new services to existing Docker Compose configurations
- Validating Docker Compose configurations for syntax and structure
- Implementing proper networking and volume management
- Creating unit tests for Docker configurations

## Key Components

### 1. Service Definition
- Define all required services with appropriate images
- Configure environment variables using `${VAR}` or `${VAR:-default}` syntax
- Set proper restart policies (`unless-stopped`, `on-failure`, etc.)
- Implement health checks for all services
- Define proper service dependencies with `depends_on`

### 2. Networking
- Create bridge networks for secure service communication
- Assign all services to the same network for inter-service communication
- Use service names for DNS resolution between containers

### 3. Volumes
- Use named volumes for persistent data storage
- Mount configuration files as read-only volumes when appropriate
- Define volume mappings for data directories
- Ensure proper permissions for volume mounts

### 4. Environment Variables
- Reference required environment variables using `${VAR_NAME}` syntax
- Provide default values where appropriate using `${VAR_NAME:-default}` syntax
- Document all environment variables in comments

## Implementation Steps

### 1. Initial Setup
1. Identify all required services for the application
2. Determine networking requirements
3. Plan volume requirements for persistent data
4. List all environment variables needed

### 2. Service Configuration
1. Define each service with appropriate image
2. Configure environment variables
3. Set up volume mappings
4. Implement health checks
5. Define service dependencies

### 3. Network Configuration
1. Create a bridge network
2. Attach all services to the network
3. Verify DNS resolution between services

### 4. Volume Configuration
1. Define named volumes for persistent data
2. Map volumes to appropriate service directories
3. Set proper read/write permissions

### 5. Validation
1. Check YAML syntax
2. Validate with `docker compose config`
3. Verify all services are defined
4. Confirm networks and volumes are properly configured

## Best Practices

### Configuration Structure
- Use descriptive service names
- Include comments explaining each service's purpose
- Organize services logically in the file
- Use consistent naming for networks and volumes

### Health Checks
- Implement health checks for all services
- Use appropriate test commands for each service type
- Set reasonable intervals and timeouts
- Define retry counts for failure detection

### Environment Variables
- Reference all sensitive data through environment variables
- Provide example values in comments
- Use default values where appropriate
- Document variable purpose in comments

### Dependencies
- Define service startup order using `depends_on`
- Use health check conditions when available
- Avoid circular dependencies
- Test startup order in development

## Testing

### Unit Tests
Create tests to verify:
1. Docker Compose file existence
2. YAML syntax validity
3. Required services presence
4. Network definitions
5. Volume definitions
6. Environment variable references

### Validation Commands
```bash
# Check YAML syntax
python -c "import yaml; yaml.safe_load(open('docker-compose.yml'))"

# Validate Docker Compose configuration
docker compose -f docker-compose.yml config

# Alternative syntax for older Docker versions
docker-compose -f docker-compose.yml config
```

## Common Pitfalls

### 1. Duplicate Environment Variables
- Avoid duplicate environment variable definitions
- Check for typos in variable names
- Ensure consistent naming conventions

### 2. Missing Dependencies
- Verify all service dependencies are defined
- Check `depends_on` conditions are correct
- Test startup order

### 3. Volume Permissions
- Ensure proper file permissions for mounted volumes
- Check ownership settings for data directories
- Verify read/write access as needed

### 4. Network Configuration
- Confirm all services are on the same network
- Verify DNS resolution between services
- Check for network naming conflicts

### 5. Health Check Failures
- Use appropriate test commands for each service
- Set reasonable timeout values
- Define proper retry counts

## Example Structure
```yaml
version: '3.8'

services:
  service-name:
    image: image-name:tag
    container_name: container-name
    restart: unless-stopped
    environment:
      ENV_VAR: ${ENV_VAR:-default}
    volumes:
      - volume-name:/container/path
    networks:
      - network-name
    depends_on:
      dependent-service:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "command", "args"]
      interval: 30s
      timeout: 10s
      retries: 3

networks:
  network-name:
    driver: bridge

volumes:
  volume-name:
```