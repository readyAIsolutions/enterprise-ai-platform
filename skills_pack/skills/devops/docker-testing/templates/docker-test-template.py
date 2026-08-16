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
    
    # Define required services for your application
    required_services = []
    services = compose_data.get('services', {})
    
    for service in required_services:
        assert service in services, f"Service '{service}' should be present in docker-compose.yml"

def test_networks_defined():
    """Test that networks are properly defined"""
    compose_file = Path("docker/docker-compose.yml")
    with open(compose_file, 'r') as f:
        compose_data = yaml.safe_load(f)
    
    networks = compose_data.get('networks', {})
    # Define required networks for your application
    required_networks = []
    
    for network in required_networks:
        assert network in networks, f"Network '{network}' should be defined"
    # Additional network validation can be added here

def test_volumes_defined():
    """Test that volumes are properly defined"""
    compose_file = Path("docker/docker-compose.yml")
    with open(compose_file, 'r') as f:
        compose_data = yaml.safe_load(f)
    
    volumes = compose_data.get('volumes', {})
    # Define required volumes for your application
    required_volumes = []
    
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
    
    # Define required environment variables for your application
    required_env_vars = []
    
    for env_var in required_env_vars:
        # Check for ${ENV_VAR} or ${ENV_VAR:-default} patterns
        assert f"${{{env_var}}}" in content or f"${{{env_var}:" in content, \
            f"Environment variable '{env_var}' should be referenced in docker-compose.yml"