"""
Shared pytest fixtures for enterprise integration tests.

Provides:
- Platform kernel boot/shutdown lifecycle
- Module registration fixtures
- Event bus for integration event flow testing
- Health check fixtures
- Temp workspaces
"""

import pytest
import sys
import os
import tempfile
import time
import threading
from pathlib import Path


# Ensure the enterprise package is importable
_ENTERPRISE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ENTERPRISE_ROOT not in sys.path:
    sys.path.insert(0, _ENTERPRISE_ROOT)


# ═══════════════════════════════════════════════════════════════════════════════
# Platform Kernel Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def enterprise_root():
    """Return the absolute path to the enterprise root directory."""
    return Path(_ENTERPRISE_ROOT)


@pytest.fixture(scope="session")
def platform_kernel_class():
    """Return the PlatformKernel class for session-wide use."""
    from kernel.kernel import PlatformKernel
    return PlatformKernel


@pytest.fixture
def platform():
    """Create, initialize, and start a fresh PlatformKernel for each test.

    The kernel is fully shut down after the test completes.
    """
    from kernel.kernel import PlatformKernel
    kernel = PlatformKernel()
    kernel.initialize()
    kernel.start()
    yield kernel
    kernel.shutdown()


@pytest.fixture
def platform_booted(platform):
    """A ready-to-use booted platform (alias for platform)."""
    return platform


# ═══════════════════════════════════════════════════════════════════════════════
# Module Registry Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def module_registry(platform):
    """Return the module registry from a booted platform."""
    return platform.registry


# ═══════════════════════════════════════════════════════════════════════════════
# Event Bus Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def event_bus(platform):
    """Return the event bus from a booted platform."""
    return platform.event_bus


@pytest.fixture
def event_collector():
    """Return a simple event collector that records received events.

    Usage:
        events = event_collector()
        event_bus.subscribe("my.event", events.append)
        # ... trigger events ...
        assert len(events) > 0
    """
    events: list = []
    return events


# ═══════════════════════════════════════════════════════════════════════════════
# Temp Workspace Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def temp_workspace():
    """Create a temporary directory that is cleaned up after the test."""
    with tempfile.TemporaryDirectory(prefix="eni_enterprise_test_") as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_config_file(temp_workspace):
    """Create a temporary config file path for testing."""
    config_path = temp_workspace / "test_config.json"
    yield config_path
    if config_path.exists():
        config_path.unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Module-specific Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def safety_guardrail():
    """Return a configured SafetyGuardrail instance."""
    from modules.safety_governance.guardrails import SafetyGuardrail
    return SafetyGuardrail()


@pytest.fixture
def prompt_registry():
    """Return a fresh PromptRegistry instance."""
    from modules.prompt_context import PromptRegistry
    return PromptRegistry()


@pytest.fixture
def context_manager():
    """Return a fresh ContextManager instance."""
    from modules.prompt_context import ContextManager
    return ContextManager()


@pytest.fixture
def agent_registry():
    """Return a fresh AgentRegistry instance."""
    from modules.agent_coordination.agents import AgentRegistry
    return AgentRegistry()


@pytest.fixture
def entity_registry():
    """Return a fresh EntityRegistry instance."""
    from modules.knowledge_graph.entities import EntityRegistry
    return EntityRegistry()


# ═══════════════════════════════════════════════════════════════════════════════
# Time / Performance Helpers
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def fake_time(monkeypatch):
    """Control time.time() for deterministic tests. Returns a mutable list [current_time]."""
    current = [time.time()]
    original = time.time

    def mock_time():
        return current[0]

    monkeypatch.setattr(time, "time", mock_time)
    return current


@pytest.fixture
def timer():
    """Simple context-manager timer for performance assertions."""
    class Timer:
        def __init__(self):
            self.start = 0.0
            self.elapsed = 0.0

        def __enter__(self):
            self.start = time.time()
            return self

        def __exit__(self, *args):
            self.elapsed = time.time() - self.start

        @property
        def ms(self):
            return self.elapsed * 1000

    return Timer()


# ═══════════════════════════════════════════════════════════════════════════════
# Integration-specific Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def wait_for_condition(condition, timeout=5.0, interval=0.1):
    """Wait for a condition to become truthy.

    Args:
        condition: Callable returning truthy when condition is met.
        timeout: Maximum seconds to wait.
        interval: Sleep interval between checks.

    Returns:
        The truthy value returned by the condition, or raises TimeoutError.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = condition()
        if result:
            return result
        time.sleep(interval)
    raise TimeoutError(f"Condition not met within {timeout}s")


@pytest.fixture
def wait_for():
    """Fixture wrapper around wait_for_condition."""
    return wait_for_condition


@pytest.fixture
def parallel_executor():
    """Simple parallel executor using ThreadPoolExecutor."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    return ThreadPoolExecutor, as_completed