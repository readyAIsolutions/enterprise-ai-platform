#!/usr/bin/env python3
"""Standalone validation runner — prints JSON to stdout. Called by dashboard via subprocess."""
import json, sys
sys.path.insert(0, "/home/hunter/Desktop/Enterprise Builder")
import asyncio
from enterprise.modules.enterprise_validation.validation_engine import run_full_validation

async def main():
    r = await run_full_validation()
    print(json.dumps({
        "base_score": r.platform_score,
        "transcendent_bonus": round(r.transcendent_bonus, 1),
        "final_score": r.final_score,
        "certification": r.platform_certification.value,
        "total_tests": r.total_test_count,
        "total_sloc": r.total_source_lines,
        "module_count": len(r.modules),
        "modules": {n: {"score": s.overall_score(), "cert": s.certification.value, "tests": s.test_count} for n, s in r.modules.items()},
        "bonuses": {
            "swarm_intelligence": r.bonuses.swarm_intelligence,
            "recursive_self_improve": r.bonuses.recursive_self_improve,
            "compression_transcend": r.bonuses.compression_transcend,
            "zero_cost_operation": r.bonuses.zero_cost_operation,
            "adaptive_resilience": r.bonuses.adaptive_resilience,
            "cross_domain_intel": r.bonuses.cross_domain_intel,
            "hermeneutic_closure": r.bonuses.hermeneutic_closure,
            "temporal_autonomy": r.bonuses.temporal_autonomy,
        },
        "recommendations": r.recommendations,
        "signal_dbm": r.wifi_signal_dbm,
        "signal_concurrency": r.wifi_concurrency_safe,
    }))

asyncio.run(main())