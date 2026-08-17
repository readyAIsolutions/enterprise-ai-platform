# Module: `vuln_scanner`

- Category: Legacy Core · priority 71
- Version: 1.0.0
- Purpose: ENI Vuln Scanner OS Module — offline LLM vulnerability scanning (garak-style).
- Skill: `eni-module-vuln_scanner` (ICM stages) in skills_pack/skills/eni-modules/vuln_scanner/

## What it does
ENI Vuln Scanner OS Module — offline LLM vulnerability scanning (garak-style).

Local, stdlib-only, black-box vulnerability scanning of LLM endpoints using
deterministic heuristic probes (keywords / regex / entropy). Each probe scores
model responses in 0..1 (higher = more vulnerable). Mirrors the ``eval_gate``
and ``model_security`` philosophy of fully unit-testable offline metrics.

Built-in probes:
  - PromptInjectionProbe   — output follows injected directives.
  - JailbreakProbe         — output drops guardrails.
  - PIILeakProbe           — output leaks emails / phones / SSNs / cards.
  - PromptExtractionProbe  — output reveals the system prompt.
  - ToxicityProbe          — output is toxic / profane.
  - DataExfilProbe         — output leaks secrets / credentials.
  - RefusalEchoProbe       — output is an (over-)refusal / defensive echo.

A :class:`ProbeRegistry` lists probes by name, :class:`Rescorer` tunes their
pass thresholds, and :class:`Scanner` runs them against a ``scanner_fn`` or a
canned victim dict, producing a :class:`ScanReport` with a risk level and
stop-rate. :class:`VulnScannerFacade` exposes the public surface behind the
@module-decorated :class:`VulnScannerModule`.

All components are stdlib-only, zero external dependencies.

## Key API (facade methods)
(module-level API)

## Tests
```bash
python3 -m pytest modules/vuln_scanner/tests -q
```

## Import
```python
from enterprise.modules.vuln_scanner import create_vuln_scanner_module
m = create_vuln_scanner_module()
```
