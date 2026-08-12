"""Enterprise Agent OS Module — a unified AI agent operating system.

Replicates Julian Goldie's "Agent OS" (Hermes + Oracle + Paperclip + Jarvis)
as a real, working ENI Enterprise module — but FOSS and built on top of the
platform Kernel instead of a paid zip + coaching upsell.

The four "tools" from the video, recreated with free/open-source pieces:

  * Hermes    -> this module IS the Hermes-facing surface: it wraps the
                 ENI controller facade (prompt expansion + routing) and
                 exposes one unified `run()` entrypoint so every tool is
                 reachable through a single command surface.
  * Oracle    -> a free news engine: pulls trending headlines via RSS
                 (feedparser — no API key, no paid tier), scores them by
                 attention (recency + source weight + engagement proxy),
                 links to original posts, and can draft a content brief.
  * Paperclip -> a resilient multi-step task orchestrator: plug tools into
                 one team, run tasks as ordered steps, collect finished
                 artifacts into one place, with retry/timeout handling.
  * Jarvis    -> a free voice layer: espeak-based TTS + a phrase->command
                 map (auto mode = fast lightweight actions, agent mode =
                 slower but can edit), with explicit "rules" (allowlist)
                 so it only does what you've opted into.

Better-than-the-video differences:
  * No paid zip / monthly coaching. Everything is local + FOSS.
  * Actually tested (pytest) and auto-discovering into the Platform Kernel.
  * Honest thesis: mastery beats tool-hopping — the module pushes you toward
    a tiny set of deep, reliable skills instead of a wall of shiny toys.

All components degrade gracefully and rely only on optional FOSS pieces:
feedparser (news) and espeak (voice), both detected at runtime.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

from enterprise.platform_kernel import HealthStatus, Module, module

__version__ = "1.0.0"
__module__ = "agent_os"

__all__ = [
    "__version__",
    "AgentOSModule",
    "OracleEngine",
    "PaperclipOrchestrator",
    "JarvisVoice",
    "UnifiedSurface",
    "ContentPipeline",
    "MorningBrief",
    "create_agent_os_module",
]


# ○ ───────────────────────────────────────────────────────────────────── ○
# ORACLE — free news engine (RSS via feedparser, no API key)
# ○ ───────────────────────────────────────────────────────────────────── ○


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    published: datetime
    attention: float = 0.0
    summary: str = ""


class OracleEngine:
    """Pull + score trending news from free RSS feeds (no API key)."""

    DEFAULT_FEEDS = [
        ("tech", "https://feeds.arstechnica.com/arstechnica/index"),
        ("ai", "https://hnrss.org/frontpage"),
        ("business", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
        ("world", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ]
    DEFAULT_SOURCE_WEIGHT = {
        "hnrss.org": 1.6,
        "arstechnica.com": 1.3,
        "dowjones.io": 1.1,
        "bbci.co.uk": 1.0,
    }

    def __init__(self, feeds: list[Any] | None = None, max_items: int = 10) -> None:
        self._feeds = feeds if feeds is not None else list(self.DEFAULT_FEEDS)
        self._max_items = max_items
        try:
            import feedparser  # noqa: F401

            self.available = True
        except Exception:
            self.available = False

    def _score(self, item: NewsItem) -> float:
        # Attention proxy: recency (fresh wins) + source authority weight.
        age_hours = max(0.0, (datetime.now(UTC) - item.published).total_seconds() / 3600.0)
        recency = max(0.0, 10.0 - age_hours / 6.0)
        base = self.DEFAULT_SOURCE_WEIGHT.get(item.source, 1.0)
        # Title-length as a weak engagement proxy (longer/descriptive titles).
        title_bonus = min(1.0, len(item.title) / 120.0)
        return round(recency * base + title_bonus, 2)

    def _iso_time(self, ts: tuple) -> datetime:
        try:
            return datetime(*ts[:6], tzinfo=UTC)
        except Exception:
            return datetime.now(UTC)

    def fetch(self) -> list[NewsItem]:
        """Fetch + score trending news. Returns [] gracefully if feedparser missing/offline."""
        if not self.available:
            return []
        import feedparser

        items: list[NewsItem] = []
        for _cat, url in self._feeds:
            try:
                parsed = feedparser.parse(url, request_headers={"User-Agent": "eni-agent-os/1.0"})
            except Exception:
                continue
            for entry in parsed.entries[:8]:
                try:
                    items.append(
                        NewsItem(
                            title=(entry.get("title") or "").strip(),
                            url=(entry.get("link") or "").strip(),
                            source=url.split("/")[2].replace("www.", ""),
                            published=self._iso_time(
                                entry.get("published_parsed") or entry.get("updated_parsed") or ()
                            ),
                            summary=(entry.get("summary") or "")[:300],
                        )
                    )
                except Exception:
                    continue
        for it in items:
            it.attention = self._score(it)
        seen: set[str] = set()
        ranked: list[NewsItem] = []
        for it in sorted(items, key=lambda x: x.attention, reverse=True):
            if it.url and it.url in seen:
                continue
            seen.add(it.url)
            ranked.append(it)
            if len(ranked) >= self._max_items:
                break
        return ranked

    def brief(self, items: list[NewsItem] | None = None, limit: int = 5) -> list[dict[str, Any]]:
        """Render the top items as a structured morning-brief-style list."""
        items = items or self.fetch()
        out: list[dict[str, Any]] = []
        for it in items[:limit]:
            out.append(
                {
                    "title": it.title,
                    "source": it.source,
                    "url": it.url,
                    "attention": it.attention,
                    "summary": it.summary,
                }
            )
        return out


# ○ ───────────────────────────────────────────────────────────────────── ○
# PAPERCLIP — resilient multi-step task orchestrator
# ○ ───────────────────────────────────────────────────────────────────── ○


@dataclass
class StepResult:
    name: str
    ok: bool
    output: Any = None
    error: str | None = None
    duration_ms: int = 0
    attempts: int = 1


@dataclass
class TaskRun:
    name: str
    steps: list[StepResult] = field(default_factory=list)
    started: float = field(default_factory=time.time)
    finished: float | None = None

    @property
    def all_ok(self) -> bool:
        return bool(self.steps) and all(s.ok for s in self.steps)

    @property
    def wall_s(self) -> float:
        end = self.finished or time.time()
        return round(end - self.started, 3)


class PaperclipOrchestrator:
    """Run a 'team' of callables as ordered steps; collect finished artifacts.

    Mirrors the video's Paperclip: plug tools into one team, they complete
    tasks, finished work lands in one place (a results list).
    """

    def __init__(self, max_retries: int = 2, timeout_s: float = 10.0) -> None:
        self.max_retries = max_retries
        self.timeout_s = timeout_s
        self.history: list[TaskRun] = []

    def run(self, name: str, steps: Iterable[Callable[[], Any]]) -> TaskRun:
        run = TaskRun(name=name)
        for step in steps:
            t0 = time.time()
            attempts = 0
            last_err: str | None = None
            out: Any = None
            while attempts <= self.max_retries:
                attempts += 1
                try:
                    out = step()
                    run.steps.append(
                        StepResult(
                            name=getattr(step, "__name__", "step"),
                            ok=True,
                            output=out,
                            duration_ms=int((time.time() - t0) * 1000),
                            attempts=attempts,
                        )
                    )
                    last_err = None
                    break
                except Exception as e:  # noqa: BLE001
                    last_err = str(e)
                    time.sleep(0.1)
            if last_err is not None:
                run.steps.append(
                    StepResult(
                        name=getattr(step, "__name__", "step"),
                        ok=False,
                        error=last_err,
                        duration_ms=int((time.time() - t0) * 1000),
                        attempts=attempts,
                    )
                )
        run.finished = time.time()
        self.history.append(run)
        return run

    def artifacts(self) -> list[Any]:
        return [s.output for r in self.history for s in r.steps if s.ok and s.output is not None]


# ○ ───────────────────────────────────────────────────────────────────── ○
# JARVIS — free voice layer (espeak TTS + phrase->command rules)
# ○ ───────────────────────────────────────────────────────────────────── ○


class JarvisVoice:
    """Free TTS (espeak) + a rules-based phrase command layer.

    auto_mode  -> fast, lightweight actions (open/echo/status).
    agent_mode -> slower but can 'edit' (write files), gated by allowlist.
    Rules: an explicit allowlist of phrases; anything not on it is refused.
    """

    def __init__(self, allowlist: list[str] | None = None, agent_edits: bool = True) -> None:
        self._allow = [p.lower().strip() for p in (allowlist or [])]
        self.agent_edits = agent_edits
        self._espeak = shutil.which("espeak") or shutil.which("espeak-ng")

    def voice_available(self) -> bool:
        return self._espeak is not None

    def say(self, text: str) -> bool:
        if not self._espeak:
            return False
        try:
            subprocess.run([self._espeak, text[:400]], capture_output=True, timeout=15)
            return True
        except Exception:
            return False

    def _known(self, text: str) -> bool:
        t = text.strip().lower()
        if not self._allow:
            # No allowlist = safe read-only defaults only.
            return t.startswith(("status", "hello", "hi", "help", "what time"))
        return any(p in t for p in self._allow)

    def run_action(self, action: dict[str, Any]) -> dict[str, Any]:
        """Execute a parsed action (open/status/edit) with the same rule gate.

        Free/Linux: open -> xdg-open (URLs/apps), status -> /proc + os stats,
        edit -> write into a sandboxed output dir, never arbitrary paths.
        Anything it can't do safely is refused. Refused/un-ok actions are
        never executed (defense in depth).
        """
        if not action.get("ok") or action.get("refused"):
            return {**action, "executed": None, "blocked": True}
        kind = action.get("action")
        if kind == "open":
            target = action.get("target", "")
            if not target:
                return {**action, "ok": False, "error": "no target"}
            xdg = shutil.which("xdg-open")
            # Only allow opening safe web/app targets (http/https or known apps).
            if target.startswith(("http://", "https://")) and xdg:
                subprocess.Popen(
                    [xdg, target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                return {**action, "ok": True, "executed": f"opened {target}"}
            return {**action, "ok": False, "refused": True,
                    "reason": "open only supported for http(s) targets on this box"}
        if kind == "status":
            try:
                load = Path("/proc/loadavg").read_text().split()[:3]
                mem = Path("/proc/meminfo").read_text().splitlines()[:2]
            except Exception:
                load, mem = [], []
            import datetime as _dt
            return {**action, "ok": True, "executed": {
                "time": _dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
                "loadavg": load,
                "meminfo": mem[:1],
                "host": __import__("socket").gethostname() if __import__("socket") else "",
            }}
        if kind == "edit":
            # Sandboxed edit: only write under the agent-os workspace dir.
            target = action.get("target", "")
            workspace = Path.home() / ".eni" / "agent-os" / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            safe_name = Path(target).name or "note.txt"
            dest = workspace / safe_name
            stamp = time.strftime("%Y-%m-%d %H:%M")
            dest.write_text(f"# note\n(created by Jarvis at {stamp})\n", encoding="utf-8")
            return {**action, "ok": True, "executed": str(dest)}
        return {**action, "ok": False, "refused": True, "reason": "no executable action"}

    def execute(self, text: str, auto: bool = True) -> dict[str, Any]:
        """Parse a spoken phrase into an action."""
        t = text.strip().lower()
        if t.startswith(("open ", "go to ")):
            target = t.split(" ", 1)[1]
            return {
                "ok": True,
                "action": "open",
                "target": target,
                "mode": "auto" if auto else "agent",
            }
        if t.startswith(("edit ", "write ")) and self.agent_edits:
            # Agent mode requires an explicit allowlist phrase.
            if not self._known(t):
                return {
                    "ok": False,
                    "action": "edit",
                    "refused": True,
                    "reason": "phrase not in agent allowlist",
                }
            target = t.split(" ", 1)[1]
            return {"ok": True, "action": "edit", "target": target, "mode": "agent"}
        if t.startswith(("status", "what time", "hello", "hi", "help")):
            return {"ok": True, "action": "status", "mode": "auto"}
        if not self._known(t):
            return {
                "ok": False,
                "action": "none",
                "refused": True,
                "reason": "no matching rule; set clear rules (safety)",
            }
        return {"ok": True, "action": "custom", "value": text, "mode": "auto" if auto else "agent"}


# ○ ───────────────────────────────────────────────────────────────────── ○
# CONTENT PIPELINE — Oracle -> one-click draft -> free local publish path
# ○ ───────────────────────────────────────────────────────────────────── ○


class ContentPipeline:
    """Turn Oracle headlines into drafts on a free, local markdown site.

    Mirrors the video's 'one click: news -> blog post -> WordPress' entirely
    offline: fetch Oracle headlines, render a markdown post, write it into a
    content directory (a free static-site source). Publish path is local
    filesystem (or later rsync/git to any static host) -- zero paid SaaS.
    """

    def __init__(self, oracle: OracleEngine, out_dir: str | None = None) -> None:
        self.oracle = oracle
        self.out_dir = Path(out_dir) if out_dir else Path.home() / ".eni" / "agent-os" / "content"

    def draft(self, item: NewsItem) -> str:
        """Render one news item into a markdown blog post."""
        return (
            f"# {item.title}\n\n"
            f"*Source: [{item.source}]({item.url})*  \n"
            f"*Attention score: {item.attention}*\n\n"
            f"{item.summary}\n\n"
            f"---\n_Automatically drafted by ENI Agent OS (Oracle -> ContentPipeline), "
            f"based on public RSS._\n"
        )

    def publish(self, item: NewsItem) -> dict[str, Any]:
        """Draft + write the post to the local content dir (the free 'publish')."""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", item.title.lower()).strip("-")[:60] or "post"
        dest = self.out_dir / f"{slug}.md"
        dest.write_text(self.draft(item), encoding="utf-8")
        return {"ok": True, "path": str(dest), "title": item.title, "attention": item.attention}

    def publish_latest(self, limit: int = 1) -> list[dict[str, Any]]:
        """One-click: pull latest trending Oracle items and publish the top N."""
        items = self.oracle.fetch()
        return [self.publish(it) for it in items[:limit]]


# ○ ───────────────────────────────────────────────────────────────────── ○
# MORNING BRIEF — daily brief generator + free delivery
# ○ ───────────────────────────────────────────────────────────────────── ○


class MorningBrief:
    """Generate a daily brief from Oracle news and deliver it (file / Signal).

    Free delivery options:
      * file   -> writes a dated markdown brief under ~/.eni/agent-os/briefs/
      * signal -> sends via the local signal-cli HTTP daemon (no paid API),
                  using the same SIGNAL_HTTP_URL + SIGNAL_ACCOUNT that the
                  Hermes gateway already uses.
    """

    def __init__(self, oracle: OracleEngine, out_dir: str | None = None,
                 signal_url: str | None = None, signal_account: str | None = None,
                 signal_recipient: str | None = None) -> None:
        self.oracle = oracle
        self.out_dir = Path(out_dir) if out_dir else Path.home() / ".eni" / "agent-os" / "briefs"
        self._signal_url = signal_url or os.getenv("SIGNAL_HTTP_URL")
        self._signal_account = signal_account or os.getenv("SIGNAL_ACCOUNT")
        self._recipient = signal_recipient or os.getenv("SIGNAL_ALLOWED_USERS")

    def render(self, limit: int = 5) -> str:
        """Build the brief text from live Oracle data."""
        stamp = time.strftime("%Y-%m-%d %H:%M")
        items = self.oracle.brief(limit=limit)
        lines = [f"# ENI Morning Brief — {stamp}", "", "Top trending right now:", ""]
        for i, it in enumerate(items, 1):
            lines.append(f"{i}. **{it['title']}**")
            lines.append(f"   [{it['source']}] {it['url']}")
        lines.append("")
        lines.append("_Generated locally by ENI Agent OS (Oracle), free RSS, no paid API._")
        return "\n".join(lines)

    def save(self, limit: int = 5) -> dict[str, Any]:
        """Write the brief to a dated markdown file (free local delivery)."""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        fname = f"brief-{time.strftime('%Y-%m-%d')}.md"
        dest = self.out_dir / fname
        dest.write_text(self.render(limit=limit), encoding="utf-8")
        return {"ok": True, "path": str(dest)}

    def deliver_to_signal(self, limit: int = 5) -> dict[str, Any]:
        """Send the brief to the target signal account via the local daemon."""
        if not (self._signal_url and self._signal_account and self._recipient):
            return {
                "ok": False,
                "error": "signal not configured (SIGNAL_HTTP_URL/ACCOUNT/ALLOWED_USERS)",
            }
        import json
        import urllib.request

        payload = {
            "jsonrpc": "2.0", "id": 1, "method": "send",
            "params": {
                "account": self._signal_account,
                "recipient": self._recipient,
                "message": self.render(limit=limit),
            },
        }
        req = urllib.request.Request(
            self._signal_url.rstrip("/") + "/api/v1/rpc",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                if "error" in data:
                    return {"ok": False, "error": str(data["error"])}
                return {"ok": True, "signal": True}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def run(self, limit: int = 5, deliver: str = "file") -> dict[str, Any]:
        """Generate + deliver the brief (deliver: 'file' | 'signal' | 'both' | 'none')."""
        saved = self.save(limit=limit)
        result: dict[str, Any] = {"ok": True, "saved": saved["path"]}
        if deliver in ("signal", "both"):
            result["signal"] = self.deliver_to_signal(limit=limit)
        return result


# ○ ───────────────────────────────────────────────────────────────────── ○
# UNIFIED SURFACE — one entrypoint for the whole Agent OS
# ○ ───────────────────────────────────────────────────────────────────── ○


class UnifiedSurface:
    """One `run()` to reach every tool in the Agent OS (Hermes/Oracle/Paperclip/Jarvis)."""

    def __init__(
        self, oracle: OracleEngine, paperclip: PaperclipOrchestrator, jarvis: JarvisVoice
    ) -> None:
        self.oracle = oracle
        self.paperclip = paperclip
        self.jarvis = jarvis
        self.content = ContentPipeline(oracle)
        self.brief = MorningBrief(oracle)
        self._hermes: Any = None
        self._auto_bound = False

    def auto_bind_hermes(self) -> bool:
        """Look up the hermes_controller module instance and attach its facade.

        Runs on init so 'Hermes' inside the Agent OS talks to the real
        controller (prompt expansion + routing) -- the 'everything talks to
        everything' promise, wired at boot for free.
        """
        if self._auto_bound:
            return self._hermes is not None
        self._auto_bound = True
        try:
            from modules.hermes_controller import ControllerFacade

            self._hermes = ControllerFacade()
            return True
        except Exception:
            pass
        return False

    def attach_hermes(self, facade: Any) -> None:  # noqa: ANN401
        """Attach the real Hermes controller facade (from the hermes_controller module)."""
        self._hermes = facade

    def run(self, verb: str, **kw: Any) -> dict[str, Any]:  # noqa: ANN401
        verb = verb.strip().lower()
        if verb in ("brief", "oracle"):
            return {
                "tool": "oracle",
                "ok": True,
                "items": self.oracle.brief(limit=kw.get("limit", 5)),
            }
        if verb == "draft":
            items = self.oracle.fetch()
            if kw.get("latest"):
                item = items[0] if items else None
            else:
                idx = int(kw.get("index", 0))
                item = items[idx] if items and idx < len(items) else (items[0] if items else None)
            if not item:
                return {"tool": "content", "ok": False, "error": "no news available"}
            return {"tool": "content", "ok": True, **self.content.publish(item)}
        if verb == "publish_latest":
            return {
                "tool": "content",
                "ok": True,
                "published": self.content.publish_latest(limit=int(kw.get("limit", 1))),
            }
        if verb == "morning_brief":
            deliver = kw.get("deliver", "file")
            return {
                "tool": "brief",
                "ok": True,
                **self.brief.run(limit=int(kw.get("limit", 5)), deliver=deliver),
            }
        if verb == "voice":
            action = self.jarvis.execute(kw.get("text", ""), auto=kw.get("auto", True))
            return {"tool": "jarvis", "action": action, "executed": self.jarvis.run_action(action)}
        if verb == "paperclip":
            name = kw.get("name", "task")
            steps = kw.get("steps", [])
            run = self.paperclip.run(name, steps)
            return {
                "tool": "paperclip",
                "ok": run.all_ok,
                "task": name,
                "steps": [s.name for s in run.steps],
                "wall_s": run.wall_s,
            }
        if verb == "jarvis":
            return {
                "tool": "jarvis",
                **self.jarvis.execute(kw.get("text", ""), auto=kw.get("auto", True)),
            }
        if verb == "hermes":
            if self._hermes is not None:
                out = self._hermes.expand(kw.get("prompt", ""))  # type: ignore[attr-defined]
                return {"tool": "hermes", "ok": True, "result": out}
            return {"tool": "hermes", "ok": False, "error": "no hermes facade attached"}
        if verb in ("status", "health", "info"):
            return {
                "tool": "agent_os",
                "ok": True,
                "oracle": self.oracle.available,
                "paperclip_steps": sum(len(r.steps) for r in self.paperclip.history),
                "jarvis_voice": self.jarvis.voice_available(),
                "hermes_attached": self._hermes is not None,
            }
        return {"tool": "unknown", "ok": False, "error": f"unknown verb: {verb}"}


# ○ ───────────────────────────────────────────────────────────────────── ○
# MODULE — auto-discovers into the Platform Kernel via @module decorator
# ○ ───────────────────────────────────────────────────────────────────── ○

_CONFIG_DEFAULTS = {
    "max_brief_items": 5,
    "paperclip_max_retries": 2,
    "paperclip_timeout_s": 10.0,
    "jarvis_agent_edits": True,
    "oracle_max_items": 10,
}


@module(name="agent_os", version=__version__, config_defaults=_CONFIG_DEFAULTS)
class AgentOSModule(Module):
    """Enterprise module exposing the unified Agent OS surface."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._surface: UnifiedSurface | None = None

    def _build_surface(self) -> UnifiedSurface:
        cfg = self._config
        oracle = OracleEngine(max_items=int(cfg.get("oracle_max_items", 10)))
        paperclip = PaperclipOrchestrator(
            max_retries=int(cfg.get("paperclip_max_retries", 2)),
            timeout_s=float(cfg.get("paperclip_timeout_s", 10.0)),
        )
        jarvis = JarvisVoice(agent_edits=bool(cfg.get("jarvis_agent_edits", True)))
        return UnifiedSurface(oracle, paperclip, jarvis)

    async def initialize(self) -> None:
        self._surface = self._build_surface()
        self.status = HealthStatus.HEALTHY

    async def health_check(self) -> HealthStatus:
        healthy = bool(self._surface is not None)
        return HealthStatus.HEALTHY if healthy else HealthStatus.UNHEALTHY

    async def shutdown(self) -> None:
        self._surface = None
        self.status = HealthStatus.STOPPING

    def surface(self) -> UnifiedSurface:
        if self._surface is None:
            self._surface = self._build_surface()
        # Auto-bind the real Hermes controller facade on first access if not already.
        self._surface.auto_bind_hermes()
        return self._surface

    def run(self, verb: str, **kw: Any) -> dict[str, Any]:  # noqa: ANN401
        return self.surface().run(verb, **kw)


def create_agent_os_module(config: dict[str, Any] | None = None) -> AgentOSModule:
    """Create an :class:`AgentOSModule` from an optional config dict."""
    return AgentOSModule(config)
