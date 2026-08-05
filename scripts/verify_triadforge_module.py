#!/usr/bin/env python3
"""Verify the TriadForge ENTERPRISE module boots and runs a real scan."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root (enterprise pkg)
sys.path.insert(0, "/home/hunter/Desktop/TriadForge")           # triadforge pkg + tests

from enterprise.modules.triadforge import TriadForgeModule  # noqa: E402
from enterprise.platform_kernel import HealthStatus  # noqa: E402


import tests.sample_app  # noqa: E402,F401  (make tests importable)


async def main() -> int:
    m = TriadForgeModule({})
    print("available:", getattr(m, "_available"))
    await m.initialize()
    print("status after init:", m.status)

    # Start a local vulnerable sample app to scan
    from tests.sample_app.app import serve
    srv = serve()
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print("sample app at:", url)

    # REGISTER + SCAN via the enterprise module facade
    tid = m.add_web_target("enterprise-module-vuln", url, mode="black")
    print("target id:", tid)
    srv2 = serve()
    t2 = m.add_web_target("zero-findings-check", f"http://127.0.0.1:{srv2.server_address[1]}/", mode="black")
    print("second target id:", t2)

    result = m.run_scan(tid)
    print("scan result:", result)
    findings = m.list_findings(scan_id=result.get("scan_id"))
    print(f"findings via facade: {len(findings)}")
    for f in findings[:6]:
        print(f"   [{f['severity']}] {f['title']} | conf={f['confidence']}")

    sarif = m.export_sarif(result.get("scan_id"))
    nr = len(sarif["runs"][0]["results"]) if sarif.get("runs") else 0
    print("SARIF results:", nr)
    print("fix_snippet(missing-hsts):", m.fix_snippet("missing-hsts"))

    hs = await m.health_check()
    print("health_check:", hs)

    srv.server_close(); srv2.server_close()
    # assert the scan actually found the xss/broken-cookie breaks
    sev = {f["rule_id"] for f in findings}
    assert any("xss" in r for r in sev) or any("cookie" in r for r in sev), f"expected breaks, got {sev}"
    assert len(findings) >= 3
    print("\n=== Enterprise TriadForge module: VERIFIED ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
