"""AI Education Guardrails — responsible & effective AI use in academics/edtech.

A pure, network-free heuristic engine distilled directly from four pulled
JE Van Clief transcripts about AI in education:

  * czIBNYeiAuw "AI in Academics: How NOT to Use It" — learning how NOT to use
    AI is the most important skill; education = giving resources & guidance to
    reach full potential; AI as chisel (enhance) vs crutch (replace); the THINK
    process (Thoughts->Thematics->Integration->Navigational Nemesis->Amplifica-
    tion); blockers (AI overwhelm, tool deficiency, community void); the Mhlanga
    ethical checklist (privacy, fairness, non-discrimination, transparency).
  * iY_j0VKimQI "AI Cheating in Class? Redefining What 'Challenging' Means" —
    if AI makes your class too easy, your class is too easy; raise the bar;
    redesign assessments to grade the *critique/prompts*, not the AI product;
    detect AI use via generic, textureless writing.
  * THQH6Uc6PNU "Perils of AI and Ed-Tech" — perils of grading the product
    instead of the process; tools missing assessment goals erode trust; the
    top-down make-the-AI-write-it/grade-the-critique method and structured
    dialogue; "you can't cheat what you don't know"; editable/deletable data
    governance; "it is not the solution, it is a tool to find the solutions".
  * wpM-c--FE04 "Artificial Minds, Real Ideas Ep.1: Who Controls EdTech?" —
    mini-publics (diverse deliberation: teachers, support staff, students,
    AI-ethics experts); four-phase process; process AND outcome metrics; bottom-
    up vs top-down control; tools not built with diverse learners widen the gap.

Export surface (pure logic — no I/O, no ML):
  * UsagePolicyClassifier       — labels a use-case MISUSE / ASSISTIVE / LEGITIMATE
                                  with matched signals + rationale.
  * AssignmentRobustnessChecker — does an assessment hold up against AI / test
                                  durable skills? robust / at_risk / fragile.
  * detect_submission           — misuse-detection heuristics (AI-texture, disclosure).
  * EdTechGovernanceChecker     — who controls the tool? inclusive vs top-down.
  * AIEducationGuardrailsEngine — facade engine composing all of the above.

Version: 1.0.0
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

__version__ = "1.0.0"


class UsageClass(str, Enum):
    MISUSE = "misuse"
    ASSISTIVE = "assistive"
    LEGITIMATE = "legitimate"
    UNDETERMINED = "undetermined"

class Verdict(str, Enum):
    ROBUST = "robust"
    AT_RISK = "at_risk"
    FRAGILE = "fragile"

class GovernanceVerdict(str, Enum):
    INCLUSIVE = "inclusive"
    PARTIAL = "partial"
    TOP_DOWN = "top_down"

class ThinkStage(str, Enum):
    """Stages of the THINK writing process from the 'How NOT to Use It' talk."""
    THOUGHTS = "thoughts"                 # dump raw thoughts / transcription
    THEMATICS = "thematics"               # organize those thoughts into themes/structure
    INTEGRATION = "integration"           # bring in other fields/data/research
    NEMESIS = "navigational_nemesis"      # adversarial debate / disagreement
    AMPLIFICATION = "amplification"       # broaden perspective, check bias, add context


_MISUSE_SIGNALS: Dict[str, List[str]] = {
    "direct_submission": [
        "submit directly", "turn in", "hand in", "submit as my own",
        "submit it as my own", "as my own work", "paste the output", "paste the ai's",
        "copy the output", "output directly", "use as my own work", "claim as my own",
        "submit the ai's", "turn in the ai's",
    ],
    "bypass_final_product": [
        "write the essay for me", "write the paper for me", "write my essay",
        "writes my essay", "writes the essay", "essay for me", "paper for me",
        "do my assignment", "do the work for me", "do my work", "do the work",
        "complete it for me", "do it for me", "the whole thing for me",
        "instead of doing it myself", "skip the work",
    ],
    "no_learning": [
        "just give me the answer", "get the answer", "just the answer",
        "give me the answer", "tell me the answer", "render the problem",
        "solve it for me", "give me the solution", "cheat what you don't know",
        "replace my thinking", "remove the thinking",
    ],
    "no_disclosure": [
        "without citing", "no citation", "don't cite", "without saying",
        "without telling", "undisclosed", "hide that i used", "without disclosing",
        "as if i wrote it", "pretend i wrote",
    ],
    "explicit_cheating": ["cheat", "cheating", "plagiar", "plagiarism", "fraud",
                          "pass off", "deceive", "deception"],
}

# Signals for ASSISTIVE/LEGITIMATE use (chisel not crutch) from THINK, the
# top-down critique method, structured dialogue, and the ethical checklist.
_ASSISTIVE_SIGNALS: Dict[str, List[str]] = {
    "organize_thoughts": [
        "organize my thoughts", "structure my thoughts", "organize this", "structure this",
        "outline", "brainstorm", "dump my thoughts", "thematics", "thematic",
    ],
    "draft_and_revise": [
        "draft", "edit", "revise", "revision", "rewrite", "revising", "proofread",
        "improve my draft", "format", "grammar",
    ],
    "feedback_critique": [
        "feedback", "critique", "criticize", "review this", "give me feedback",
        "check my work", "grade the critique",
    ],
    "dialogue_debate": [
        "debate", "nemesis", "disagree with me", "argue with me", "argue against",
        "dialogue", "discuss", "structured dialogue", "adversarial",
    ],
    "learn_understand": [
        "explain this concept", "explain it to me", "help me learn", "help me understand",
        "simplify", "teach me", "walk me through", "learn",
    ],
    "disclosure_citation": [
        "cite", "citation", "credit", "disclose", "disclosure", "acknowledge",
        "with citation", "with credit", "sources", "reference",
    ],
    "amplify_perspective": [
        "amplify", "other perspectives", "what am i missing", "check my bias",
        "bias", "other view", "better context",
    ],
    "accompanying_tool_control": [
        "vote on the data", "delete the data", "same tool everyone", "equitable access",
        "equal access", "free tool", "available to all",
    ],
}

def _matches(text: str, phrases: List[str]) -> List[str]:
    low = text.lower()
    return [p for p in phrases if p in low]

class UsagePolicyClassifier:
    """Labels an academic AI use-case as misuse vs assistive/legitimate.

    The transcripts insist the *problem is not the tool, it is the mindset*: the
    same engine is a chisel or a crutch depending on whether it replaces durable
    thinking or amplifies it, and whether disclosure/equity controls are honored.
    """

    def __init__(self) -> None:
        self.misuse_signals = {k: list(v) for k, v in _MISUSE_SIGNALS.items()}
        self.assistive_signals = {k: list(v) for k, v in _ASSISTIVE_SIGNALS.items()}

    def classify(self, usage: str) -> "UsageVerdict":
        """Classify a free-text use-case -> UsageVerdict (label, signals, rationale)."""
        text = (usage or "").strip()
        if not text:
            return UsageVerdict(UsageClass.UNDETERMINED, 0.0, [], [],
                                "No use-case described to evaluate.")

        misuse_hits: List[str] = []
        assist_hits: List[str] = []
        for cat, phrases in self.misuse_signals.items():
            for p in _matches(text, phrases):
                misuse_hits.append(f"{cat}:{p}")
        for cat, phrases in self.assistive_signals.items():
            for p in _matches(text, phrases):
                assist_hits.append(f"{cat}:{p}")

        decisive_misuse = {
            "direct_submission", "bypass_final_product", "no_learning", "no_disclosure",
        }
        decisive_assist = {"disclosure_citation", "feedback_critique", "dialogue_debate",
                           "organize_thoughts", "learn_understand"}

        mis_cats = {h.split(":")[0] for h in misuse_hits}
        ast_cats = {h.split(":")[0] for h in assist_hits}
        strength = round(min(1.0, 0.45 + 0.12 * max(0, len(misuse_hits) - 1)), 2)

        if mis_cats & decisive_misuse:
            return self._verdict(UsageClass.MISUSE, strength, misuse_hits, assist_hits,
                                 self._rationale_misuse(mis_cats, ast_cats))
        if assist_hits and not misuse_hits:
            label = UsageClass.ASSISTIVE if ast_cats & decisive_assist else UsageClass.LEGITIMATE
            conf = round(max(0.55, 0.6 + 0.06 * (len(assist_hits) - 1)), 2)
            return self._verdict(label, conf, misuse_hits, assist_hits,
                                 self._rationale_assistive(ast_cats))
        if misuse_hits:
            return self._verdict(UsageClass.MISUSE, strength, misuse_hits, assist_hits,
                                 self._rationale_misuse(mis_cats, ast_cats))
        if assist_hits:
            return self._verdict(UsageClass.LEGITIMATE, 0.55, misuse_hits, assist_hits,
                                 "Strongly assistive intent; treat as a chisel, not a crutch.")
        return UsageVerdict(UsageClass.UNDETERMINED, 0.2, [], [],
                            "Not enough signal; policy should require disclosure + equity check.")

    @staticmethod
    def _verdict(label: UsageClass, conf: float, mis: List[str], ast: List[str],
                 reason: str) -> "UsageVerdict":
        return UsageVerdict(label, conf, mis, ast, reason)

    @staticmethod
    def _rationale_misuse(mis_cats, ast_cats) -> str:
        parts = ["Hands over or bypasses the durable skill the assignment builds."]
        if mis_cats & {"direct_submission", "bypass_final_product"}:
            parts.append("The AI output is being submitted as the graded product "
                         "rather than worked through.")
        if "no_learning" in mis_cats:
            parts.append("It short-circuits learning — you cannot 'cheat what you"
                         " don't know' without it showing at assessment time.")
        if "no_disclosure" in mis_cats:
            parts.append("No disclosure/citation where the academic-integrity "
                         "policy would require it.")
        if "explicit_cheating" in mis_cats:
            parts.append("The intent is explicitly deceptive.")
        return " ".join(parts)

    @staticmethod
    def _rationale_assistive(ast_cats) -> str:
        parts = ["Classified as assistive/legitimate: the AI is used as a chisel "
                 "that amplifies the student's own thinking."]
        if "organize_thoughts" in ast_cats:
            parts.append("It organizes drafts of the student's own thoughts (THINK).")
        if "feedback_critique" in ast_cats or "dialogue_debate" in ast_cats:
            parts.append("It is used for critique, revision or adversarial dialogue "
                         "— the student still does the judgment.")
        if "learn_understand" in ast_cats:
            parts.append("It is used to understand rather than to replace understanding.")
        if "disclosure_citation" in ast_cats:
            parts.append("Transparency/disclosure is honored.")
        return " ".join(parts)

@dataclass
class UsageVerdict:
    label: UsageClass
    confidence: float
    misuse_signals: List[str] = field(default_factory=list)
    assistive_signals: List[str] = field(default_factory=list)
    rationale: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label.value,
            "confidence": self.confidence,
            "misuse_signals": self.misuse_signals,
            "assistive_signals": self.assistive_signals,
            "rationale": self.rationale,
        }


@dataclass
class AssignmentDesign:
    description: str = ""
    graded_on: Optional[str] = None   # free text: what exactly is graded (product?, process?)
    format: Optional[str] = None      # e.g. 'essay', 'exam', 'oral', 'project'

# Features that make an assessment robust to AI — each grounded in a
# transcript recommendation. `weight` encodes how strongly a feature makes the
# assessment AI-proof; the top-down method (grade the critique + prompt + process)
# is the transcripts' primary recommended redesign and therefore weighted highest.
_ROBUST_FEATURES: Dict[str, Dict[str, Any]] = {
    "process_grading": {
        "phrases": ["grade the process", "graded on process", "assess the process",
                    "grade the critique", "graded on the critique", "rubric on process",
                    "assessed on process", "not the product", "not just the essay",
                    "assessed on", "grade the prompts", "graded on the prompts",
                    "assess the prompts"],
        "weight": 0.25,
        "note": "grades the process rather than the AI-generable product",
    },
    "critique_revision": {
        "phrases": ["critique the ai", "critique the essay", "critique the output",
                    "revise the ai", "rewrite the ai", "rewrite the essay", "edit the ai",
                    "make three essays", "compare the essays", "find what could be better",
                    "improve the draft", "revise", "critique"],
        "weight": 0.20,
        "note": "students critique/revise AI output — durable editorial judgment",
    },
    "prompt_assessment": {
        "phrases": ["assess the prompt", "assess the prompts", "grade the prompt",
                    "grade the prompts", "the prompts given", "prompt quality",
                    "asses the prompt", "asses the prompts"],
        "weight": 0.20,
        "note": "explicitly grades the quality of prompts/dialogue steering",
    },
    "structured_dialogue": {
        "phrases": ["structured dialogue", "dialogue", "discuss", "discussion",
                    "conversation with the ai", "talk to the ai", "speak to the ai",
                    "chat log", "interview", "guided discussion", "take them through"],
        "weight": 0.15,
        "note": "assesses the student's line of questioning/critical thought",
    },
    "individual_voice": {
        "phrases": ["individual tone", "personal perspective", "your own perspective",
                    "own voice", "your voice", "personal experience", "in your own words",
                    "individual style", "your own style", "aligned with what you would"],
        "weight": 0.12,
        "note": "requires a personal, non-generic voice AI cannot fabricate well",
    },
    "oral_interaction": {
        "phrases": ["oral", "presentation", "present it", "speak to", "spoken",
                    "explain it out loud", "defend", "talk about it", "in person",
                    "verbal"],
        "weight": 0.12,
        "note": "interactive/spoken components — 'you can't cheat what you don't know'",
    },
    "durable_knowledge": {
        "phrases": ["critical think", "critical thought", "understanding",
                    "durable", "expertise", "defend your", "explain your reasoning",
                    "reasoning", "judgment", "high-level structure"],
        "weight": 0.12,
        "note": "tests durable skills/knowledge rather than a one-shot product",
    },
    "live_demonstration": {
        "phrases": ["timed", "in class", "in-class", "closed book", "proctored",
                    "hands-on", "live demo", "demonstrate"],
        "weight": 0.12,
        "note": "live/timed delivery where leveraging a tool is constrained",
    },
}

_RISK_SIGNALS: Dict[str, List[str]] = {
    "pure_product": [
        "grade the essay", "graded on the essay", "grade the paper", "graded on the paper",
        "grade the final product", "grade the output", "graded on the output",
        "grade what is submitted", "grade the submission",
    ],
    "generic_task": [
        "write an essay about", "write a paper on", "a 5 paragraph essay", "summary of",
        "book report", "define", "list the causes", "generic", "standard essay",
        "five-paragraph",
    ],
    "easy_to_generate": [
        "essay", "report", "analysis of a topic", "summarize", "write a response",
    ],
}

class AssignmentRobustnessChecker:
    """Does an assessment hold up against AI / test durable skills?

    ROBUST grades process/critique/dialogue; AT_RISK has some robust features but
    still grades a product; FRAGILE grades a generic AI-generable product.
    """

    def __init__(self, threshold_robust: float = 0.6,
                 threshold_at_risk: float = 0.3) -> None:
        self.threshold_robust = threshold_robust
        self.threshold_at_risk = threshold_at_risk

    def assess(self, design: AssignmentDesign) -> "AssignmentAssessment":
        text = (design.description or "").lower()
        graded = (design.graded_on or "").lower()
        haystack = f"{text} {graded} {design.format or ''}".lower()

        matched: List[str] = []
        notes: List[str] = []
        weight_sum = 0.0
        for feat, spec in _ROBUST_FEATURES.items():
            hits = [p for p in spec["phrases"] if p in haystack]
            if hits:
                matched.append(f"{feat}:{hits[0]}")
                notes.append(spec["note"])
                weight_sum += float(spec.get("weight", 0.1))

        risks: List[str] = []
        for cat, phrases in _RISK_SIGNALS.items():
            for p in phrases:
                if p in haystack:
                    risks.append(f"{cat}:{p}")

        risk_cats = {r.split(":")[0] for r in risks}
        feat_cats = {m.split(":")[0] for m in matched}
        process_cats = {"process_grading", "critique_revision", "prompt_assessment",
                        "structured_dialogue"}
        if "pure_product" in risk_cats:
            penalty = 0.5
        elif "easy_to_generate" in risk_cats and not (feat_cats & process_cats):
            penalty = 0.25
        else:
            penalty = 0.0
        score = round(max(0.0, min(1.0, weight_sum - penalty)), 2)

        if score >= self.threshold_robust:
            verdict = Verdict.ROBUST
        elif score >= self.threshold_at_risk:
            verdict = Verdict.AT_RISK
        else:
            verdict = Verdict.FRAGILE

        recommendations = self._recommendations(verdict, matched, risks)
        return AssignmentAssessment(verdict, score, matched, risks, notes,
                                    recommendations)

    @staticmethod
    def _recommendations(verdict: Verdict, matched: List[str],
                         risks: List[str]) -> List[str]:
        recs: List[str] = []
        cats = {m.split(":")[0] for m in matched}
        rcats = {r.split(":")[0] for r in risks}
        if "critique_revision" not in cats:
            recs.append("Have students make the AI produce the artifact, then grade "
                        "their critique/revision of it rather than the artifact.")
        if "prompt_assessment" not in cats and "structured_dialogue" not in cats:
            recs.append("Assess the prompts or the structured dialogue the student "
                        "runs, not (only) the final output.")
        if "individual_voice" not in cats:
            recs.append("Anchor the task in the student's own perspective/voice "
                        "and lived examples so a generic model output cannot satisfy it.")
        if "oral_interaction" not in cats and "live_demonstration" not in cats:
            recs.append("Add a spoken/defense or timed component — you can't cheat "
                        "what you don't know when you have to explain it.")
        if "pure_product" in rcats:
            recs.append("Stop grading the finished text directly; grade the process "
                        "(critique, prompts, revision) the transcripts recommend.")
        if "generic_task" in rcats:
            recs.append("Replace generic prompts with higher-level, individualized "
                        "tasks ('raise the bar' rather than ban the tool).")
        if not recs:
            recs.append("Assessment already robust: it evaluates durable skills and "
                        "the process rather than an AI-generable product.")
        return recs

@dataclass
class AssignmentAssessment:
    verdict: Verdict
    score: float
    robust_features: List[str] = field(default_factory=list)
    risk_signals: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "score": self.score,
            "robust_features": self.robust_features,
            "risk_signals": self.risk_signals,
            "notes": self.notes,
            "recommendations": self.recommendations,
        }

def build_assignment(description: str, graded_on: Optional[str] = None,
                     format: Optional[str] = None) -> AssignmentDesign:
    return AssignmentDesign(description=description, graded_on=graded_on, format=format)


_GENERIC_PHRASES = [
    "in today's world", "in today's society", "it is important to note that",
    "furthermore", "moreover", "in conclusion", "in summary", "to sum up",
    "it should be noted that", "in the modern era", "plays a crucial role",
    "plays a pivotal role", "is of paramount importance", "delve into",
    "in a nutshell", "a double-edged sword", "the ever-evolving",
    "in this essay", "ultimately", "overall,",
]

_PERSONAL_STANCE = [
    "i believe", "i think", "in my experience", "i found", "i noticed",
    "in my view", "my own", "i argue", "i would", "my perspective",
    "i remember", "from my",
]

@dataclass
class MisuseReport:
    ai_texture_risk: float            # 0..1 generic/synthetic signal
    generic_markers: List[str]
    personal_stance_markers: List[str]
    disclosed: bool                   # did the author disclose AI assistance?
    has_citation: bool
    misuses_disclosure: bool          # no disclosure where expected + high ai texture
    flags: List[str]
    overall_risk: float

    @property
    def likely_ai_generated(self) -> bool:
        return self.overall_risk >= 0.6

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ai_texture_risk": self.ai_texture_risk,
            "generic_markers": self.generic_markers,
            "personal_stance_markers": self.personal_stance_markers,
            "disclosed": self.disclosed,
            "has_citation": self.has_citation,
            "misuses_disclosure": self.misuses_disclosure,
            "flags": self.flags,
            "overall_risk": self.overall_risk,
            "likely_ai_generated": self.likely_ai_generated,
        }

def detect_submission(text: str, disclosed: bool = False) -> MisuseReport:
    """Run misuse-detection heuristics on a submission.

    Tells: generic, textureless model writing ("a generic writer is what most AI
    output looks like") vs individual voice. Heuristic only — flags signals for
    an educator to review, never proof.
    """
    low = (text or "").lower()
    generic = [p for p in _GENERIC_PHRASES if p in low]
    stance = [p for p in _PERSONAL_STANCE if p in low]

    connector_tokens = sum(len(p.split()) for p in generic)
    word_count = max(1, len(re.findall(r"\b\w+\b", low)))
    generic_density = min(1.0, connector_tokens / max(1, word_count))

    texture = round(min(1.0, generic_density * 3.0 + (0.25 if len(generic) >= 4 else 0.0)
                        + (0.0 if stance else 0.2)), 2)

    has_citation = bool(re.search(r"\([^)]*\d{4}\)|\[\d+\]|references|works cited|bibliography|doi",
                                  (text or "").lower()))

    flags: List[str] = []
    if generic and len(generic) >= 4:
        flags.append("high_generic_texture: heavy formulaic connector language")
    if not stance:
        flags.append("no_personal_stance: little individual voice, hard to verify as the author's own")
    if not disclosed and texture >= 0.5 and not has_citation:
        flags.append("no_disclosure_with_model_texture: assistance not disclosed where expected")

    misuses_disclosure = (not disclosed) and texture >= 0.55
    overall = texture
    if misuses_disclosure:
        overall += 0.25
    elif disclosed:
        overall -= 0.15
    overall = round(max(0.0, min(1.0, overall)), 2)

    return MisuseReport(
        ai_texture_risk=texture,
        generic_markers=generic,
        personal_stance_markers=stance,
        disclosed=disclosed,
        has_citation=has_citation,
        misuses_disclosure=misuses_disclosure,
        flags=flags,
        overall_risk=overall,
    )


@dataclass
class GovernanceModel:
    stakeholder_groups: List[str] = field(default_factory=list)  # teachers, students, support, ethics
    has_deliberation: bool = False           # structured deliberation (mini-public / dialogue)
    four_phase: int = 0                      # how many of the 4 phases are present (0..4)
    process_metrics: bool = False            # participation, diversity, discussion depth
    outcome_metrics: bool = False            # recommendations actually adopted/used
    data_controls: bool = False              # vote on data / delete data
    tool_choice: bool = False                # choice among providers/ethics/energy
    safeguards: bool = False                 # protections against dominant voices
    vendor_profit_first: bool = False        # top-down, optimized-for-profit, low-results

class EdTechGovernanceChecker:
    """Scores whether edtech control is inclusive vs top-down vendor control.

    (wpM-c--FE04 + THQH6Uc6PNU) tools not designed with diverse learners widen the
    gap; the remedy is bottom-up mini-public governance (diverse stakeholders, real
    deliberation, process AND outcome metrics, data controls, safeguards) vs
    top-down "ride the wave" vendor control.
    """

    def assess(self, model: GovernanceModel) -> "GovernanceAssessment":
        score = 0.0
        notes: List[str] = []

        if len(model.stakeholder_groups) >= 3:
            score += 0.2
            notes.append("Diverse stakeholder representation (teachers + students + "
                         "support/ethics) aligns with the mini-public model.")
        elif model.stakeholder_groups:
            score += 0.08
            notes.append("Some stakeholders represented, but the mini-public ideal "
                         "needs teachers, students, support staff and ethics experts.")

        if model.has_deliberation:
            score += 0.2
            notes.append("Structured deliberation present (depth beyond surveys).")
        if model.four_phase >= 3:
            score += 0.15
            notes.append("Most of the 4-phase governance cycle is implemented.")
        elif model.four_phase > 0:
            score += 0.06
            notes.append("Only part of the 4-phase cycle present.")

        if model.process_metrics:
            score += 0.1
            notes.append("Process metrics tracked (participation, diversity, depth).")
        if model.outcome_metrics:
            score += 0.1
            notes.append("Outcome metrics tracked — recommendations actually adopted, "
                         "not just 'did we ask'.")
        if model.data_controls:
            score += 0.1
            notes.append("Users can govern/delete the data collected.")
        if model.tool_choice:
            score += 0.05
            notes.append("Choice of tool/provider honors ethics & access.")

        if model.vendor_profit_first:
            score -= 0.25
            notes.append("Vendor-profit-first control risks obscene prices for low "
                         "results and waning trust; no community voice.")

        score = round(max(0.0, min(1.0, score)), 2)
        if score >= 0.65:
            verdict = GovernanceVerdict.INCLUSIVE
        elif score >= 0.35:
            verdict = GovernanceVerdict.PARTIAL
        else:
            verdict = GovernanceVerdict.TOP_DOWN

        gaps = []
        if not model.has_deliberation:
            gaps.append("Add a structured dialogue / mini-public deliberation process.")
        if len(model.stakeholder_groups) < 3:
            gaps.append("Broaden representation to students, support staff and AI-ethics experts.")
        if not model.process_metrics:
            gaps.append("Track process metrics (participation, diversity, discussion depth).")
        if not model.outcome_metrics:
            gaps.append("Track outcome metrics — are recommendations actually used?")
        if not model.safeguards:
            gaps.append("Add safeguards so dominant voices don't silence challenging perspectives.")
        if not model.data_controls:
            gaps.append("Give users the ability to see/vote on and delete their data.")

        return GovernanceAssessment(verdict, score, notes, gaps,
                                    "inclusive" if verdict == GovernanceVerdict.INCLUSIVE else
                                    ("partial" if verdict == GovernanceVerdict.PARTIAL else "top-down"))

@dataclass
class GovernanceAssessment:
    verdict: GovernanceVerdict
    score: float
    notes: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    control_mode: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "score": self.score,
            "notes": self.notes,
            "gaps": self.gaps,
            "control_mode": self.control_mode,
        }


_THINK_PHRASES = {
    ThinkStage.THOUGHTS: ["dump", "thoughts", "talk and explain", "transcription",
                          "get it out of your head", "brainstorm", "raw"],
    ThinkStage.THEMATICS: ["organize", "organiz", "structure", "thematics", "thematic",
                           "outline", "formalize", "connections"],
    ThinkStage.INTEGRATION: ["integrate", "integrat", "data", "other fields", "research",
                             "bolster", "consensus", "studies", "dissect"],
    ThinkStage.NEMESIS: ["debate", "disagree", "nemesis", "argue", "enemy",
                         "adversarial", "against", "echo chamber"],
    ThinkStage.AMPLIFICATION: ["amplify", "amplification", "other perspectives",
                               "bias", "better context", "what am i missing", "explain a concept"],
}

class ThinkFramework:
    """Classifies an action into THINK process stages (thoughts->thematics->...->amplification)."""

    def stages_used(self, description: str) -> List[ThinkStage]:
        low = (description or "").lower()
        used = [s for s, phrases in _THINK_PHRASES.items() if any(p in low for p in phrases)]
        return used

    def is_process_oriented(self, description: str) -> bool:
        """True if the described use resembles the THINK (process) workflow."""
        return len(self.stages_used(description)) >= 2


class AIEducationGuardrailsEngine:
    """Facade composing every guardrail check into one pure-logic engine."""
    def __init__(self, policy_default: str = "disclosure-based",
                 robust_threshold: float = 0.6, at_risk_threshold: float = 0.3) -> None:
        self.policy_default = policy_default
        self.classifier = UsagePolicyClassifier()
        self.assignment_checker = AssignmentRobustnessChecker(robust_threshold,
                                                              at_risk_threshold)
        self.governance_checker = EdTechGovernanceChecker()
        self.think = ThinkFramework()

    def classify_usage(self, usage: str) -> UsageVerdict:
        return self.classifier.classify(usage)

    def assess_assignment(self, design: AssignmentDesign) -> AssignmentAssessment:
        return self.assignment_checker.assess(design)

    def detect(self, text: str, disclosed: bool = False) -> MisuseReport:
        return detect_submission(text, disclosed=disclosed)

    def assess_governance(self, model: GovernanceModel) -> GovernanceAssessment:
        return self.governance_checker.assess(model)

    def think_stages(self, description: str) -> List[ThinkStage]:
        return self.think.stages_used(description)

__all__ = [
    "UsageClass", "Verdict", "GovernanceVerdict", "ThinkStage",
    "UsagePolicyClassifier", "UsageVerdict",
    "AssignmentDesign", "AssignmentRobustnessChecker", "AssignmentAssessment",
    "build_assignment",
    "MisuseReport", "detect_submission",
    "GovernanceModel", "EdTechGovernanceChecker", "GovernanceAssessment",
    "ThinkFramework", "AIEducationGuardrailsEngine",
    "__version__",
]
