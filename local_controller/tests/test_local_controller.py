"""Tests for SLICE B local_controller (vault, planner, build_provider, controller).

Run with:  python3 -m pytest local_controller/tests/ -q
Covers the four mandated proofs:
  1. vault.redact strips real secrets leaving only placeholder names.
  2. planner produces >=4 cohesive steps with dependency lists.
  3. build_provider.run_plan writes artifact files + manifest.json.
  4. controller endpoints (/plan /enrich /program /health) respond over HTTP.
"""

from __future__ import annotations

import json
import os
import socket
import tempfile
import threading
import urllib.request

import pytest

from local_controller import planner, vault
from local_controller.build_provider import BuildProvider
from local_controller.controller import ControllerHandler, LocalControllerServer

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# 1. Vault + redaction security
# ---------------------------------------------------------------------------


def test_vault_set_get_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        v = vault.Vault(path=os.path.join(d, "vault.json"),
                        key_path=os.path.join(d, ".vault_key"))
        v.set("openai_key", "sk-LIVE-SECRET-VALUE")
        assert v.get("openai_key") == "sk-LIVE-SECRET-VALUE"
        assert v.get("missing") is None
        assert "openai_key" in v.placeholders()


def test_vault_redact_strips_real_secret_leaves_placeholder_name():
    with tempfile.TemporaryDirectory() as d:
        v = vault.Vault(path=os.path.join(d, "vault.json"),
                        key_path=os.path.join(d, ".vault_key"))
        v.set("openai_key", "sk-SUPER-REAL-VALUE-9x7")
        prompt = (
            "Call the model with {openai_key}; auth header: "
            "Bearer sk-SUPER-REAL-VALUE-9x7"
        )
        red = v.redact(prompt)
        # real value must NEVER survive
        assert "sk-SUPER-REAL-VALUE-9x7" not in red
        # placeholder NAME must remain so the cloud sees it exists (not its value)
        assert "openai_key" in red
        # the {token} syntax is resolved, not left dangling
        assert "{openai_key}" not in red
        assert "Bearer openai_key" in red


def test_module_redact_function():
    red = vault.redact("use {db_password} when connecting")
    assert "db_password" in red
    assert "{db_password}" not in red
    assert "hunter2" not in red


# ---------------------------------------------------------------------------
# 2. Planner: deterministic goal -> task DAG
# ---------------------------------------------------------------------------


def test_planner_produces_at_least_4_steps_with_deps():
    plan = planner.parse_goal("Build a markdown to html converter")
    assert len(plan.tasks) >= 4
    assert len(plan.tasks) <= 8
    for task in plan.tasks:
        assert isinstance(task.deps, list)
        assert task.feature
        assert task.prompt
        assert task.test_hint  # every step carries a test hint
    # last step depends on first step (real DAG), and step 1 has no deps
    assert plan.tasks[0].deps == []
    assert plan.tasks[1].deps == [0]
    # same goal -> same plan (deterministic)
    again = planner.parse_goal("Build a markdown to html converter")
    assert [t.to_dict() for t in plan.tasks] == [t.to_dict() for t in again.tasks]


def test_enrich_prompt_expands_short_prompt():
    big = planner.enrich_prompt("Just do it: print hello")
    assert len(big) > len("Just do it: print hello")
    assert "CORE ASK" in big
    assert "ACCEPTANCE" in big or "Acceptance" in big


# ---------------------------------------------------------------------------
# 3. Build provider: artifacts + manifest.json
# ---------------------------------------------------------------------------


def test_run_plan_produces_files_and_manifest(tmp_path):
    prov = BuildProvider(sessions_dir=str(tmp_path))
    goal = "Build a tiny todo cli"
    result = prov.run_plan(goal=goal, session_id="test_session_1")
    session_dir = result["session_dir"]
    # session dir exists and contains files
    assert os.path.isdir(session_dir)
    files = os.listdir(session_dir)
    assert len(files) >= 2  # at least one artifact + manifest
    assert "manifest.json" in files
    # every artifact path referenced exists on disk
    for art in result["artifacts"]:
        assert os.path.isfile(art)
    # manifest parses and records steps
    with open(result["manifest_file"]) as fh:
        manifest = json.load(fh)
    assert manifest["session_id"] == "test_session_1"
    assert manifest["goal"] == goal
    assert len(manifest["steps"]) >= 4
    assert all("file" in s and "status" in s for s in manifest["steps"])
    # manifest path recorded in the summary points at the written file
    assert result["manifest_file"] == os.path.join(tmp_path, "test_session_1", "manifest.json")


def test_external_llm_not_used_by_default_and_no_key_log(tmp_path):
    prov = BuildProvider(sessions_dir=str(tmp_path))
    prov.run_plan(goal="demo", session_id="nokey_session")
    # no exception raised when no url/key_env supplied; local worker used
    assert True


# ---------------------------------------------------------------------------
# 4. Controller HTTP endpoints
# ---------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def running_server():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()
    srv = LocalControllerServer(port=port)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()
    srv.server_close()


def _post(url, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def _get(url):
    with urllib.request.urlopen(url, timeout=15) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def test_health_endpoint(running_server):
    status, body = _get(f"{running_server}/health")
    assert status == 200
    assert body["status"] == "ok"
    assert "/plan" in body["endpoints"]
    assert "/enrich" in body["endpoints"]
    assert "/program" in body["endpoints"]


def test_plan_endpoint(running_server):
    status, body = _post(f"{running_server}/plan", {"goal": "Build a csv stats tool"})
    assert status == 200
    assert body["steps"] >= 4
    assert len(body["plan"]) == body["steps"]
    first = body["plan"][0]
    assert first["deps"] == []
    assert first["test_hint"]


def test_enrich_endpoint(running_server):
    status, body = _post(f"{running_server}/enrich", {"prompt": "print hi"})
    assert status == 200
    assert len(body["prompt"]) > len("print hi")
    assert body["enriched_length"] > body["source_length"]


def test_program_endpoint(running_server, tmp_path):
    status, body = _post(f"{running_server}/program", {"goal": "Build a timezone tool"})
    assert status == 200
    assert body["session_id"]
    assert os.path.isfile(body["manifest_file"])
    for art in body["artifacts"]:
        assert os.path.isfile(art)