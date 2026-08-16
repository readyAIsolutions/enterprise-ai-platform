"""procurement_bid_automation — deterministic, stdlib-only procurement / RFP bid
assistant.

Grounded in the real JE Van Clief transcripts:

* ``I-enT6szVQQ.md`` — "I Used AI to Fix Government Contracting". Walks through
  automating government contracting: the main portals (Bidnet Direct, SAM.gov),
  solicitation types (RFQ, RFP, IFB, RFI), government procurement codes (NAICS,
  NIGP, PSC), CAGE codes, capability statements ("a one to two page PDF,
  government buyers expect this format"), vendor profile optimization with a
  profile grade ("75 out of 100 ... it's missing critical information, specific
  contact information, geographic coverage ... clearance level or GSA
  schedules"), company-info -> apply/codes guidance ("Here is my company's info.
  How would I apply and what codes should I use?"), and similarity scoring
  ("it immediately creates a similarity score or your chances of being similar
  for a contract ... I got a 43% similarity here"). A central design point in
  the talk is that a *deterministic reference database* of codes/terms beats
  fine-tuned model guessing: "instead of having to fine-tune a model ... you can
  just come in and change it right here and then the AI references this list
  which is really important when it comes to accuracy."

* ``AjzBaEkWkNA.md`` — "AI Agency and Consulting Models are DEAD". Argues the
  old strategy->implementation->adoption consulting chain is collapsing because
  AI compresses the cost of building: "Some solutions are gamechanging. We're
  seeing thousands of percent of ROI. Other ones are absolutely negative." The
  right stack is "60% traditional software, 20% rule-based logic ... 10%/20% AI
  implementation", you must "provide value beyond what the individual ... can
  do themselves", and you decide what to invest in by returning to first
  principles about fit. This module applies that ROI/fit critique to the
  bid/no-bid decision: does your company *actually fit* this opportunity, or is
  it effort with no chance of value.

Everything here is pure Python stdlib: no network, no filesystem, no third-party
imports — fully unit-testable and deterministic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

__all__ = [
    "Code", "ScoredCode", "CodeMatcher", "BUILTIN_TAXONOMY",
    "CompanyProfile", "CapabilityStatement", "generate_capability_statement",
    "ProfileGrade", "grade_profile",
    "Solicitation", "SolicitationAnalysis", "analyze_solicitation",
    "OpportunityAssessment", "assess_opportunity",
    "tokenize", "keyword_overlap",
]


# --------------------------------------------------------------------------- #
# Text helpers
# --------------------------------------------------------------------------- #
_STOP = {
    "a", "an", "the", "and", "or", "but", "for", "with", "from", "that",
    "this", "these", "those", "your", "our", "their", "its", "into", "onto",
    "will", "shall", "must", "can", "may", "should", "have", "has", "had",
    "are", "is", "was", "were", "of", "to", "in", "on", "by", "at", "as",
    "not", "no", "be", "do", "does", "done", "being", "been", "etc", "e.g",
    "i", "you", "we", "he", "she", "it", "they", "me", "us", "them", "my",
    "his", "her", "what", "when", "where", "how", "who", "why", "here",
    "there", "just", "like", "going", "really", "actually", "also", "then",
    "proposal", "contract", "solicitation",
}


def tokenize(text: str) -> List[str]:
    """Lowercase word tokens (letters/digits) with stop words removed."""
    out: List[str] = []
    for tok in re.findall(r"[a-zA-Z0-9]+", text.lower()):
        if tok in _STOP:
            continue
        out.append(tok)
    return out


def keyword_overlap(description_tokens: Sequence[str],
                    keywords: Sequence[str]) -> int:
    """Count how many of ``keywords`` appear in the token set (exact match on
    the token, so multi-word phrases are counted once per phrase hit)."""
    token_set = set(description_tokens)
    hits = 0
    for kw in keywords:
        parts = [p for p in tokenize(kw) if p]
        if not parts:
            continue
        if all(p in token_set for p in parts):
            hits += 1
    return hits


# --------------------------------------------------------------------------- #
# Procurement code taxonomy (NAICS / NIGP / PSC style)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Code:
    """A single procurement code in the taxonomy.

    ``id`` — the official code string (e.g. ``"541511"`` or a NIGP ``"91821"``).
    ``family`` — one of ``"naics"``, ``"nigp"`` or ``"psc"``.
    ``title`` — human description of what the code covers.
    ``keywords`` — terms that indicate this code is a fit for the capability.
    """
    id: str
    title: str
    family: str
    keywords: Tuple[str, ...] = ()

    def matches(self, tokens: Sequence[str]) -> int:
        return keyword_overlap(tokens, self.keywords)


@dataclass(frozen=True)
class ScoredCode:
    code: Code
    score: int
    matched: Tuple[str, ...] = ()

    @property
    def id(self) -> str:  # type: ignore[return]
        return self.code.id

    @property
    def family(self) -> str:
        return self.code.family

    @property
    def title(self) -> str:
        return self.code.title


def _tok_matched(tokens: Sequence[str], keywords: Sequence[str]) -> List[str]:
    token_set = set(tokens)
    matched: List[str] = []
    for kw in keywords:
        parts = [p for p in tokenize(kw) if p]
        if parts and all(p in token_set for p in parts):
            matched.append(kw)
    return matched


# A small, *curated* reference taxonomy grounded in the codes the transcript
# names (NAICS 5415xx computer services, 54161x management consulting, NIGP
# 91821 business consulting, 91824 IT consulting, 91899 computer related
# services, 91838 data processing, plus PSC/CAGE-adjacent concepts). In
# production this would be the "reference list the AI points at" from the talk.
BUILTIN_TAXONOMY: Tuple[Code, ...] = (
    Code("541511", "Custom Computer Programming Services", "naics",
         ("software", "programming", "custom software", "application development",
          "code", "development")),
    Code("541512", "Computer Systems Design Services", "naics",
         ("systems design", "system design", "it architecture", "solution architecture",
          "integration")),
    Code("541519", "Other Computer Related Services", "naics",
         ("computer", "it services", "computer related", "technical support")),
    Code("541611", "Administrative Management and General Management Consulting", "naics",
         ("management consulting", "business consulting", "advisory", "operations management")),
    Code("541618", "Other Management Consulting Services", "naics",
         ("management consulting", "strategy", "consulting", "advisory", "process improvement")),
    Code("541690", "Other Scientific and Technical Consulting Services", "naics",
         ("technical consulting", "research", "analysis", "science")),
    Code("541330", "Engineering Services", "naics",
         ("engineering", "design", "civil", "mechanical")),
    Code("541990", "All Other Professional, Scientific, and Technical Services", "naics",
         ("professional services", "technical services", "consulting services")),
    Code("518210", "Data Processing, Hosting, and Related Services", "naics",
         ("data", "data processing", "hosting", "data verification", "data analysis",
          "database")),
    Code("5415110", "Cybersecurity and Risk Management", "psc",
         ("cyber", "cybersecurity", "security", "risk", "risk management", "compliance",
          "zero trust")),
    Code("91821", "Management / Business Consulting Services", "nigp",
         ("consulting", "management", "business consulting", "advisory", "training")),
    Code("91824", "IT / Technology Consulting Services", "nigp",
         ("it consulting", "technology", "software consulting", "digital", "ai")),
    Code("91899", "Computer Related Services", "nigp",
         ("computer", "it services", "computer related", "support")),
    Code("91838", "Data Processing Services", "nigp",
         ("data", "data processing", "verification", "analysis", "records")),
    Code("91898", "Cybersecurity Services", "nigp",
         ("cyber", "security", "risk", "network")),
)


class CodeMatcher:
    """Deterministic code recommendation engine.

    Scores candidate codes purely by keyword overlap against a company
    capability description — the "reference this list ... for accuracy" idea
    from the transcript, implemented as plain token matching rather than model
    guessing.
    """

    def __init__(self, codes: Optional[Sequence[Code]] = None) -> None:
        self.codes: Tuple[Code, ...] = tuple(codes) if codes else BUILTIN_TAXONOMY

    def score_codes(self, description: str) -> List[ScoredCode]:
        tokens = tokenize(description)
        scored = [
            ScoredCode(code=code, score=code.matches(tokens),
                       matched=tuple(_tok_matched(tokens, code.keywords)))
            for code in self.codes
        ]
        scored.sort(key=lambda s: (s.score, s.code.id), reverse=True)
        return scored

    def recommend_codes(self, description: str,
                        limit: Optional[int] = None,
                        min_score: int = 1) -> List[ScoredCode]:
        """Top scoring codes with at least ``min_score`` keyword hits."""
        ranked = [s for s in self.score_codes(description) if s.score >= min_score]
        if limit is not None:
            ranked = ranked[:limit]
        return ranked

    def code_by_id(self, code_id: str) -> Optional[Code]:
        for code in self.codes:
            if code.id == code_id:
                return code
        return None


# --------------------------------------------------------------------------- #
# Company profile & capability statement
# --------------------------------------------------------------------------- #
@dataclass
class CompanyProfile:
    """Structured vendor/company profile — the fields the transcript says matter
    for government contracting (mission, what you do, target agencies/sectors,
    past performance, certifications, team size)."""
    name: str = ""
    description: str = ""
    mission: str = ""
    target_agencies: List[str] = field(default_factory=list)
    sectors: List[str] = field(default_factory=list)
    past_performance: List[str] = field(default_factory=list)
    certifications: List[str] = field(default_factory=list)
    team_size: int = 0
    geographic_coverage: str = ""
    contact_info: str = ""
    differentiators: List[str] = field(default_factory=list)
    client_list: List[str] = field(default_factory=list)
    clearance_level: str = ""
    gsa_schedules: List[str] = field(default_factory=list)
    cage_code: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "mission": self.mission,
            "target_agencies": list(self.target_agencies),
            "sectors": list(self.sectors),
            "past_performance": list(self.past_performance),
            "certifications": list(self.certifications),
            "team_size": self.team_size,
            "geographic_coverage": self.geographic_coverage,
            "contact_info": self.contact_info,
            "differentiators": list(self.differentiators),
            "client_list": list(self.client_list),
            "clearance_level": self.clearance_level,
            "gsa_schedules": list(self.gsa_schedules),
            "cage_code": self.cage_code,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "CompanyProfile":
        if not data:
            return cls()
        def _lst(v: Any) -> List[str]:
            if isinstance(v, list):
                return [str(x) for x in v]
            if v:
                return [x.strip() for x in str(v).split(",") if x.strip()]
            return []
        return cls(
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            mission=str(data.get("mission", "")),
            target_agencies=_lst(data.get("target_agencies")),
            sectors=_lst(data.get("sectors")),
            past_performance=_lst(data.get("past_performance")),
            certifications=_lst(data.get("certifications")),
            team_size=int(data.get("team_size", 0) or 0),
            geographic_coverage=str(data.get("geographic_coverage", "")),
            contact_info=str(data.get("contact_info", "")),
            differentiators=_lst(data.get("differentiators")),
            client_list=_lst(data.get("client_list")),
            clearance_level=str(data.get("clearance_level", "")),
            gsa_schedules=_lst(data.get("gsa_schedules")),
            cage_code=str(data.get("cage_code", "")),
        )


@dataclass
class CapabilityStatement:
    """A structured capability statement — the transcript: "a one to two page
    PDF capability assessment. Government buyers expect this format." """
    company_name: str
    overview: str
    core_capabilities: List[str]
    differentiators: List[str]
    past_performance: List[str]
    certifications: List[str]
    geographic_coverage: str
    target_agencies: List[str]
    point_of_contact: str
    team_size: int = 0
    clearance_level: str = ""

    def render(self) -> str:
        lines = [f"CAPABILITY STATEMENT — {self.company_name or 'Vendor'}", ""]
        lines.append(self.overview or "Company overview.")
        if self.core_capabilities:
            lines += ["", "Core Capabilities:"]
            lines += [f"  - {c}" for c in self.core_capabilities]
        if self.differentiators:
            lines += ["", "Differentiators:"]
            lines += [f"  - {d}" for d in self.differentiators]
        if self.past_performance:
            lines += ["", "Past Performance:"]
            lines += [f"  - {p}" for p in self.past_performance]
        if self.certifications:
            lines += ["", "Certifications & Set-Asides:"]
            lines += [f"  - {c}" for c in self.certifications]
        lines += ["", f"Geographic Coverage: {self.geographic_coverage or 'Not specified'}",
                  f"Target Agencies: {', '.join(self.target_agencies) or 'Not specified'}",
                  f"Team Size: {self.team_size or 'Not specified'}"]
        if self.clearance_level:
            lines.append(f"Clearance Level: {self.clearance_level}")
        lines += ["", f"Point of Contact: {self.point_of_contact or 'Not specified'}"]
        return "\n".join(lines)

    def page_estimate(self) -> int:
        """Approx page count for a printed PDF (rough 250 words/page)."""
        words = len(self.render().split())
        return max(1, round(words / 250))


def generate_capability_statement(profile: CompanyProfile) -> CapabilityStatement:
    overview = (profile.description or profile.mission
                or f"{profile.name} provides services to government customers.")
    core = list(profile.sectors) or []
    if not core and profile.description:
        # Derive headline sectors from the code taxonomy as a curated suggestion.
        matcher = CodeMatcher()
        core = [s.code.title for s in matcher.recommend_codes(
            profile.description, limit=4, min_score=1)]
    return CapabilityStatement(
        company_name=profile.name,
        overview=overview,
        core_capabilities=core,
        differentiators=list(profile.differentiators),
        past_performance=list(profile.past_performance),
        certifications=list(profile.certifications),
        geographic_coverage=profile.geographic_coverage,
        target_agencies=list(profile.target_agencies),
        point_of_contact=profile.contact_info,
        team_size=profile.team_size,
        clearance_level=profile.clearance_level,
    )


# --------------------------------------------------------------------------- #
# Vendor profile optimization / grading
# --------------------------------------------------------------------------- #
@dataclass
class ProfileGrade:
    score: float  # 0..100
    working_well: List[str]
    missing: List[str]
    recommendations: List[str]

    @property
    def letter(self) -> str:
        if self.score >= 90:
            return "A"
        if self.score >= 80:
            return "B"
        if self.score >= 70:
            return "C"
        if self.score >= 60:
            return "D"
        return "F"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 1),
            "letter": self.letter,
            "working_well": list(self.working_well),
            "missing": list(self.missing),
            "recommendations": list(self.recommendations),
        }


# Fields a government-facing profile should carry (from the transcript: contact
# info, geographic coverage, clearance level, GSA schedules, differentiators,
# client list, credentials).
_PROFILE_CHECKS: Tuple[Tuple[str, str, str, float], ...] = (
    ("core_description", "description", "A descriptive company/mission statement", 20.0),
    ("target_agencies", "target_agencies", "Specific target agencies / sectors", 10.0),
    ("past_performance", "past_performance", "Past performance descriptions", 15.0),
    ("certifications", "certifications", "Certifications & set-aside status", 10.0),
    ("differentiators", "differentiators", "Specific differentiators", 10.0),
    ("client_list", "client_list", "A defined client list / strong credentials", 10.0),
    ("contact_info", "contact_info", "Point of contact information", 10.0),
    ("geographic_coverage", "geographic_coverage", "Geographic coverage", 10.0),
    ("gov_enhance", "gov_enhance", "Government-specific enhancements (clearance/GSA)", 5.0),
)


def _has(data: Dict[str, Any], key: str) -> bool:
    val = data.get(key)
    if isinstance(val, (list, tuple)):
        return len(val) > 0
    return bool(val)


def grade_profile(profile: CompanyProfile) -> ProfileGrade:
    """Grade how complete/competitive a vendor profile is (the transcript's
    "75 out of 100 ... missing critical information" profile coach)."""
    data = profile.to_dict()
    data["gov_enhance"] = bool(profile.clearance_level or profile.gsa_schedules
                               or profile.cage_code)
    score = 0.0
    working: List[str] = []
    missing: List[str] = []
    recommendations: List[str] = []
    for _key, dkey, label, weight in _PROFILE_CHECKS:
        if _has(data, dkey):
            score += weight
            working.append(label)
        else:
            missing.append(label)
            recommendations.append(f"Add: {label}")
    score = min(100.0, score)
    return ProfileGrade(score=round(score, 1), working_well=working,
                        missing=missing, recommendations=recommendations)


# --------------------------------------------------------------------------- #
# Solicitation / RFP analysis
# --------------------------------------------------------------------------- #
@dataclass
class Solicitation:
    """A parsed representation of a solicitation / RFP / RFI / IFB.

    ``source`` is the portal it came from (e.g. ``"sam.gov"`` / ``"bidnet"``).
    ``text`` is the raw body used for decoder heuristics.
    """
    id: str
    title: str
    agency: str
    source: str = ""
    text: str = ""
    response_deadline: str = ""
    set_aside: str = ""
    naics_codes: List[str] = field(default_factory=list)
    published: str = ""


_DEADLINE_RE = re.compile(
    r"(?:deadline|due|response\s+(?:due|date)|closing|closes)\s*\S{0,12}\s*"
    r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}|"
    r"[A-Z][a-z]{2,8}\s+\d{1,2},?\s+\d{4})",
    re.IGNORECASE,
)

_SET_ASIDE_KEYWORDS = (
    "small business", "veteran-owned", "service-disabled", "woman-owned",
    "hubzone", "8(a)", "minority-owned", "disadvantaged",
)

# Heuristics for deciding whether to pursue an opportunity (grounded in the
# "Agency models are DEAD" ROI/fit critique: a solution only matters if the
# company genuinely fits and the effort can pay off).
_BID_POSITIVES = (
    "sources sought", "request for information", "rfi", "market research",
    "capability statement",
)
_BID_NEGATIVES = (
    "requires clearance", "top secret", "certified", "bond required",
    "set aside", "small business",
)


@dataclass
class SolicitationAnalysis:
    id: str
    title: str
    agency: str
    deadline: str
    set_aside: Optional[str]
    naics_codes: List[str]
    requirements: List[str]
    eligibility: List[str]
    do_bid_signals: List[str]
    donot_bid_heuristics: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "title": self.title, "agency": self.agency,
            "deadline": self.deadline, "set_aside": self.set_aside,
            "naics_codes": list(self.naics_codes),
            "requirements": list(self.requirements),
            "eligibility": list(self.eligibility),
            "do_bid_signals": list(self.do_bid_signals),
            "donot_bid_heuristics": list(self.donot_bid_heuristics),
        }


def _extract_requirements(text: str) -> List[str]:
    reqs: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("-", "*", "•")) and len(stripped) > 3:
            reqs.append(stripped.lstrip("- *•").strip())
    # Requirement-prefixed statements
    for m in re.finditer(r"(?:requirement|scope|deliverable)[s]?[:\-]?\s*(.+)",
                         text, re.IGNORECASE):
        val = m.group(1).strip()
        if val and len(val) > 3 and val not in reqs:
            reqs.append(val)
    return reqs[:20]


def _detect_set_aside(text: str, existing: str) -> Optional[str]:
    low = text.lower()
    for kw in _SET_ASIDE_KEYWORDS:
        if kw in low:
            return kw
    return existing.strip() or None


def analyze_solicitation(sol: Solicitation) -> SolicitationAnalysis:
    """'Solicitation decoder' — break a solicitation down into requirements,
    deadline, eligibility and do/don't bid signals."""
    deadline = sol.response_deadline
    if not deadline:
        m = _DEADLINE_RE.search(sol.text)
        if m:
            deadline = m.group(1)

    set_aside = _detect_set_aside(sol.text, sol.set_aside)

    requirements = _extract_requirements(sol.text)
    eligibility: List[str] = []
    low = sol.text.lower()
    for kw in _SET_ASIDE_KEYWORDS:
        if kw in low:
            eligibility.append(f"Eligible/limited to: {kw}")
    if sol.naics_codes:
        eligibility.append("NAICS restriction: " + ", ".join(sol.naics_codes))
    if set_aside and set_aside not in [e for e in eligibility]:
        eligibility.append(f"Set-aside: {set_aside}")

    do_bid_signals = [p for p in _BID_POSITIVES if p in low]
    donot = [n for n in _BID_NEGATIVES if n in low]

    return SolicitationAnalysis(
        id=sol.id, title=sol.title, agency=sol.agency, deadline=deadline,
        set_aside=set_aside, naics_codes=list(sol.naics_codes),
        requirements=requirements, eligibility=eligibility,
        do_bid_signals=do_bid_signals, donot_bid_heuristics=donot,
    )


# --------------------------------------------------------------------------- #
# Opportunity fit / ROI assessment (bid / no-bid)
# --------------------------------------------------------------------------- #
@dataclass
class OpportunityAssessment:
    """Scored bid/no-bid reasoning — brings the 'Agency models are DEAD'
    ROI/fit critique to the procurement decision: capability match is not
    enough; you also need past performance, capacity and a realistic ROI."""

    capability_match: float    # 0..1 — does the company actually do this?
    past_performance: float    # 0..1 — has it done similar work before?
    capacity: float            # 0..1 — does it have the team/capacity to deliver?
    roi: float                 # 0..1 — is the effort worth the expected value?
    overall: float             # 0..1 weighted composite
    verdict: str               # "bid" | "no_bid" | "deliberate"
    rationale: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_match": round(self.capability_match, 2),
            "past_performance": round(self.past_performance, 2),
            "capacity": round(self.capacity, 2),
            "roi": round(self.roi, 2),
            "overall": round(self.overall, 2),
            "verdict": self.verdict,
            "rationale": list(self.rationale),
        }


def assess_opportunity(profile: CompanyProfile,
                       solicitation: Solicitation,
                       weights: Optional[Dict[str, float]] = None,
                       capacity: float = 0.5) -> OpportunityAssessment:
    """Decide whether the opportunity is a genuine fit for THIS company.

    Capability match is estimated by code-taxonomy keyword overlap between the
    company description/sectors and the solicitation text. Past performance
    counts whether the profile lists relevant, non-empty performance for the
    same domain. Capacity is passed in (defaults to a neutral 0.5).
    """
    w = weights or {}
    w_cap = float(w.get("capability_match", 0.45))
    w_perf = float(w.get("past_performance", 0.20))
    w_capy = float(w.get("capacity", 0.15))
    w_roi = float(w.get("roi", 0.20))

    sol_text = f"{solicitation.title} {solicitation.text}".lower()
    company_text = " ".join([profile.description, profile.mission,
                             " ".join(profile.sectors)]).lower()
    sol_tokens = tokenize(sol_text)
    company_tokens = tokenize(company_text)

    # Capability: fraction of company capability keywords present in the
    # solicitation, averaged with code-taxonomy alignment.
    profile_kw = set(company_tokens)
    if profile_kw:
        overlap_hit = sum(1 for tok in sol_tokens if tok in profile_kw)
        cap_signal = min(1.0, overlap_hit / max(1, len(profile_kw)))
    else:
        cap_signal = 0.0
    matcher = CodeMatcher()
    company_codes = {s.code.id for s in matcher.score_codes(company_text)
                     if s.score > 0}
    sol_codes = {s.code.id for s in matcher.score_codes(sol_text) if s.score > 0}
    code_align = 0.0
    if sol_codes:
        code_align = len(company_codes & sol_codes) / len(sol_codes)
    capability = round(min(1.0, 0.5 * cap_signal + 0.5 * code_align), 3)

    # Past performance: non-empty and topically relevant.
    perf_entries = list(profile.past_performance)
    past_performance = 0.0
    if perf_entries:
        perf_hits = sum(1 for p in perf_entries
                        if _domain_overlap(str(p), sol_text))
        past_performance = round(perf_hits / len(perf_entries), 3)

    capacity = max(0.0, min(1.0, float(capacity)))

    # ROI: positive when fit is high AND the opportunity looks structured to
    # minimize wasted effort (sources-sought / RFI are low-effort, high-info).
    low_effort = any(s in sol_text for s in ("sources sought", "request for information", "rfi"))
    roi = round(min(1.0, 0.5 * capability + 0.3 * past_performance
                    + (0.2 if low_effort else 0.0)), 3)

    overall = round(w_cap * capability + w_perf * past_performance
                    + w_capy * capacity + w_roi * roi, 3)

    rationale: List[str] = []
    if capability < 0.4:
        rationale.append("Capability match is low — the company may not actually do this work.")
    else:
        rationale.append("Capability matches the solicitation domain.")
    if past_performance < 0.5:
        rationale.append("Limited relevant past performance — hard to win without it.")
    else:
        rationale.append("Relevant past performance supports the bid.")
    if capacity < 0.4:
        rationale.append("Team capacity may be too small to deliver.")
    if roi < 0.4:
        rationale.append("Expected return does not justify the proposal effort.")
    elif roi >= 0.7:
        rationale.append("High expected value per unit of proposal effort.")

    if overall >= 0.7:
        verdict = "bid"
    elif overall >= 0.45:
        verdict = "deliberate"
    else:
        verdict = "no_bid"

    return OpportunityAssessment(
        capability_match=capability,
        past_performance=past_performance,
        capacity=capacity,
        roi=roi,
        overall=overall,
        verdict=verdict,
        rationale=rationale,
    )


def _domain_overlap(perf_text: str, sol_text: str) -> bool:
    perf_tokens = set(tokenize(perf_text))
    sol_tokens = set(tokenize(sol_text))
    if not perf_tokens:
        return False
    shared = perf_tokens & sol_tokens
    # A meaningful share of the performance's signature terms also appear in
    # the solicitation.
    return (len(shared) / len(perf_tokens)) >= 0.10


# --------------------------------------------------------------------------- #
# Top-level convenience facade used by the module wrapper
# --------------------------------------------------------------------------- #
def company_info_to_guidance(profile: CompanyProfile,
                             top_codes: int = 5) -> Dict[str, Any]:
    """The "Here is my company's info. How would I apply and what codes should I
    use?" flow — returns recommended codes plus a generated capability statement
    plus a profile grade."""
    matcher = CodeMatcher()
    codes = [
        {"id": s.code.id, "family": s.code.family, "title": s.code.title,
         "score": s.score, "matched": list(s.matched)}
        for s in matcher.recommend_codes(profile.description or profile.mission,
                                         limit=top_codes, min_score=1)
    ]
    statement = generate_capability_statement(profile)
    grade = grade_profile(profile)
    return {
        "recommended_codes": codes,
        "capability_statement": statement.render(),
        "capability_pages": statement.page_estimate(),
        "profile_grade": grade.to_dict(),
    }
