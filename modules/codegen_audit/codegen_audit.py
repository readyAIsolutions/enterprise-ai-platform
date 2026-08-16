"""codegen_audit — deterministic, stdlib-only auditing of AI-generated code.

Grounded in three JE Van Clief transcripts:

* ``_rtyhVD4v4A`` "One of These AI Coding Tools Failed Completely" — how well AI
  coding tools understand a technical goal and produce *working, modular* code.
  -> hallucinated/broken imports that bricked builds; truncated data ("... add
     it later") that broke the pipeline's exact academic fidelity; feature
     claims without verification ("implemented" but not checked); the tool that
     "failed completely" never understood the goal.
* ``nWbM9Ye2sLw`` "Open Claw Vibe Coded an App. Real Developers Read Every Line
  and Tell You What They Found." — a team line-by-line security audit of a
  vibe-coded app. -> leaked/hardcoded API keys; re-inventing platform built-ins
  (own JWT/crypto instead of Supabase ``auth.getSession``) creating a new attack
  vector; unverified JWT ``iss`` accepting ANY token from ANY project.
* ``5B6W2OGfxq0`` "How One Line of Python Triggers 12,000 Lines of Code" — the
  execution stack source -> AST -> bytecode -> interpreter/runtime. -> the
  dependency / abstraction-depth analysis; every layer has error handling.

Pure stdlib, network-free, deterministic, unit-testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

__version__ = "1.0.0"

T_TOOL_COMPARISON = "_rtyhVD4v4A"
T_SECURITY_AUDIT = "nWbM9Ye2sLw"
T_EXECUTION_LAYERS = "5B6W2OGfxq0"


class Status(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


# ---------------------------------------------------------------------------
# Dependency / abstraction-depth analysis  (5B6W2OGfxq0)
# ---------------------------------------------------------------------------
EXECUTION_LAYERS: Tuple[Tuple[str, str], ...] = (
    ("parse", "source text -> abstract syntax tree"),
    ("ast", "tree -> bytecode compilation"),
    ("bytecode", "bytecode -> C interpreter execution"),
    ("interpreter_runtime", "runtime -> OS/hardware/electrons"),
)


@dataclass
class DependencyDepthResult:
    symbol: str
    depth: int
    direct_dependencies: int
    transitive_dependencies: int
    longest_chain: List[str] = field(default_factory=list)
    layers_crossed: List[str] = field(default_factory=list)
    has_cycle: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol, "depth": self.depth,
            "direct_dependencies": self.direct_dependencies,
            "transitive_dependencies": self.transitive_dependencies,
            "longest_chain": self.longest_chain,
            "layers_crossed": self.layers_crossed, "has_cycle": self.has_cycle,
        }


def dependency_depth(symbol, graph, max_depth=None) -> DependencyDepthResult:
    """How deep a symbol's dependency chain reaches.

    ``graph`` maps each symbol to the symbols it depends on.  Following the
    chain from ``symbol`` mirrors one line descending through the 12,000 lines
    of interpreter/runtime — the deeper the chain, the more abstraction layers
    its execution crosses.  Deterministic DFS longest-path with cycle detection.
    """
    direct = set(graph.get(symbol, ()) or ())
    longest: List[str] = []
    visited: Set[str] = set()
    in_rec: Set[str] = set()
    has_cycle = False

    def dfs(node, path):
        nonlocal has_cycle
        if node in in_rec:  # back-edge -> cycle; stop to avoid infinite recursion
            has_cycle = True
            return
        if node in visited:
            return
        in_rec.add(node)
        deps = list(graph.get(node, ()) or ())
        if not deps:
            if len(path) > len(longest):
                longest[:] = list(path)
        else:
            for dep in deps:
                dfs(dep, path + [dep])
        in_rec.discard(node)
        visited.add(node)

    dfs(symbol, [symbol])
    transitive = set(longest) | direct
    transitive.discard(symbol)
    depth = len(longest)
    if max_depth is not None:
        depth = min(depth, max_depth)

    names = [n for n, _ in EXECUTION_LAYERS]
    return DependencyDepthResult(
        symbol=symbol, depth=depth,
        direct_dependencies=len(direct), transitive_dependencies=len(transitive),
        longest_chain=longest,
        layers_crossed=names[: max(1, min(depth, len(names)))],
        has_cycle=has_cycle,
    )


@dataclass
class BlastRadiusResult:
    symbol: str
    direct_dependents: int
    transitive_dependents: int
    dependents: List[str] = field(default_factory=list)
    over_broad: bool = False
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol, "direct_dependents": self.direct_dependents,
            "transitive_dependents": self.transitive_dependents,
            "dependents": self.dependents, "over_broad": self.over_broad,
            "reason": self.reason,
        }


def dependency_blast_radius(symbol, graph, over_broad_threshold=5) -> BlastRadiusResult:
    """Outward reach of a symbol: who breaks if it breaks.

    A symbol has an over-broad blast radius when one failure cascades to many
    dependents — matching the audit's finding that a single generated crypto
    layer radiated an attack surface across the whole app.
    """
    reverse: Dict[str, Set[str]] = {}
    for node, deps in graph.items():
        for dep in (deps or ()):
            reverse.setdefault(dep, set()).add(node)

    direct = sorted(reverse.get(symbol, set()))
    transitive: Set[str] = set()
    queue = list(direct)
    seen = {symbol}
    while queue:
        cur = queue.pop(0)
        if cur in seen:
            continue
        seen.add(cur)
        transitive.add(cur)
        queue.extend(reverse.get(cur, ()))

    over_broad = len(transitive) > over_broad_threshold
    reason = (
        ""
        if not over_broad
        else f"symbol '{symbol}' failure cascades to {len(transitive)} dependents; "
        f"single-point failures radiate an outsized blast radius (>{over_broad_threshold})."
    )
    return BlastRadiusResult(
        symbol=symbol, direct_dependents=len(direct),
        transitive_dependents=len(transitive), dependents=sorted(transitive),
        over_broad=over_broad, reason=reason,
    )


# ---------------------------------------------------------------------------
# Static heuristic code review  (_rtyhVD4v4A + nWbM9Ye2sLw)
# ---------------------------------------------------------------------------
BUILTIN_MODULES: Set[str] = {
    "abc", "argparse", "array", "ast", "asyncio", "base64", "binascii", "bisect",
    "builtins", "cmath", "collections", "concurrent", "configparser", "contextlib",
    "copy", "csv", "dataclasses", "datetime", "decimal", "enum", "errno",
    "functools", "gc", "glob", "hashlib", "heapq", "hmac", "html", "http", "io",
    "importlib", "inspect", "itertools", "json", "logging", "math", "multiprocessing",
    "operator", "os", "pathlib", "pickle", "platform", "queue", "random", "re",
    "secrets", "shutil", "signal", "socket", "sqlite3", "ssl", "statistics",
    "string", "struct", "subprocess", "sys", "tempfile", "threading", "time",
    "tokenize", "traceback", "types", "typing", "unicodedata", "urllib", "uuid",
    "warnings", "weakref", "xml", "zipfile", "zlib",
}

_IMPORT_RE = re.compile(
    r"^\s*(?:import\s+(?P<imp>[A-Za-z_][\w\.]*(?:\s*,\s*[A-Za-z_][\w\.]*)*)"
    r"|from\s+(?P<frm>[A-Za-z_][\w\.]*)\s+import\s+(?P<names>.+?))(?:#.*)?$"
)
_FUNC_DEF_RE = re.compile(r"^\s*def\s+([A-Za-z_]\w*)\s*\((?P<params>[^)]*)\)\s*(->.*)?:")
_SECRET_RE = re.compile(
    r"\b(api[_-]?key|apikey|token|access[_-]?token|secret|secret[_-]?key|"
    r"passwd|password|client[_-]?secret)\b\s*(=|\:)\s*['\"][^'\"]{6,}['\"]",
    re.IGNORECASE,
)
_SECRET_LITERAL_RE = re.compile(
    r"\b(sk-[A-Za-z0-9_\-]{8,}|AKIA[A-Z0-9]{16}|[A-Fa-f0-9]{32,}|eyJ[A-Za-z0-9\-_\.]{10,})\b"
)
_NONDET_RE = re.compile(
    r"\b(random\.|secrets\.|uuid4|os\.urandom|datetime\.now|time\.time|"
    r"time\.perf_counter|time\.sleep|time\.local|os\.getpid)\b"
)
_NETWORK_OR_IO_RE = re.compile(
    r"\b(open\(|subprocess|requests\.|urlopen|urlretrieve|socket\.|"
    r"\.execute\(|exec\(|eval\(|os\.system|connect\()"
)
_TRUNCATION_MARKERS = ("...", "\u2026", "add it later", "you'll add it later",
                       "TODO", "FIXME", "placeholder")


@dataclass
class CheckResult:
    check: str
    status: Status
    message: str
    evidence: str = ""
    line: Optional[int] = None
    transcript_ref: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check": self.check, "status": self.status.value,
            "message": self.message, "evidence": self.evidence,
            "line": self.line, "transcript_ref": self.transcript_ref,
        }


@dataclass
class CodeReview:
    source_lines: int
    checks: List[CheckResult] = field(default_factory=list)

    def check(self, name):
        for c in self.checks:
            if c.check == name:
                return c
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {"source_lines": self.source_lines,
                "checks": [c.to_dict() for c in self.checks]}


def _used(text, name):
    return bool(re.search(r"\b" + re.escape(name) + r"\b", text))


def review_code(source, available_modules=None, acknowledge_imports=None) -> CodeReview:
    """Run all static heuristic checks over ``source``.

    ``available_modules`` = third-party modules the caller vouches are
    resolvable (so a real dependency isn't flagged hallucinated).
    ``acknowledge_imports`` = aliases intentionally kept (suppress unused).
    Deterministic, network-free, stdlib-only.
    """
    lines = (source or "").splitlines()
    text = source or ""
    avail = set(available_modules or ())
    acknowledged = set(acknowledge_imports or ())
    checks: List[CheckResult] = []

    imports: List[Tuple[str, str, int]] = []  # (module, alias, lineno)
    body_lines: List[str] = []
    for i, raw in enumerate(lines, start=1):
        line = raw.rstrip()
        m = _IMPORT_RE.match(line)
        if m:
            if m.group("imp"):
                for part in m.group("imp").split(","):
                    part = part.strip()
                    if not part:
                        continue
                    alias = part.split(" as ")[-1].split(".")[0].strip()
                    imports.append((part.split(".")[0], alias, i))
            else:
                mod_top = m.group("frm").split(".")[0]
                for alias in re.split(r"\s*,\s*", m.group("names")):
                    alias = alias.strip().split(" as ")[-1].strip()
                    imports.append((mod_top, alias, i))
            # import lines excluded from body so unused-import detection works
        else:
            body_lines.append(line)
    body = "\n".join(body_lines)
    imports_used = {a for _, a, _ in imports if a in acknowledged or _used(body, a)}

    # 1) hallucinated / unresolved imports (T1: import errors bricked a build)
    bad = [(mod, a, ln) for mod, a, ln in imports
           if mod not in BUILTIN_MODULES and mod not in avail]
    if bad:
        names = ", ".join(sorted({f"{m} (as {a})" for m, a, _ in bad}))
        checks.append(CheckResult(
            "hallucinated_import", Status.FAIL,
            f"unresolved/hallucinated import(s): {names} - not stdlib and not declared "
            "available; in the comparison, import/config errors bricked the app.",
            evidence=str(bad[:3]), line=bad[0][2], transcript_ref=T_TOOL_COMPARISON))
    else:
        checks.append(CheckResult("hallucinated_import", Status.PASS,
                                  "all imports resolve to stdlib or declared modules.",
                                  transcript_ref=T_TOOL_COMPARISON))

    # 2) unused imports (T2: devs flag dead imports reading every line)
    unused = [(m, a) for m, a, _ in imports if a not in acknowledged and a not in imports_used]
    if unused:
        names = ", ".join(sorted({f"{a} ({m})" for m, a in unused}))
        checks.append(CheckResult("unused_import", Status.WARN,
                                  f"imports never referenced in the body: {names}. Dead "
                                  "imports are a reviewer-visible smell.",
                                  evidence=names[:200], transcript_ref=T_SECURITY_AUDIT))
    else:
        checks.append(CheckResult("unused_import", Status.PASS, "no unused imports.",
                                  transcript_ref=T_SECURITY_AUDIT))

    # 3) print debugging left in (T2: leftover debug the reviewers deleted)
    pl = [i for i, l in enumerate(lines, start=1) if re.search(r"(^|[^.\w])print\s*\(", l)]
    if pl:
        checks.append(CheckResult("debug_print", Status.WARN,
                                  f"print() debugging call(s) at line(s) {pl[:6]}. Vibe-coded "
                                  "apps ship debug prints reviewers strip out.",
                                  evidence=str(pl[:6]), line=pl[0], transcript_ref=T_SECURITY_AUDIT))
    else:
        checks.append(CheckResult("debug_print", Status.PASS, "no stray debug prints.",
                                  transcript_ref=T_SECURITY_AUDIT))

    # 4) silent bare except (T3: every layer has error handling; bare swallows it)
    bare = [i for i, l in enumerate(lines, start=1)
            if re.search(r"^\s*except\s*:?", l) and ":" in l and len(l.strip()) < 12]
    if bare:
        checks.append(CheckResult("bare_except", Status.FAIL,
                                  f"silent bare except at line(s) {bare[:6]} - swallows errors. "
                                  "The stack is built on error handling at every layer.",
                                  evidence=str(bare[:6]), line=bare[0],
                                  transcript_ref=T_EXECUTION_LAYERS))
    else:
        checks.append(CheckResult("bare_except", Status.PASS, "no bare except clauses.",
                                  transcript_ref=T_EXECUTION_LAYERS))

    # 5) overly-broad except (T2: broad handling that misses verification)
    broad = [i for i, l in enumerate(lines, start=1)
             if re.search(r"^\s*except\s+(Exception|BaseException|RuntimeError)\b", l)]
    if broad:
        checks.append(CheckResult("broad_except", Status.WARN,
                                  f"overly-broad except at line(s) {broad[:6]} - masks the "
                                  "failures the audit warns about.",
                                  evidence=str(broad[:6]), line=broad[0],
                                  transcript_ref=T_SECURITY_AUDIT))
    else:
        checks.append(CheckResult("broad_except", Status.PASS, "no broad except handlers.",
                                  transcript_ref=T_SECURITY_AUDIT))

    # 6) missing type hints (T1/T2: rigor & clarity of a modular refactor)
    untyped = []
    for i, l in enumerate(lines, start=1):
        m = _FUNC_DEF_RE.match(l)
        if m and "->" not in l and ":" not in re.sub(r"def\s+\w+\s*", "", m.group("params") or ""):
            untyped.append((i, m.group(1)))
    if untyped:
        shown = untyped[:5]
        checks.append(CheckResult("missing_type_hint", Status.WARN,
                                  f"{len(untyped)} function(s) lack type hints (e.g. {shown}). "
                                  "Explicit contracts let other agents/devs navigate.",
                                  evidence=str(shown), line=untyped[0][0],
                                  transcript_ref=T_TOOL_COMPARISON))
    else:
        checks.append(CheckResult("missing_type_hint", Status.PASS, "functions are type-hinted.",
                                  transcript_ref=T_TOOL_COMPARISON))

    # 7) TODO / truncation stubs (T1: "... add it later" fidelity loss)
    trunc = [i for i, l in enumerate(lines, start=1) if any(t in l for t in _TRUNCATION_MARKERS)]
    if trunc:
        checks.append(CheckResult("todo_stub", Status.WARN,
                                  f"TODO/placeholder/truncation marker(s) at line(s) {trunc[:6]}. "
                                  "Models truncated data with '...' and told the author they'd "
                                  "'add it later', losing exactness.",
                                  evidence=str(trunc[:6]), line=trunc[0],
                                  transcript_ref=T_TOOL_COMPARISON))
    else:
        checks.append(CheckResult("todo_stub", Status.PASS, "no TODO/truncation stubs.",
                                  transcript_ref=T_TOOL_COMPARISON))

    # 8) non-determinism (T3: probabilistic layers need deterministic engineering)
    nondet = [(i, l.strip()[:80]) for i, l in enumerate(lines, start=1) if _NONDET_RE.search(l)]
    if nondet:
        checks.append(CheckResult("non_deterministic", Status.WARN,
                                  f"non-deterministic primitive(s) at line(s) "
                                  f"{[i for i, _ in nondet[:6]]} - the stack is probabilistic "
                                  "underneath; generated code should be reproducible.",
                                  evidence=str(nondet[:3]), line=nondet[0][0],
                                  transcript_ref=T_EXECUTION_LAYERS))
    else:
        checks.append(CheckResult("non_deterministic", Status.PASS,
                                  "no obvious non-deterministic primitives.",
                                  transcript_ref=T_EXECUTION_LAYERS))

    # 9) hardcoded secrets (T2: leaked API key Google had to lock down)
    hits = [(i, l.strip()[:60]) for i, l in enumerate(lines, start=1)
            if _SECRET_RE.search(l) or _SECRET_LITERAL_RE.search(l)]
    if hits:
        checks.append(CheckResult("secret_in_code", Status.FAIL,
                                  f"possible hardcoded secret(s)/credential(s) at line(s) "
                                  f"{[i for i, _ in hits[:6]]}. The audit found a leaked API key "
                                  "Google itself had to lock down - AI cannot see a secret not "
                                  "in the code.",
                                  evidence=str(hits[:3]), line=hits[0][0],
                                  transcript_ref=T_SECURITY_AUDIT))
    else:
        checks.append(CheckResult("secret_in_code", Status.PASS, "no hardcoded secrets detected.",
                                  transcript_ref=T_SECURITY_AUDIT))

    # 10) unverified auth (T2: custom auth never verified the JWT issuer)
    if re.search(r"\bjwt\.decode\b|\bverify_token\b|\bdecode_token\b", text) and "iss" not in text:
        checks.append(CheckResult("unverified_auth", Status.FAIL,
                                  "auth token decoding without an issuer ('iss')/claims check. "
                                  "The audit showed generated auth accepting ANY Supabase JWT "
                                  "from ANY project because it never verified the issuer.",
                                  transcript_ref=T_SECURITY_AUDIT))
    else:
        checks.append(CheckResult("unverified_auth", Status.PASS, "no unverified token-decoding.",
                                  transcript_ref=T_SECURITY_AUDIT))

    # 11) redundant reinvention (T2: own crypto instead of a platform built-in)
    reinvent = [i for i, l in enumerate(lines, start=1)
                if re.search(r"^\s*def\s+(encode|decode)_(token|jwt|auth|session|secret)", l)
                or re.search(r"^\s*def\s+(create|make|build)_(encoder|crypto|token|jwt)", l)]
    if reinvent:
        checks.append(CheckResult("redundant_reinvention", Status.WARN,
                                  f"custom auth/crypto re-implementation at line(s) {reinvent[:6]}. "
                                  "The team found the AI built its own JWT/crypto layer instead of "
                                  "the platform's built-in auth - a new attack vector.",
                                  evidence=str(reinvent[:6]), line=reinvent[0],
                                  transcript_ref=T_SECURITY_AUDIT))
    else:
        checks.append(CheckResult("redundant_reinvention", Status.PASS, "no re-invented platform layer.",
                                  transcript_ref=T_SECURITY_AUDIT))

    # 12) missing error handling around risky ops (T3: error handling every layer)
    risky = sum(1 for l in lines if _NETWORK_OR_IO_RE.search(l))
    has_try = bool(re.search(r"\btry\s*:", text)) and bool(re.search(r"\bexcept\b", text))
    if risky and not has_try:
        checks.append(CheckResult("error_handling", Status.WARN,
                                  f"{risky} risky I/O/exec op(s) but file has no try/except. Every "
                                  "stack layer is engineered with error handling.",
                                  evidence=f"risky_ops={risky}, try/except=0",
                                  transcript_ref=T_EXECUTION_LAYERS))
    else:
        checks.append(CheckResult("error_handling", Status.PASS,
                                  "risky ops are paired with error handling (or none present).",
                                  transcript_ref=T_EXECUTION_LAYERS))

    # 13) dangerous dynamic eval/exec (T3/T2 security)
    dyn = [i for i, l in enumerate(lines, start=1) if re.search(r"\b(eval|exec|os\.system)\s*\(", l)]
    if dyn:
        checks.append(CheckResult("dangerous_eval", Status.WARN,
                                  f"dynamic eval()/exec()/os.system() at line(s) {dyn[:6]} - common "
                                  "injection & non-determinism source in generated code.",
                                  evidence=str(dyn[:6]), line=dyn[0],
                                  transcript_ref=T_EXECUTION_LAYERS))
    else:
        checks.append(CheckResult("dangerous_eval", Status.PASS, "no dynamic eval/exec detected.",
                                  transcript_ref=T_EXECUTION_LAYERS))

    # 14) feature-verification markers (T1: best tool verified its features)
    if re.search(r"\b(assert|verify|test_|check|validate)\b", text):
        checks.append(CheckResult("feature_verification", Status.PASS,
                                  "code contains verification/assertion markers - matches the tool "
                                  "that actually verified its claimed features.",
                                  transcript_ref=T_TOOL_COMPARISON))
    else:
        checks.append(CheckResult("feature_verification", Status.WARN,
                                  "no explicit verification/assertion markers - without "
                                  "verification, feature claims are unproven.",
                                  transcript_ref=T_TOOL_COMPARISON))

    return CodeReview(source_lines=len(lines), checks=checks)


# ---------------------------------------------------------------------------
# Review scoring report
# ---------------------------------------------------------------------------
def score_checks(checks: Sequence[CheckResult]) -> "ReviewScore":
    """Aggregate per-check results into an overall grade + verdict."""
    counts = {s: 0 for s in Status}
    fails = sum(1 for c in checks if c.status is Status.FAIL)
    warns = sum(1 for c in checks if c.status is Status.WARN)
    for c in checks:
        counts[c.status] += 1
    total = len(checks) or 1
    if fails:
        grade = "F" if fails >= total * 0.2 else ("D" if fails >= total * 0.1 else "C")
    elif warns:
        grade = "B"
    else:
        grade = "A"
    verdict = Status.FAIL if fails else Status.PASS
    return ReviewScore(
        total=total, passed=counts[Status.PASS], warned=counts[Status.WARN],
        failed=counts[Status.FAIL], grade=grade, verdict=verdict,
        summary=(f"{total} checks: {counts[Status.PASS]} PASS, {counts[Status.WARN]} WARN, "
                 f"{counts[Status.FAIL]} FAIL."),
    )


@dataclass
class ReviewScore:
    total: int
    passed: int
    warned: int
    failed: int
    grade: str
    verdict: Status
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"total": self.total, "passed": self.passed, "warned": self.warned,
                "failed": self.failed, "grade": self.grade,
                "verdict": self.verdict.value, "summary": self.summary}


# ---------------------------------------------------------------------------
# Task-understanding evaluator  (_rtyhVD4v4A + nWbM9Ye2sLw)
# ---------------------------------------------------------------------------
@dataclass
class RequirementResult:
    requirement: str
    status: Status
    detail: str
    transcript_ref: str = T_TOOL_COMPARISON

    def to_dict(self) -> Dict[str, Any]:
        return {"requirement": self.requirement, "status": self.status.value,
                "detail": self.detail, "transcript_ref": self.transcript_ref}


@dataclass
class TaskUnderstandingReport:
    overall: Status
    total: int
    covered: int
    missing: List[str]
    fidelity_ok: bool
    results: List[RequirementResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"overall": self.overall.value, "total": self.total,
                "covered": self.covered, "missing": self.missing,
                "fidelity_ok": self.fidelity_ok,
                "results": [r.to_dict() for r in self.results]}


def _tokens(req):
    return [t for t in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", req.lower()) if len(t) > 2]


def evaluate_requirements(requirements, delivered, require_fidelity=True) -> TaskUnderstandingReport:
    """Does generated/delivered code satisfy the stated goals?

    The core question of the comparison video: does the model understand the
    technical goal and meet the requirements?  A requirement is MISSING when
    none of its tokens appear in the delivered text.  ``require_fidelity``
    warns when truncation markers suggest data was shortened, not preserved
    exactly (the "academic fidelity" failure).
    """
    lowered = (delivered or "").lower()
    results: List[RequirementResult] = []
    missing: List[str] = []
    total = covered = 0
    for raw in requirements or ():
        req = (raw or "").strip()
        toks = _tokens(req)
        if not req or not toks:
            continue
        total += 1
        if all(t in lowered for t in toks):
            covered += 1
            results.append(RequirementResult(req, Status.PASS,
                                             "requirement tokens present in delivered code."))
        else:
            missing.append(req)
            results.append(RequirementResult(req, Status.FAIL,
                                             "requirement not satisfied: no evidence in delivered "
                                             "code; the tool that 'failed completely' never closed "
                                             "this gap."))

    fidelity_ok = True
    if require_fidelity and "..." in lowered:
        fidelity_ok = False
        results.append(RequirementResult("data_fidelity", Status.WARN,
                                         "truncation markers ('...') - models shortened large "
                                         "data lists, breaking the exactness the pipeline needs.",
                                         transcript_ref=T_TOOL_COMPARISON))
    return TaskUnderstandingReport(overall=Status.FAIL if missing else Status.PASS,
                                   total=total, covered=covered, missing=missing,
                                   fidelity_ok=fidelity_ok, results=results)


def verify_features(requested, claimed, actual) -> TaskUnderstandingReport:
    """Feature-verification: are claimed features actually present?

    One tool verified its features while another just said "implemented".
    A claimed-but-unverifiable feature leaves only a WARN; a truly absent
    requested feature is a FAIL.
    """
    lowered = (actual or "").lower()
    claimed_set = {c.strip() for c in (claimed or ()) if c.strip()}
    results: List[RequirementResult] = []
    missing: List[str] = []
    overall = Status.PASS
    for f in requested or ():
        f = f.strip()
        toks = _tokens(f)
        if not f or not toks:
            continue
        present = all(t in lowered for t in toks)
        was_claimed = f in claimed_set
        if present:
            results.append(RequirementResult(f, Status.PASS, "feature verified present."))
        elif was_claimed:
            missing.append(f)
            results.append(RequirementResult(
                f, Status.WARN, "claimed implemented but no evidence in output - claims without "
                "verification (the audit found 'implemented' claims that were not)."))
            if overall is Status.PASS:
                overall = Status.WARN
        else:
            missing.append(f)
            results.append(RequirementResult(f, Status.FAIL, "required feature missing entirely."))
            overall = Status.FAIL
    return TaskUnderstandingReport(overall=overall, total=len(results),
                                   covered=sum(1 for r in results if r.status is Status.PASS),
                                   missing=missing, fidelity_ok=True, results=results)


# ---------------------------------------------------------------------------
# Convenience wrapper (pure)
# ---------------------------------------------------------------------------
def audit_code(source, available_modules=None, requirements=None) -> Dict[str, Any]:
    """Run the full audit pipeline: static review + score + task understanding."""
    review = review_code(source, available_modules=available_modules)
    return {
        "review": review.to_dict(),
        "score": score_checks(review.checks).to_dict(),
        "task_understanding": (
            evaluate_requirements(requirements, source).to_dict() if requirements else None
        ),
    }


__all__ = [
    "Status", "CheckResult", "CodeReview", "ReviewScore",
    "DependencyDepthResult", "BlastRadiusResult",
    "RequirementResult", "TaskUnderstandingReport",
    "EXECUTION_LAYERS", "BUILTIN_MODULES",
    "review_code", "score_checks", "evaluate_requirements", "verify_features",
    "dependency_depth", "dependency_blast_radius", "audit_code",
    "T_TOOL_COMPARISON", "T_SECURITY_AUDIT", "T_EXECUTION_LAYERS", "__version__",
]
