# Demiurge Marketing OS Docker Testing Example

This reference shows the complete unit test implementation for validating the Docker Compose configuration used in the Demiurge Marketing OS v2.0 project.

## Complete test_docker.py

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
    """Test that all required services are present in docker-compose.yml"""
    compose_file = Path("docker/docker-compose.yml")
    with open(compose_file, 'r') as f:
        compose_data = yaml.safe_load(f)
    
    required_services = ['postgres', 'redis', 'fonoster', 'usesend', 'odoo19', 'app']
    services = compose_data.get('services', {})
    
    for service in required_services:
        assert service in services, f"Service '{service}' should be present in docker-compose.yml"

def test_networks_defined():
    """Test that networks are properly defined"""
    compose_file = Path("docker/docker-compose.yml")
    with open(compose_file, 'r') as f:
        compose_data = yaml.safe_load(f)
    
    networks = compose_data.get('networks', {})
    assert 'demiurge-net' in networks, "demiurge-net network should be defined"
    assert networks['demiurge-net'].get('driver') == 'bridge', "demiurge-net should use bridge driver"

def test_volumes_defined():
    """Test that volumes are properly defined"""
    compose_file = Path("docker/docker-compose.yml")
    with open(compose_file, 'r') as f:
        compose_data = yaml.safe_load(f)
    
    volumes = compose_data.get('volumes', {})
    required_volumes = ['postgres_data', 'redis_data', 'fonoster_data', 'usesend_data', 'odoo_data']
    
    for volume in required_volumes:
        assert volume in volumes, f"Volume '{volume}' should be defined"

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
        assert result.returncode == 0, f"docker-compose config validation failed: {result.stderr}"
    except subprocess.TimeoutExpired:
        pytest.fail("docker-compose config validation timed out")
    except FileNotFoundError:
        # Docker not installed, skip this test
        pytest.skip("Docker not installed")

def test_environment_variables():
    """Test that required environment variables are referenced"""
    compose_file = Path("docker/docker-compose.yml")
    with open(compose_file, 'r') as f:
        content = f.read()
    
    # Check for references to required environment variables
    required_env_vars = [
        'POSTGRES_PASSWORD',
        'FONOSTER_API_KEY',
        'FONOSTER_API_SECRET',
        'FONOSTER_ACCESS_KEY_ID',
        'USESEND_API_KEY'
    ]
    
    for env_var in required_env_vars:
        # Check for ${ENV_VAR} or ${ENV_VAR:-default} patterns
        assert f"${{{env_var}}}" in content or f"${{{env_var}:" in content, \
            f"Environment variable '{env_var}' should be referenced in docker-compose.yml"
```

## Test Execution Results

When running these tests on the Demiurge Marketing OS project, the results were:

```
tests/test_docker.py::test_docker_compose_file_exists PASSED
tests/test_docker.py::test_docker_compose_syntax PASSED
tests/test_docker.py::test_required_services_present PASSED
tests/test_docker.py::test_networks_defined PASSED
tests/test_docker.py::test_volumes_defined PASSED
tests/test_docker.py::test_docker_compose_config SKIPPED (Docker not installed)
tests/test_docker.py::test_environment_variables PASSED
```

Overall Result: 6 passed, 1 skipped

## Key Features of This Test Suite

1. **Comprehensive Validation**: Tests cover file existence, syntax, services, networks, volumes, and environment variables
2. **Graceful Handling**: Skips tests when Docker is not installed rather than failing
3. **Version Compatibility**: Supports both `docker compose` and `docker-compose` commands
4. **Clear Error Messages**: Provides specific feedback when tests fail
5. **Timeout Protection**: Prevents tests from hanging indefinitely
6. **Real-world Testing**: Validates actual environment variable references in the configuration

## Running the Tests

```bash
# Run all Docker tests
python -m pytest tests/test_docker.py -v

# Run with coverage
python -m pytest tests/test_docker.py --cov=docker --cov-report=html

# Run specific test
python -m pytest tests/test_docker.py::test_required_services_present -v
```