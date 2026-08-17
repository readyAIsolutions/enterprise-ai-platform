"""Context Routing — task→(read/skip/skills) table with token discipline.

Built directly from the pulled JE Van Clief transcript "Stop Building AI Agents.
Use This Folder System Instead" (MkN-ss2Nl10), which explains the routing-table
mechanism that makes folder-based agentic work efficient:

    "a simple table that tells the AI: for this task, read these files, skip
     those files, you might need these skills. Without this, the AI either
     reads everything and runs out of room ... using way too many tokens, or it
     guesses wrong ... or you can't edit what it creates along the process."

This module *is* that table, made executable. It:
  * Holds a declarative routing table: task keyword -> {read: [...], skip: [...], skills: [...], budget_tokens}.
  * route(task) returns the exact read/skip/skills set for that task.
  * budget(task, file_sizes) returns whether the selected files fit within a
    token budget, and which to drop if not (progressive disclosure / context
    discipline — only load what the current task needs).

This directly implements the "context window is finite, so separate your
thoughts and read only what matters" principle from the same transcript.

Version: 1.0.0
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

TOKENS_PER_BYTE = 0.25   # ~4 chars per token, rough but useful heuristic


@dataclass
class RoutingRule:
    task: str
    read: List[str] = field(default_factory=list)   # file/glob patterns to read
    skip: List[str] = field(default_factory=list)   # patterns to explicitly skip
    skills: List[str] = field(default_factory=list) # skills the agent may need
    budget_tokens: int = 8000                       # max tokens to load for this task
    fallback: bool = False                          # True = catch-all rule


class ContextRouter:
    """Task->read/skip/skills routing table with a token-budget guard."""

    def __init__(self, rules: Optional[List[RoutingRule]] = None) -> None:
        self.rules = rules or []
        self._fallbacks = [r for r in self.rules if r.fallback]

    # ------------------------------------------------------------- rules
    @classmethod
    def from_dicts(cls, items: List[Dict]) -> "ContextRouter":
        return cls([RoutingRule(**{k: v for k, v in it.items()}) for it in items])

    def add_rule(self, rule: RoutingRule) -> None:
        self.rules.append(rule)
        if rule.fallback:
            self._fallbacks.append(rule)

    # ------------------------------------------------------------- route
    def route(self, task: str) -> RoutingRule:
        """Return the best-matching routing rule for a task.

        Match is exact-keyword-first, then substring, then the fallback rule.
        Falls back to an empty catch-all if none is registered.
        """
        t = task.lower()
        # exact match first
        for r in self.rules:
            if r.task.lower() == t:
                return r
        # substring match (longest keyword wins)
        best = None; best_len = -1
        for r in self.rules:
            if r.task in t and len(r.task) > best_len:
                best = r; best_len = len(r.task)
        if best:
            return best
        # fallback rule
        if self._fallbacks:
            return self._fallbacks[0]
        return RoutingRule(task="*", read=["**/*.md"], skills=[], budget_tokens=8000)

    # ------------------------------------------------------- token budget
    def budget(self, task: str, files: Optional[Dict[str, int]] = None,
               all_files: Optional[List[str]] = None) -> Dict:
        """Compute what to load for a task within its token budget.

        files: {path: bytes} of the available project files.
        all_files: just the path list (sizes read via Path). Picks the read
        patterns that fit under rule.budget_tokens, respecting skip patterns.
        Returns {read:[...], skipped:[...], tokens, within_budget}.
        """
        rule = self.route(task)
        sizes = files or {}
        paths = all_files or list(sizes.keys())
        # apply skip: absolute excludes
        def matches(name: str, pat: str) -> bool:
            pat = pat.replace("/", "").lower()
            n = name.lower()
            return pat in n or ("*" in pat and __import__("fnmatch").fnmatch(n, pat.lower().lstrip("/")))
        skipped = [p for p in paths if any(matches(p, s) for s in rule.skip)]
        # get read candidates (respecting skip)
        if rule.read and rule.read != ["**/*.md"]:
            cands = [p for p in paths
                     if any(matches(p, r) for r in rule.read)
                     and not any(matches(p, s) for s in rule.skip)]
        else:
            cands = [p for p in paths if p not in skipped]
        # fit under budget (greedy)
        read = []; used = 0
        for p in sorted(cands):
            sz = sizes.get(p, _file_size(p))
            tok = int(sz * TOKENS_PER_BYTE)
            if used + tok <= rule.budget_tokens or not read:
                if used + tok <= rule.budget_tokens:
                    read.append(p); used += tok
                else:
                    read.append(p); used += tok  # always include at least the first matched
                    break
            else:
                break
        return {
            "task": task, "rule": rule.task,
            "read": read, "skipped_read": [p for p in cands if p not in read],
            "explicit_skip": skipped,
            "tokens": used, "budget": rule.budget_tokens,
            "within_budget": used <= rule.budget_tokens,
        }

    def skills_for(self, task: str) -> List[str]:
        return self.route(task).skills


def _file_size(path: str) -> int:
    try:
        return Path(path).stat().st_size
    except Exception:
        return 0


__all__ = ["ContextRouter", "RoutingRule", "TOKENS_PER_BYTE", "__version__"]
__version__ = "1.0.0"