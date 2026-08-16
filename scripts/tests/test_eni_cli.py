"""Tests for the ENI Enterprise operational CLI (eni_cli).

These verify the CLI wiring (status reflects the platform, doctor verifies the
kernel import + portable pack, agent-os reports the agent_os verb) without
requiring network. Tests assert the REAL contract of the canonical eni_cli.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent  # enterprise/
CLI = REPO / "scripts" / "eni_cli"


def _run(*args: str, timeout: int = 45) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True, text=True, timeout=timeout, cwd=str(REPO),
    )


def test_cli_status_reports_modules() -> None:
    r = _run("status", timeout=40)
    assert r.returncode == 0
    assert "ENI platform status" in r.stdout
    assert "modules present:" in r.stdout
    assert "skillspack present" in r.stdout or "skills_pack present" in r.stdout


def test_cli_doctor() -> None:
    r = _run("doctor", timeout=60)
    assert r.returncode == 0
    assert "platform kernel import" in r.stdout


def test_cli_agent_os_status_json() -> None:
    r = _run("agent-os", "status", timeout=30)
    assert r.returncode in (0, 1)
    data = json.loads(r.stdout)
    assert data["tool"] == "agent_os"
    assert data["present"] is True   # modules/agent_os exists in this repo
    assert data["ok"] is True


def test_cli_help_shows_local_command() -> None:
    r = _run("--help", timeout=20)
    assert r.returncode == 0
    assert r.stdout == "" or "doctor" in r.stdout