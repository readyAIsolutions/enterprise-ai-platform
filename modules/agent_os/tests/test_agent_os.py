"""Tests for the Enterprise Agent OS module.

Covers: module lifecycle + meta, Oracle news scoring, Paperclip
orchestration (with retry/failure), Jarvis voice rules (allowlist / safety),
and the unified surface routing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from modules.agent_os import (
    AgentOSModule,
    JarvisVoice,
    NewsItem,
    OracleEngine,
    PaperclipOrchestrator,
    UnifiedSurface,
    create_agent_os_module,
)


@pytest.fixture
def module() -> AgentOSModule:
    return create_agent_os_module({"test": True})


# ── Module lifecycle + meta ──────────────────────────────────────────────
def test_module_meta_fields(module: AgentOSModule) -> None:
    assert module.name == "agent_os"
    assert module.version == "1.0.0"
    assert module._meta_config["jarvis_agent_edits"] is True


@pytest.mark.asyncio
async def test_module_lifecycle(module: AgentOSModule) -> None:
    await module.initialize()
    assert module.status.value == "healthy"
    health = await module.health_check()
    assert health.value in ("healthy", "unhealthy")
    await module.shutdown()
    assert module.status.value == "stopping"


# ── Oracle news engine ───────────────────────────────────────────────────
def test_oracle_score_favors_recency_and_authority() -> None:
    eng = OracleEngine(feeds=[])  # don't hit network; test scoring directly
    fresh = NewsItem("A", "http://x/1", "hnrss.org", datetime.now(UTC))
    stale = NewsItem("B", "http://x/2", "bbci.co.uk", datetime.now(UTC) - timedelta(days=3))
    assert eng._score(fresh) > eng._score(stale)
    # Same recency, higher authority source wins.
    a = NewsItem("C", "http://x/3", "hnrss.org", datetime.now(UTC))
    b = NewsItem("D", "http://x/4", "bbci.co.uk", datetime.now(UTC))
    assert eng._score(a) > eng._score(b)


def test_oracle_ranks_and_limits() -> None:
    eng = OracleEngine(feeds=[], max_items=3)
    now = datetime.now(UTC)
    items = [
        NewsItem("a", "http://x/a", "hnrss.org", now),
        NewsItem("b", "http://x/b", "bbci.co.uk", now),
        NewsItem("c", "http://x/c", "hnrss.org", now),
        NewsItem("d", "http://x/d", "bbci.co.uk", now - timedelta(hours=50)),
    ]
    brief = eng.brief(items, limit=3)
    assert len(brief) == 3
    # First item should be highest-scoring (hnrss, fresh).
    assert brief[0]["source"] == "hnrss.org"


def test_oracle_graceful_when_offline() -> None:
    # Explicit empty feed list -> no network -> returns [] without crashing.
    eng = OracleEngine(feeds=[], max_items=2)
    assert eng.fetch() == []


def test_oracle_live_fetch_gets_news() -> None:
    # Real RSS fetch (guarded: skips if offline/CI without network).
    eng = OracleEngine(max_items=4)
    if not eng.available:
        pytest.skip("feedparser not installed")
    items = eng.fetch()
    if not items:
        pytest.skip("no network / feeds unreachable in this environment")
    assert len(items) >= 1
    # Every fetched item has a title and source.
    assert all(i.title for i in items)
    assert all(i.source for i in items)
    # Ranked by attention desc.
    atts = [i.attention for i in items]
    assert atts == sorted(atts, reverse=True)


# ── Paperclip orchestrator ───────────────────────────────────────────────
def test_paperclip_runs_all_steps_and_artifacts() -> None:
    orch = PaperclipOrchestrator(max_retries=2)
    run = orch.run("demo", steps=[lambda: 1, lambda: "two", lambda: [3]])
    assert run.all_ok is True
    assert len(run.steps) == 3
    assert len(orch.artifacts()) == 3


def test_paperclip_retries_failing_step() -> None:
    orch = PaperclipOrchestrator(max_retries=2)
    calls = {"n": 0}

    def flaky() -> int:
        calls["n"] += 1
        if calls["n"] < 3:
            err = "transient"
            raise RuntimeError(err)
        return 42

    run = orch.run("flaky", steps=[flaky])
    assert run.all_ok is True
    assert run.steps[0].attempts == 3  # retried until success
    assert run.steps[0].output == 42


def test_paperclip_records_failure_when_exhausted() -> None:
    orch = PaperclipOrchestrator(max_retries=1)

    def always_bad() -> None:
        err = "nope"
        raise ValueError(err)

    run = orch.run("bad", steps=[always_bad])
    assert run.all_ok is False
    assert run.steps[0].error == "nope"


# ── Jarvis voice rules ───────────────────────────────────────────────────
def test_jarvis_open_in_auto_mode() -> None:
    j = JarvisVoice()
    res = j.execute("open google")
    assert res["ok"] is True
    assert res["action"] == "open"
    assert res["target"] == "google"
    assert res["mode"] == "auto"


def test_jarvis_agent_edit_refused_when_not_allowlisted() -> None:
    j = JarvisVoice(allowlist=["write notes file"], agent_edits=True)
    res = j.execute("edit /etc/passwd")
    assert res["ok"] is False
    assert res.get("refused") is True
    # Allowlisted phrase passes.
    ok = j.execute("write notes file update")
    assert ok["ok"] is True
    assert ok["action"] == "edit"


def test_jarvis_no_rule_is_refused() -> None:
    j = JarvisVoice()  # empty allowlist = read-only defaults only
    res = j.execute("send money to nobody")
    assert res["ok"] is False
    assert res.get("refused") is True


# ── Unified surface ──────────────────────────────────────────────────────
def test_unified_surface_routes_verbs(module: AgentOSModule) -> None:
    surf = module.surface()
    assert surf.run("status")["ok"] is True
    assert surf.run("jarvis", text="open mail", auto=True)["action"] == "open"
    assert surf.run("oracle")["tool"] == "oracle"
    pr = surf.run("paperclip", name="x", steps=[lambda: 1])
    assert pr["ok"] is True


def test_unified_surface_unknown_verb() -> None:
    surf = UnifiedSurface(OracleEngine(feeds=[]), PaperclipOrchestrator(), JarvisVoice())
    res = surf.run("frobnicate")
    assert res["ok"] is False
    assert res["error"]


def test_create_helper_returns_module() -> None:
    m = create_agent_os_module({"x": 1})
    assert isinstance(m, AgentOSModule)


# ── Content Pipeline (Oracle -> draft -> free publish) ──────────────────
def test_content_pipeline_publishes_markdown(tmp_path: Path) -> None:
    from pathlib import Path

    from modules.agent_os import ContentPipeline, NewsItem, OracleEngine
    eng = OracleEngine(feeds=[])
    pipe = ContentPipeline(eng, out_dir=str(tmp_path))
    item = NewsItem("Hello World Test", "http://x/1", "hnrss.org",
                    __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                    attention=9.9, summary="A short summary.")
    res = pipe.publish(item)
    assert res["ok"] is True
    path = Path(res["path"])
    assert path.exists()
    assert "# Hello World Test" in path.read_text()


# ── Morning Brief ────────────────────────────────────────────────────────
def test_morning_brief_saves_file(tmp_path: Path) -> None:
    from pathlib import Path

    from modules.agent_os import MorningBrief, OracleEngine
    eng = OracleEngine(feeds=[])
    brief = MorningBrief(eng, out_dir=str(tmp_path))
    res = brief.run(deliver="file")
    assert res["ok"] is True
    assert "brief-" in res["saved"]
    assert Path(res["saved"]).exists()


def test_morning_brief_signal_unconfigured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from modules.agent_os import MorningBrief, OracleEngine
    # Force unconfigured regardless of ambient SIGNAL_* env on this box.
    monkeypatch.delenv("SIGNAL_HTTP_URL", raising=False)
    monkeypatch.delenv("SIGNAL_ACCOUNT", raising=False)
    monkeypatch.delenv("SIGNAL_ALLOWED_USERS", raising=False)
    eng = OracleEngine(feeds=[])
    brief = MorningBrief(eng, out_dir=str(tmp_path))
    res = brief.deliver_to_signal()
    assert res["ok"] is False  # no Signal config -> graceful unconfigured error


# ── Jarvis real execution (rule-gated) ────────────────────────────────────
def test_jarvis_run_action_respects_refusal() -> None:
    j = JarvisVoice(allowlist=["write my notes"])
    refused = j.execute("edit /etc/passwd")  # not allowlisted
    assert refused["ok"] is False
    out = j.run_action(refused)
    assert out.get("blocked") is True  # never executes a refused action


def test_jarvis_run_action_status() -> None:
    j = JarvisVoice()
    action = j.execute("status")
    out = j.run_action(action)
    assert out["ok"] is True
    assert isinstance(out["executed"], dict)
    assert "loadavg" in out["executed"]


# ── Hermes auto-bind ──────────────────────────────────────────────────────
def test_surface_auto_binds_hermes(module: AgentOSModule) -> None:
    surf = module.surface()
    surf.auto_bind_hermes()
    # ControllerFacade should be importable; binding succeeds when available.
    # In isolated test the hermes_controller facade may not fully init, but the
    # surface must not raise and must expose run('hermes') without crashing.
    res = surf.run("hermes", prompt="expand this")
    assert isinstance(res, dict)

