# Module: `research_verification`

- Category: Legacy Core · priority 45
- Version: 1.0.0
- Purpose: Research & Verification OS — Enterprise Platform Kernel Module v1.0.0
- Skill: `eni-module-research_verification` (ICM stages) in skills_pack/skills/eni-modules/research_verification/

## What it does
Research & Verification OS — Enterprise Platform Kernel Module v1.0.0
======================================================================

Enterprise-grade module implementing the Research & Verification Operating
System for the ENI Enterprise AI platform, per the Research OS spec.

Produces trustworthy, evidence-based outputs by retrieving, validating,
comparing, ranking, and synthesizing information before it is accepted
into organizational memory or engineering decisions.

Core components (aligned with Research OS spec):
  - ResearchPlanner       — plan research, classify domain, scope investigation
  - SourceRanker          — rank sources by authority (internal > vendor > standard >
    academic > tech pub > community)
  - ClaimDetector         — detect conflicting claims, distinguish facts from assumptions
  - ConfidenceAssigner    — assign confidence levels to findings with transparent reasoning
  - EvidenceSynthesizer   — synthesize evidence into unified findings with recommendations
  - ProvenanceTracker     — preserve provenance chains, version research, trace lineage

Workflow (per spec):  Understand → Classify → Check internal → Retrieve external →
                       Rank → Compare → Detect conflicts → Assign confidence →
                       Produce findings → Recommend actions → Store validated knowledge.

Core Principles:
  - Truth before speed
  - Verify before concluding
  - Prefer authoritative sources
  - Distinguish facts from assumptions
  - Preserve provenance
  - Version research
  - Never fabricate evidence

Events emitted:
  - research.plan.created        — a new research plan created
  - research.sources.ranked      — sources have been ranked
  - research.claims.detected     — claims extracted and classified
  - research.confidence.assigned — confidence scores assigned
  - research.evidence.synthesized— findings synthesized into report
  - research.provenance.recorded — provenance chain stored
  - research.completed           — full research pipeline finished

Metrics tracked:
  - sources_ranked              — count of ranked sources
  - claims_detected             — count of detected claims
  - conflicts_found             — count of conflicting claims
  - average_confidence          — avg confidence score across findings
  - pipeline_duration_ms        — end-to-end research pipeline time

Architecture:
    __init__.py              — Module housekeeping, @module registration, exports
    research_engine.py       — ResearchPlanner, SourceRanker, ClaimDetector,
                                ConfidenceAssigner, EvidenceSynthesizer, ProvenanceTracker
    source_ranker.py         — SourceRanker standalone with authority tiers
    claim_detector.py        — ClaimDetector standalone with fact/assumption classification
    confidence.py            — ConfidenceAssigner standalone with score computation
    evidence_synthesizer.py  — EvidenceSynthesizer standalone with narrative generation
    tests/tests_research.py  — 25+ production-quality tests

## Key API (facade methods)
confidence, detector, execute_pipeline, health_check, initialize, planner, ranker, shutdown, synthesizer, tracker

## Tests
```bash
python3 -m pytest modules/research_verification/tests -q
```

## Import
```python
from enterprise.modules.research_verification import create_research_verification_module
m = create_research_verification_module()
```
