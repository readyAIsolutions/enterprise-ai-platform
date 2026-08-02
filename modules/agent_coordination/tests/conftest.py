"""Shared pytest fixtures and configuration for agent_coordination tests."""
import pytest
import sys
from pathlib import Path

# Add the project root to sys.path for imports
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))