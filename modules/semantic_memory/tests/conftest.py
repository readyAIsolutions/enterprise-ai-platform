"""Shared pytest fixtures and configuration for semantic_memory tests.

The ``enterprise`` package is the repository root directory itself. The
Platform Kernel package (``enterprise.platform_kernel``) is only importable
when the *parent* of the repo root is on ``sys.path``. This conftest inserts
both the repo root (for ``modules.*``) and the parent directory (for
``enterprise.*``) so the module's kernel-interface imports resolve.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Repo root: parents = tests/ -> semantic_memory/ -> modules/ -> repo root
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
# Parent of repo root exposes the 'enterprise' package itself.
_WORKSPACE_ROOT = _PROJECT_ROOT.parent

for _path in (_PROJECT_ROOT, _WORKSPACE_ROOT):
    _s = str(_path)
    if _s not in sys.path:
        sys.path.insert(0, _s)
