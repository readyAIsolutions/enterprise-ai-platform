"""Compose agentic workflows the way the transcript does — pure stdlib, network-free.

Grounded in the JEVanClief transcript *"Claude Code + Cursor: Making Agentic
workflows with an Agentic workflow!"*
(https://www.youtube.com/watch?v=v2UnNFmkia0). The speaker builds a multi-agent
pipeline by:

  * running Claude Code as a CLI tool (``claude`` in the terminal) or as a Cursor
    plugin, inside WSL or PowerShell;
  * authoring **MD files** (system prompts) that run across an entire dataset /
    codebase — Claude Code behaves like "a super advanced agent";
  * composing **sections of agents** — *parser agents*, *auditor agents*, and a
    *framework loader agent* that breaks a source document (e.g. a PDF of human
    rights codes) into its specific parts;
  * modelling each agent with Pydantic-style classes + JSON (a ``ParsedStatement``
    with fields ``individual``, ``description``, ``category``, ``field`` and a
    ``list of compliance``);
  * letting the agent generate its own **to-do list** before touching any code,
    and watching it "chug" through documents with auto-accept on (Shift-Tab turns
    it off);
  * refactoring one big ``massive.py`` into **modules that initiate from each
    other**;
  * estimating cost from tokens in/tokens out and an hourly API rate.

Everything here is deterministic, stdlib-only logic that *models* that workflow
so it can be orchestrated, validated and costed without any network access.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field as _dc_field
from typing import Any, Dict, Iterable, List, Optional

# Tools / environments named in the transcript.
TOOLS = ("claude_code", "cursor")
ENVIRONMENTS = ("wsl", "powershell", "terminal")

# Agent roles the speaker composes in the pipeline.
PARSER_AGENT = "parser_agent"
AUDITOR_AGENT = "auditor_agent"
FRAMEWORK_LOADER_AGENT = "framework_loader_agent"

# Default cost model grounded in the transcript's discussion of API vs. account
# access: ~$5/hour spent on tokens when running on API, and a pro account that
# costs between $20 and $100 per month.
DEFAULT_HOURLY_RATE = 5.0
DEFAULT_MONTHLY_RATE = 100.0
DEFAULT_DAILY_HOURS = 1.0


@dataclass
class AgentSpec:
    """A single agent in a composed workflow (e.g. a parser or auditor agent).

    Mirrors the transcript's practice of defining agents via classes + JSON so a
    model can instantiate them: each agent has a role, a human/system prompt (an
    ``.md`` system-prompt file), and the tools it may use.
    """

    name: str
    role: str
    system_prompt: str = ""
    tools: List[str] = _dc_field(default_factory=lambda: ["claude_code"])

    def __post_init__(self) -> None:
        unknown = [t for t in self.tools if t not in TOOLS]
        if unknown:
            raise ValueError(f"unknown tools: {unknown!r} (expected one of {TOOLS})")
        if self.role not in (
            PARSER_AGENT,
            AUDITOR_AGENT,
            FRAMEWORK_LOADER_AGENT,
        ):
            # Allow custom roles but keep the known set first-class.
            if not self.role or not self.role.strip():
                raise ValueError("agent role must be a non-empty string")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "system_prompt": self.system_prompt,
            "tools": list(self.tools),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentSpec":
        return cls(
            name=str(data["name"]),
            role=str(data["role"]),
            system_prompt=str(data.get("system_prompt", "")),
            tools=[str(t) for t in data.get("tools", ["claude_code"])],
        )


@dataclass
class Workflow:
    """An agentic workflow: an ordered composition of agent sections.

    The transcript describes building "sections of agents" that each handle part
    of the thought process the speaker used to do by hand. A workflow holds those
    sections in order plus a plan of steps.
    """

    name: str
    agents: List[AgentSpec] = _dc_field(default_factory=list)
    plan: List[str] = _dc_field(default_factory=list)

    def add_agent(self, agent: AgentSpec) -> "Workflow":
        if any(a.name == agent.name for a in self.agents):
            raise ValueError(f"agent {agent.name!r} already in workflow")
        self.agents.append(agent)
        return self

    def add_plan_step(self, step: str) -> "Workflow":
        if step and step.strip():
            self.plan.append(step.strip())
        return self

    @property
    def roles(self) -> List[str]:
        return [a.role for a in self.agents]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "agents": [a.to_dict() for a in self.agents],
            "plan": list(self.plan),
        }


@dataclass
class ParsedStatement:
    """Schema for a parsed compliance statement.

    Grounded directly in the transcript's ``ParsedStatement`` class, which the
    speaker watches the agent rebuild and verifies field-by-field:
    ``individual``, ``description``, ``category`` (the statement belongs to a
    category), ``field``, and a ``list of compliance``. The speaker even checks
    whether the agent is "doing the list as a string" — so we support both a real
    list and a string-serialised form.
    """

    individual: str
    description: str
    category: str
    field: str = ""
    compliance: List[str] = _dc_field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "individual": self.individual,
            "description": self.description,
            "category": self.category,
            "field": self.field,
            "compliance": list(self.compliance),
        }

    def to_json(self, list_as_string: bool = False) -> str:
        """Serialise to JSON; optionally render the compliance list as a string.

        Mirrors the transcript moment: "is it doing the list as a string though?"
        — a valid, explicitly-supported serialisation mode for downstream models.
        """
        payload: Dict[str, Any] = self.to_dict()
        if list_as_string:
            payload = dict(payload)
            payload["compliance"] = ", ".join(payload["compliance"])
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ParsedStatement":
        compliance = data.get("compliance", [])
        if isinstance(compliance, str):
            # Reverse the "list as a string" serialisation.
            compliance = [
                part.strip() for part in compliance.split(",") if part.strip()
            ]
        return cls(
            individual=str(data["individual"]),
            description=str(data["description"]),
            category=str(data["category"]),
            field=str(data.get("field", "")),
            compliance=[str(c) for c in compliance],
        )


def build_workflow(name: str, *agents: AgentSpec) -> Workflow:
    """Compose a workflow from an ordered set of agent sections."""
    workflow = Workflow(name=name)
    for agent in agents:
        workflow.add_agent(agent)
    return workflow


def create_todo_list(goal: str, steps: Iterable[str]) -> List[Dict[str, Any]]:
    """Generate an agent-style to-do list before any code is touched.

    The transcript stresses that the agent "creates actual tasks before it even
    starts editing lines". Each item carries an index, a task, and a done flag
    (all False at creation time).
    """
    if not goal or not goal.strip():
        raise ValueError("goal must be a non-empty string")
    todo: List[Dict[str, Any]] = []
    for i, step in enumerate(steps, start=1):
        if not step or not step.strip():
            continue
        todo.append(
            {"index": i, "task": step.strip(), "goal": goal.strip(), "done": False}
        )
    return todo


def decompose_module(source: str, filename: str = "massive.py") -> List[Dict[str, str]]:
    """Refactor a monolithic Python source file into modules that initiate each other.

    Grounded in the transcript's refactor of one big ``massive.py`` into modules
    that "initiate from each other". This splits the source into sections around
    top-level ``def`` / ``class`` definitions and names each candidate module after
    the identifier found there.
    """
    if not source.strip():
        raise ValueError("source must be non-empty")
    header_terms = {
        "import": "imports",
        "from": "imports",
    }
    modules: List[Dict[str, str]] = []
    current_name = "core"
    current = []

    def flush() -> None:
        nonlocal current
        if current:
            body = "\n".join(current).strip()
            if body:
                modules.append({"name": current_name, "source": body})
        current = []

    for raw_line in source.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        m = re.match(r"^(def|class)\s+([A-Za-z_]\w*)", stripped)
        if m:
            if m.group(1) == "class":
                # The ParsedStatement class is the anchor schema module.
                current_name = "parsed_statement" if "parsed_statement" in raw_line.lower() else "core"
            elif m.group(1) == "def":
                current_name = "core"
            flush()
        current.append(raw_line)
        if not current_name:
            current_name = "core"
    flush()

    if not modules:
        modules.append({"name": "core", "source": source.strip()})
    return modules


def estimate_cost(
    hours: Optional[float] = None,
    plan: str = "api",
    hourly_rate: float = DEFAULT_HOURLY_RATE,
) -> Dict[str, Any]:
    """Estimate the token/runtime cost of an agentic workflow run.

    Grounded in the transcript's cost discussion: running on the **API** spends
    roughly $5/hour in tokens in + tokens out for a big codebase, while a **pro**
    account costs between $20 and $100 per month and is limited by token limits
    rather than per-token spend.
    """
    if plan not in ("api", "pro", "max"):
        raise ValueError("plan must be one of 'api', 'pro', 'max'")
    if hours is None:
        hours = DEFAULT_DAILY_HOURS
    if hours < 0:
        raise ValueError("hours must be non-negative")

    result: Dict[str, Any] = {
        "plan": plan,
        "hours": hours,
        "hourly_rate": hourly_rate,
        "estimated_usd": round(hours * hourly_rate, 2),
        "monthly_cap_usd": DEFAULT_MONTHLY_RATE,
    }
    if plan == "api":
        result["billing_model"] = "per_token"
        result["estimated_usd"] = round(hours * hourly_rate, 2)
    else:
        result["billing_model"] = "monthly_subscription"
        result["estimated_usd"] = min(DEFAULT_MONTHLY_RATE, hours * hourly_rate)
    return result


def statement_matches(source: ParsedStatement, reference: ParsedStatement) -> bool:
    """Verify a parsed statement against a reference, field by field.

    Mirrors the transcript's verification pass: the speaker checks the agent's
    ``ParsedStatement`` matches their own field-by-field ("individual description
    category ... Yep."). This returns True only when every field agrees.
    """
    return (
        source.individual == reference.individual
        and source.description == reference.description
        and source.category == reference.category
        and source.field == reference.field
        and list(source.compliance) == list(reference.compliance)
    )


def workflow_stats(workflow: Workflow) -> Dict[str, Any]:
    """Summarise a composed workflow (agent count, roles, plan steps)."""
    return {
        "name": workflow.name,
        "agent_count": len(workflow.agents),
        "roles": workflow.roles,
        "plan_steps": len(workflow.plan),
    }
