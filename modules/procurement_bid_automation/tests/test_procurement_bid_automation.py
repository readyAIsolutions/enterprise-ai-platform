"""Tests for the procurement_bid_automation module.

All tests are deterministic and network-free (pure stdlib). async tests use
asyncio_mode="auto". Focused on the real transcript themes: NAICS/PSC/NIGP code
selection, solicitation/RFP decoding, capability statements, profile grading,
and bid/no-bid fit & ROI assessment.
"""
import asyncio

import pytest

from enterprise.platform_kernel import Event, EventBus, HealthStatus

from enterprise.modules.procurement_bid_automation import (
    BUILTIN_TAXONOMY, CapabilityStatement, Code, CodeMatcher, CompanyProfile,
    OpportunityAssessment, ProcurementBidAutomationModule, ProfileGrade,
    ScoredCode, Solicitation, SolicitationAnalysis, analyze_solicitation,
    assess_opportunity, company_info_to_guidance,
    create_procurement_bid_automation_module, generate_capability_statement,
    grade_profile,
)
from enterprise.modules.procurement_bid_automation.procurement_bid_automation import (
    tokenize, keyword_overlap,
)


def _ai_consulting_profile() -> CompanyProfile:
    return CompanyProfile(
        name="VanClief Analytics",
        description="We provide AI strategy, machine learning implementation, "
                    "data verification and analytics for government agencies.",
        mission="Help agencies adopt AI responsibly.",
        target_agencies=["DHS", "DoD", "GSA"],
        sectors=["AI consulting", "data analytics", "software development"],
        past_performance=["Built a ML analytics platform for a federal agency",
                          "Provided AI strategy consulting to a state government"],
        certifications=["Veteran-Owned Small Business"],
        team_size=12,
        geographic_coverage="Continental US",
        contact_info="contracts@vanclief.example",
        differentiators=["Veteran-owned", "Fast delivery", "AI domain experts"],
        client_list=["Example Federal Agency"],
        clearance_level="Public Trust",
        gsa_schedules=["IT Schedule 70"],
    )


# --------------------------------------------------------------------------- #
# text helpers
# --------------------------------------------------------------------------- #
def test_tokenize_lowercases_and_drops_stopwords():
    toks = tokenize("We provide AI strategy and analytics for agencies")
    assert isinstance(toks, list)
    assert "ai" in toks and "analytics" in toks
    assert "and" not in toks and "we" not in toks


def test_keyword_overlap_counts_phrase_hits():
    toks = tokenize("software development and custom application development")
    assert keyword_overlap(toks, ("software", "application development")) == 2
    assert keyword_overlap(toks, ("quantum cryptography",)) == 0


# --------------------------------------------------------------------------- #
# code taxonomy & CodeMatcher
# --------------------------------------------------------------------------- #
def test_builtin_taxonomy_has_expected_families():
    families = {c.family for c in BUILTIN_TAXONOMY}
    assert {"naics", "nigp", "psc"} <= families
    assert any(c.id == "91821" for c in BUILTIN_TAXONOMY)  # consulting code
    assert any(c.id == "91899" for c in BUILTIN_TAXONOMY)  # computer services


def test_code_matches_returns_score():
    code = Code("541511", "Custom Computer Programming Services", "naics",
                ("software", "programming"))
    tokens = tokenize("custom software programming for agencies")
    assert code.matches(tokens) == 2


def test_score_codes_returns_sorted_descending():
    m = CodeMatcher()
    scored = m.score_codes("AI consulting, data analytics and software development")
    scores = [s.score for s in scored]
    assert scores == sorted(scores, reverse=True)


def test_recommend_codes_filters_by_min_score():
    m = CodeMatcher()
    recs = m.recommend_codes("computer related services and it support",
                             min_score=1)
    assert all(s.score >= 1 for s in recs)
    assert any("91899" in s.code.id for s in recs)


def test_recommend_codes_limit():
    m = CodeMatcher()
    assert len(m.recommend_codes("consulting", limit=2, min_score=1)) <= 2


def test_code_by_id_finds_existing():
    m = CodeMatcher()
    assert m.code_by_id("541511") is not None
    assert m.code_by_id("999999") is None


def test_full_company_description_ranks_ai_data_codes_high():
    m = CodeMatcher()
    recs = m.recommend_codes(
        "AI strategy, machine learning, data verification and analytics",
        limit=5, min_score=1)
    assert recs[0].score >= recs[-1].score
    # the data/nigp data code should be among the top handful
    assert any("91838" in s.code.id for s in recs[:6])


def test_code_matcher_is_deterministic():
    m1, m2 = CodeMatcher(), CodeMatcher()
    assert ([s.code.id for s in m1.score_codes("data analytics consulting")]
            == [s.code.id for s in m2.score_codes("data analytics consulting")])


def test_custom_code_registry_respected():
    custom = [Code("X1", "Custom", "naics", ("widget",))]
    m = CodeMatcher(codes=custom)
    recs = m.recommend_codes("we make a widget here", min_score=1)
    assert any(s.code.id == "X1" for s in recs)
    assert m.code_by_id("541511") is None  # builtins not mixed in


# --------------------------------------------------------------------------- #
# CompanyProfile
# --------------------------------------------------------------------------- #
def test_profile_roundtrip_dict():
    p = _ai_consulting_profile()
    d = p.to_dict()
    p2 = CompanyProfile.from_dict(d)
    assert p2.name == p.name
    assert p2.target_agencies == p.target_agencies
    assert p2.team_size == 12


def test_profile_from_empty_dict():
    assert CompanyProfile.from_dict(None).team_size == 0
    assert CompanyProfile.from_dict({}).name == ""


def test_profile_from_scalar_list_fields():
    p = CompanyProfile.from_dict(
        {"target_agencies": "DHS, DoD", "cage_code": "7X8A1"})
    assert p.target_agencies == ["DHS", "DoD"]
    assert p.cage_code == "7X8A1"


# --------------------------------------------------------------------------- #
# capability statement
# --------------------------------------------------------------------------- #
def test_generate_capability_statement_sections():
    stmt = generate_capability_statement(_ai_consulting_profile())
    assert isinstance(stmt, CapabilityStatement)
    assert stmt.company_name == "VanClief Analytics"
    assert len(stmt.core_capabilities) > 0
    assert stmt.past_performance
    assert stmt.point_of_contact == "contracts@vanclief.example"


def test_capability_statement_render_contains_overview():
    stmt = generate_capability_statement(_ai_consulting_profile())
    text = stmt.render()
    assert "CAPABILITY STATEMENT" in text
    assert "VanClief Analytics" in text
    assert "Past Performance" in text


def test_capability_statement_page_estimate():
    stmt = generate_capability_statement(_ai_consulting_profile())
    pages = stmt.page_estimate()
    assert isinstance(pages, int) and pages >= 1


def test_generate_capability_statement_derives_capabilities_from_description():
    p = CompanyProfile(name="Acme", description="data processing and database hosting")
    stmt = generate_capability_statement(p)
    assert len(stmt.core_capabilities) > 0


# --------------------------------------------------------------------------- #
# profile grading
# --------------------------------------------------------------------------- #
def test_grade_profile_full_profile_scores_high():
    grade = grade_profile(_ai_consulting_profile())
    assert isinstance(grade, ProfileGrade)
    assert 50 <= grade.score <= 100


def test_grade_profile_empty_scores_low_and_lists_missing():
    grade = grade_profile(CompanyProfile())
    assert grade.score < 40
    assert grade.missing  # lists what's missing
    assert grade.recommendations


def test_grade_profile_missing_contact_and_geo_dropped():
    p = _ai_consulting_profile()
    p.contact_info = ""
    p.geographic_coverage = ""
    p.clearance_level = ""
    p.gsa_schedules = []
    p.cage_code = ""
    grade = grade_profile(p)
    assert any("contact" in r.lower() for r in grade.missing)
    assert any("geographic" in r.lower() for r in grade.missing)
    assert grade.score < grade_profile(_ai_consulting_profile()).score


def test_grade_profile_letter_boundaries():
    assert ProfileGrade(score=95.0, working_well=[], missing=[], recommendations=[]).letter == "A"
    assert ProfileGrade(score=72.0, working_well=[], missing=[], recommendations=[]).letter == "C"
    assert ProfileGrade(score=5.0, working_well=[], missing=[], recommendations=[]).letter == "F"


def test_grade_profile_to_dict():
    d = grade_profile(_ai_consulting_profile()).to_dict()
    assert "score" in d and "letter" in d and "missing" in d


# --------------------------------------------------------------------------- #
# solicitation / RFP analysis
# --------------------------------------------------------------------------- #
_SOL_TEXT = (
    "Request for Proposal - Data Analytics Platform for Network Performance.\n"
    "- Provide data verification and analysis services.\n"
    "- Deliver monthly performance reports.\n"
    "- Deadline: 09/15/2026 for all submissions.\n"
    "This is a small business set aside. NAICS 518210 applies.\n"
    "Sources sought - capability statement encouraged.\n"
)


def _solicitation() -> Solicitation:
    return Solicitation(
        id="RFP-2026-0142",
        title="Data Analytics Platform for Network Performance",
        agency="DHS",
        source="sam.gov",
        text=_SOL_TEXT,
        naics_codes=["518210"],
    )


def test_analyze_solicitation_extracts_deadline():
    analysis = analyze_solicitation(_solicitation())
    assert analysis.deadline == "09/15/2026"


def test_analyze_solicitation_extracts_requirements():
    analysis = analyze_solicitation(_solicitation())
    assert any("data verification" in r.lower() for r in analysis.requirements)
    assert any("monthly performance reports" in r.lower() for r in analysis.requirements)


def test_analyze_solicitation_detects_set_aside_and_eligibility():
    analysis = analyze_solicitation(_solicitation())
    assert analysis.set_aside == "small business"
    assert any("small business" in e.lower() for e in analysis.eligibility)
    assert any("518210" in e for e in analysis.eligibility)


def test_analyze_solicitation_do_bid_signals():
    analysis = analyze_solicitation(_solicitation())
    assert any("sources sought" in s for s in analysis.do_bid_signals)
    assert any("capability statement" in s for s in analysis.do_bid_signals)


def test_analyze_solicitation_high_clearance_triggers_donot_bid():
    sol = _solicitation()
    sol.text = "Requires top secret clearance and bond required."
    analysis = analyze_solicitation(sol)
    assert analysis.donot_bid_heuristics  # clearance / bond negatives


def test_analyze_solicitation_caps_requirements():
    sol = _solicitation()
    sol.text = "\n".join(f"- requirement item {i}" for i in range(40))
    analysis = analyze_solicitation(sol)
    assert len(analysis.requirements) <= 20


def test_analyze_solicitation_explicit_deadline_wins():
    sol = _solicitation()
    sol.response_deadline = "12/01/2026"
    sol.text = "due by 07/04/2026"
    analysis = analyze_solicitation(sol)
    assert analysis.deadline == "12/01/2026"


def test_solicitation_analysis_to_dict():
    d = analyze_solicitation(_solicitation()).to_dict()
    assert d["id"] == "RFP-2026-0142"
    assert d["deadline"] == "09/15/2026"


# --------------------------------------------------------------------------- #
# opportunity fit / ROI assessment
# --------------------------------------------------------------------------- #
def test_assess_opportunity_good_fit_returns_bid():
    case = _solicitation()
    result = assess_opportunity(_ai_consulting_profile(), case, capacity=0.8)
    assert isinstance(result, OpportunityAssessment)
    assert result.verdict in ("bid", "deliberate")
    assert 0.0 <= result.overall <= 1.0


def test_assess_opportunity_no_fit_returns_no_bid():
    sol = Solicitation(
        id="X", title="Road resurfacing and asphalt repair",
        agency="City DOT", text="excavation asphalt paving aggregate",
        naics_codes=[],
    )
    prof = _ai_consulting_profile()
    result = assess_opportunity(prof, sol, capacity=0.3)
    assert result.capability_match < 0.5
    assert result.verdict == "no_bid"


def test_assess_opportunity_low_capacity_flags():
    case = _solicitation()
    result = assess_opportunity(_ai_consulting_profile(), case, capacity=0.2)
    assert any("capacity" in r.lower() for r in result.rationale)


def test_assess_opportunity_weights_respected():
    case = _solicitation()
    w = {"capability_match": 1.0, "past_performance": 0.0,
         "capacity": 0.0, "roi": 0.0}
    result = assess_opportunity(_ai_consulting_profile(), case,
                                weights=w, capacity=0.9)
    assert result.overall == pytest.approx(result.capability_match, abs=0.02)


def test_assess_opportunity_sources_sought_boosts_roi():
    prof = _ai_consulting_profile()
    case = _solicitation()
    roi_ss = assess_opportunity(prof, case, capacity=0.6)
    case2 = _solicitation()
    case2.text = "Statement of work - full fixed price delivery requirement."
    roi_sw = assess_opportunity(prof, case2, capacity=0.6)
    assert roi_ss.roi >= roi_sw.roi


def test_assess_opportunity_to_dict():
    case = _solicitation()
    d = assess_opportunity(_ai_consulting_profile(), case, capacity=0.6).to_dict()
    assert d["verdict"] in ("bid", "no_bid", "deliberate")
    assert set(["capability_match", "past_performance", "capacity", "roi",
                "overall"]) <= set(d.keys())


# --------------------------------------------------------------------------- #
# company-info -> apply/codes guidance flow
# --------------------------------------------------------------------------- #
def test_company_info_to_guidance_bundles_codes_statement_grade():
    out = company_info_to_guidance(_ai_consulting_profile(), top_codes=4)
    assert out["recommended_codes"]
    assert "CAPABILITY STATEMENT" in out["capability_statement"]
    assert out["capability_pages"] >= 1
    assert "score" in out["profile_grade"]


def test_company_info_to_guidance_respects_top_codes():
    out = company_info_to_guidance(_ai_consulting_profile(), top_codes=3)
    assert len(out["recommended_codes"]) <= 3


# --------------------------------------------------------------------------- #
# module wrapper
# --------------------------------------------------------------------------- #
def test_create_module_factory():
    mod = create_procurement_bid_automation_module()
    assert isinstance(mod, ProcurementBidAutomationModule)


def test_module_initialize_and_health():
    mod = create_procurement_bid_automation_module()
    mod.set_event_bus(None)  # no bus yet — must not raise

    async def run():
        await mod.initialize()
        assert mod.status is HealthStatus.HEALTHY
        assert await mod.health_check() is HealthStatus.HEALTHY
        await mod.shutdown()
        assert mod.status is HealthStatus.UNKNOWN

    asyncio.run(run())


@pytest.fixture
def wired_module():
    async def build():
        mod = create_procurement_bid_automation_module()
        bus = EventBus(config={"async_dispatch": False})

        @bus.subscribe("procurement.bid.*", subscriber_name="test")
        def _noop(e):
            return None

        mod.set_event_bus(bus)
        await mod.initialize()
        return mod, bus
    return asyncio.run(build())


def test_module_recommend_codes_facade(wired_module):
    mod, _bus = wired_module
    recs = mod.recommend_codes("AI strategy, data analytics and software")
    assert isinstance(recs, list)
    assert all("id" in r and "score" in r for r in recs)


def test_module_generate_capability_statement_facade(wired_module):
    mod, _bus = wired_module
    out = mod.generate_capability_statement(_ai_consulting_profile().to_dict())
    assert "CAPABILITY STATEMENT" in out["text"]


def test_module_grade_profile_facade(wired_module):
    mod, _bus = wired_module
    d = mod.grade_profile(_ai_consulting_profile().to_dict())
    assert 0 <= d["score"] <= 100


def test_module_analyze_solicitation_facade(wired_module):
    mod, _bus = wired_module
    out = mod.analyze_solicitation(_solicitation().__dict__)
    assert out["deadline"] == "09/15/2026"
    assert out["set_aside"] == "small business"


def test_module_assess_opportunity_facade(wired_module):
    mod, _bus = wired_module
    out = mod.assess_opportunity(_ai_consulting_profile().to_dict(),
                                 _solicitation().__dict__, capacity=0.8)
    assert out["verdict"] in ("bid", "deliberate", "no_bid")


def test_module_recommend_codes_without_init_raises():
    mod = create_procurement_bid_automation_module()
    with pytest.raises(RuntimeError):
        mod.recommend_codes("data analytics")


def test_module_publishes_event_when_bus_wired():
    captured = []

    async def run():
        bus = EventBus(config={"async_dispatch": False})

        @bus.subscribe("procurement.bid.*")
        def handler(e):
            captured.append(e)

        mod = create_procurement_bid_automation_module()
        mod.set_event_bus(bus)
        await mod.initialize()
        mod.grade_profile(_ai_consulting_profile().to_dict())

    asyncio.run(run())
    assert captured  # at least one event published
    topics = {e.topic for e in captured}
    assert "procurement.bid.initialized" in topics


def test_module_does_not_publish_without_bus():
    # No EventBus wired — publishing is guarded and must not raise.
    async def run():
        mod = create_procurement_bid_automation_module()
        await mod.initialize()
        mod.grade_profile(_ai_consulting_profile().to_dict())

    asyncio.run(run())  # must not raise


def test_module_health_unhealthy_without_initialize():
    mod = create_procurement_bid_automation_module()

    async def run():
        assert await mod.health_check() is HealthStatus.UNHEALTHY

    asyncio.run(run())
