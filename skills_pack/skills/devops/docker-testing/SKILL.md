---
name: docker-testing
description: Create and maintain unit tests for Docker configurations, images, and Compose files to ensure reliability and correctness
tags: [docker, testing, validation, compose, containers]
related: [docker-compose-configuration, python-app-packaging]
references:
  - references/demiurge-marketing-os-test-example.md
  - ../coding/lo-project-standards/references/testing-with-external-dependencies.md
templates:
  - templates/docker-test-template.py
---

# Docker Testing

## Purpose
Create and maintain comprehensive unit tests for Docker configurations, images, and Compose files to ensure reliability, correctness, and proper functionality of containerized applications.

## When to Use
- Validating Docker Compose configurations for syntax and structure
- Testing Docker image builds for correctness
- Verifying service dependencies and networking
- Ensuring environment variables are properly configured
- Checking volume mounts and permissions
- Validating health checks and startup procedures

## Key Components

### 1. Docker Compose Validation
- YAML syntax validation
- Service presence verification
- Network and volume configuration checks
- Environment variable reference validation
- Dependency validation

### 2. Docker Image Testing
- Image build validation
- Layer optimization checks
- Security scanning
- Size optimization verification

### 3. Service Integration Testing
- Inter-service communication
- Health check validation
- Startup order verification
- Data persistence testing

## Implementation Steps

### 1. Test Setup
1. Identify test requirements for the Docker configuration
2. Determine which services need validation
3. Plan test scenarios for different components
4. Set up test environment

### 2. YAML Syntax Validation
1. Parse Docker Compose file as YAML
2. Check for syntax errors
3. Validate structure against Docker Compose schema
4. Verify file existence

### 3. Service Validation
1. Verify all required services are defined
2. Check service configurations (images, environment, volumes)
3. Validate service dependencies
4. Confirm health checks are properly defined

### 4. Network and Volume Testing
1. Verify network definitions
2. Check volume configurations
3. Validate mount points and permissions
4. Test inter-service connectivity

### 5. Environment Variable Testing
1. Verify environment variables are referenced
2. Check for proper variable substitution
3. Validate default values where applicable
4. Ensure sensitive data is handled properly

## Best Practices

### Test Organization
- Use descriptive test function names
- Group related tests in classes or modules
- Include setup and teardown methods
- Use fixtures for common test data

### Validation Techniques
- Parse YAML to validate syntax
- Use subprocess to run Docker commands
- Implement timeouts for long-running tests
- Handle Docker not installed gracefully

### Error Handling
- Provide clear error messages
- Skip tests when dependencies are missing
- Handle timeouts appropriately
- Log failures for debugging

## Testing Patterns

### File Existence and Syntax
```python
def test_docker_compose_file_exists():
    """Test that docker-compose.yml file exists"""
    compose_file = Path("docker/docker-compose.yml")
    assert compose_file.exists(), "docker-compose.yml file should exist"

def test_docker_compose_syntax():
    """Test that docker-compose.yml has valid YAML syntax"""
    compose_file = Path("docker/docker-compose.yml")
    with open(compose_file, 'r') as f:
        try:
            yaml.safe_load(f)
        except yaml.YAMLError as e:
            pytest.fail(f"docker-compose.yml has invalid YAML syntax: {e}")
```

### Service Validation
```python
def test_required_services_present():
    """Test that all required services are present in docker-compose.yml"""
    compose_file = Path("docker/docker-compose.yml")
    with open(compose_file, 'r') as f:
        compose_data = yaml.safe_load(f)
    
    required_services = ['service1', 'service2']
    services = compose_data.get('services', {})
    
    for service in required_services:
        assert service in services, f"Service '{service}' should be present"
```

### Docker Command Validation
```python
def test_docker_compose_config():
    """Test docker-compose config validation"""
    try:
        # Try docker compose first (new syntax)
        result = subprocess.run(
            ["docker", "compose", "-f", "docker/docker-compose.yml", "config"],
            capture_output=True,
            text=True,
            cwd=".",
            timeout=30
        )
        if result.returncode != 0:
            # Try docker-compose (old syntax)
            result = subprocess.run(
                ["docker-compose", "-f", "docker/docker-compose.yml", "config"],
                capture_output=True,
                text=True,
                cwd=".",
                timeout=30
            )
        assert result.returncode == 0, f"Validation failed: {result.stderr}"
    except subprocess.TimeoutExpired:
        pytest.fail("Validation timed out")
    except FileNotFoundError:
        # Docker not installed, skip this test
        pytest.skip("Docker not installed")
```

## Common Pitfalls

### 1. Docker Not Installed
- Handle gracefully by skipping tests
- Provide clear messaging about skipped tests
- Don't fail entire test suite

### 2. Timeout Issues
- Set appropriate timeouts for Docker commands
- Handle long-running validations
- Provide progress feedback

### 3. Environment Dependencies
- Isolate tests from host environment
- Use mock data where appropriate
- Handle missing dependencies gracefully

### 4. Version Differences
- Support both `docker compose` and `docker-compose`
- Handle different Docker versions
- Test with common Docker installations

## Example Test Suite
```python
"""
Test suite for Docker configuration validation
"""

import os
import subprocess
import pytest
import yaml
from pathlib import Path

def test_docker_compose_file_exists():
    """Test that docker-compose.yml file exists"""
    compose_file = Path("docker/docker-compose.yml")
    assert compose_file.exists(), "docker-compose.yml file should exist"

def test_docker_compose_syntax():
    """Test that docker-compose.yml has valid YAML syntax"""
    compose_file = Path("docker/docker-compose.yml")
    with open(compose_file, 'r') as f:
        try:
            yaml.safe_load(f)
        except yaml.YAMLError as e:
            pytest.fail(f"docker-compose.yml has invalid YAML syntax: {e}")

def test_required_services_present():
    """Test that all required services are present"""
    compose_file = Path("docker/docker-compose.yml")
    with open(compose_file, 'r') as f:
        compose_data = yaml.safe_load(f)
    
    required_services = ['postgres', 'redis']  # Define for your app
    services = compose_data.get('services', {})
    
    for service in required_services:
        assert service in services, f"Service '{service}' missing"

def test_docker_compose_config():
    """Test docker-compose config validation"""
    try:
        # Try both docker compose syntax variants
        commands = [
            ["docker", "compose", "-f", "docker/docker-compose.yml", "config"],
            ["docker-compose", "-f", "docker/docker-compose.yml", "config"]
        ]
        
        for cmd in commands:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, 
                                      cwd=".", timeout=30)
                if result.returncode == 0:
                    break
            except FileNotFoundError:
                continue
        else:
            pytest.skip("Docker/Docker Compose not installed")
            
        assert result.returncode == 0, f"Validation failed: {result.stderr}"
    except subprocess.TimeoutExpired:
        pytest.fail("Validation timed out")
```