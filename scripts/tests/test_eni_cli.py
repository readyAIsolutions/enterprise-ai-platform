"""Tests for the ENI Enterprise operational CLI (eni-cli).

These verify the CLI wiring (discovery reflects modules, agent-os verbs route,
brief/draft produce output) without requiring network.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent  # enterprise/
CLI = REPO / "scripts" / "eni_cli.py"


def _run(*args: str, timeout: int = 45) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True, text=True, timeout=timeout, cwd=str(REPO),
    )


def test_cli_status_reports_modules() -> None:
    r = _run("status", timeout=40)
    assert r.returncode in (0, 1, 2)  # exit codes: 0 ok / 1 degraded / 2 down
    assert "ENI Enterprise Platform" in r.stdout
    assert "agent_os present" in r.stdout


def test_cli_doctor() -> None:
    r = _run("doctor", timeout=60)
    assert "kernel importable : True" in r.stdout
    # agent_os may be healthy/unhealthy depending on env; it must be reported.
    assert "health agent_os" in r.stdout


def test_cli_agent_os_status_json() -> None:
    r = _run("agent-os", "status", timeout=30)
    assert '"tool": "agent_os"' in r.stdout
    assert '"ok": true' in r.stdout
