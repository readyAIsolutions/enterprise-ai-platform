#!/usr/bin/env python3
"""
SaaS Production Hardening Audit Scanner.

Scans a codebase for critical production-readiness patterns:
- Resilience patterns (circuit breaker, retry, timeout, bulkhead, rate limit)
- Observability (metrics, logging, tracing, alerting)
- Security (encryption, secrets, auth, rate limiting)
- Compliance (GDPR, CCPA, TCPA, CAN-SPAM)
- Multi-tenancy (RLS, isolation)
- Testing maturity

Usage:
    python audit_scan.py /path/to/project --output audit_report.md
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


# =============================================================================
# PATTERNS TO SCAN
# =============================================================================

CRITICAL_PATTERNS = {
    # Resilience
    "circuit_breaker": [
        r"circuit.?breaker",
        r"CircuitBreaker",
        r"@circuit_breaker",
        r"pybreaker",
        r"circuitbreaker",
    ],
    "retry": [
        r"retry",
        r"@retry",
        r"tenacity",
        r"backoff",
        r"exponential.?backoff",
    ],
    "timeout": [
        r"timeout",
        r"Timeout",
        r"asyncio\.wait_for",
        r"httpx\.Timeout",
    ],
    "bulkhead": [
        r"bulkhead",
        r"Bulkhead",
        r"semaphore",
        r"concurrency.?limit",
    ],
    "rate_limit": [
        r"rate.?limit",
        r"RateLimiter",
        r"token.?bucket",
        r"throttle",
    ],
    "idempotency": [
        r"idempotent",
        r"idempotency",
        r"Idempotency",
    ],
    "dead_letter": [
        r"dead.?letter",
        r"DLQ",
        r"dead_letter",
    ],
    
    # Observability
    "prometheus": [
        r"prometheus",
        r"Prometheus",
        r"Counter\(",
        r"Histogram\(",
        r"Gauge\(",
        r"/metrics",
    ],
    "structured_logging": [
        r"structlog",
        r"json.?log",
        r"correlation.?id",
        r"contextvars",
    ],
    "distributed_tracing": [
        r"opentelemetry",
        r"OpenTelemetry",
        r"jaeger",
        r"zipkin",
        r"trace.?id",
        r"span",
    ],
    "alerting": [
        r"alertmanager",
        r"Alertmanager",
        r"prometheus.?rule",
        r"alert.?rule",
    ],
    
    # Security
    "encryption_at_rest": [
        r"encryption.?at.?rest",
        r"TDE",
        r"pgcrypto",
        r"fernet",
        r"cryptography",
    ],
    "encryption_in_transit": [
        r"mtls",
        r"mutual.?tls",
        r"tls.*cert",
        r"ssl.*cert",
    ],
    "secrets_management": [
        r"vault",
        r"Vault",
        r"sealed.?secret",
        r"external.?secret",
        r"sops",
        r"age.?encryption",
    ],
    "auth": [
        r"oauth2",
        r"oidc",
        r"saml",
        r"mfa",
        r"multi.?factor",
    ],
    "rate_limiting": [
        r"rate.?limit",
        r"RateLimiter",
        r"throttle",
    ],
    
    # Compliance
    "gdpr": [
        r"gdpr",
        r"GDPR",
        r"data.?protection.?impact",
        r"DPIA",
        r"ROPA",
        r"DSAR",
        r"right.?to.?erasure",
        r"R2E",
        r"consent.?receipt",
    ],
    "ccpa": [
        r"ccpa",
        r"CCPA",
        r"cpra",
        r"CPRA",
        r"consumer.?rights",
        r"opt.?out",
        r"do.?not.?sell",
    ],
    "tcpa": [
        r"tcpa",
        r"TCPA",
        r"do.?not.?call",
        r"DNC",
        r"prior.?express.?consent",
        r"STIR/SHAKEN",
        r"A2P.?10DLC",
    ],
    "can_spam": [
        r"can.?spam",
        r"CAN.?SPAM",
        r"unsubscribe",
        r"List-Unsubscribe",
    ],
    
    # Multi-tenancy
    "row_level_security": [
        r"row.?level.?security",
        r"RLS",
        r"pg.?rls",
        r"policy.?create",
    ],
    "multi_tenant": [
        r"multi.?tenant",
        r"workspace.?isolation",
        r"tenant.?isolation",
    ],
    
    # Testing
    "integration_test": [
        r"integration.?test",
        r"@pytest.?mark.?integration",
    ],
    "e2e_test": [
        r"e2e.?test",
        r"playwright",
        r"cypress",
        r"selenium",
    ],
    "load_test": [
        r"load.?test",
        r"k6",
        r"locust",
        r"jmeter",
    ],
    "chaos_test": [
        r"chaos.?test",
        r"litmus",
        r"chaos.?mesh",
    ],
}


# =============================================================================
# SCANNER
# =============================================================================

@dataclass
class ScanResult:
    file: str
    line: int
    pattern: str
    match: str
    category: str


def scan_file(filepath: Path) -> list[ScanResult]:
    """Scan a single file for patterns."""
    results = []
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
        lines = content.split("\n")
        
        for category, patterns in CRITICAL_PATTERNS.items():
            for pattern in patterns:
                for i, line in enumerate(lines, 1):
                    if re.search(pattern, line, re.IGNORECASE):
                        results.append(ScanResult(
                            file=str(filepath),
                            line=i,
                            pattern=pattern,
                            match=line.strip()[:100],
                            category=category,
                        ))
    except Exception as e:
        print(f"Error scanning {filepath}: {e}", file=sys.stderr)
    return results


def scan_project(root: Path, exclude_dirs: set = None) -> dict[str, list[ScanResult]]:
    """Scan entire project."""
    exclude_dirs = exclude_dirs or {"__pycache__", ".git", ".venv", "venv", "node_modules", ".pytest_cache", "dist", "build", "*.egg-info"}
    
    results_by_category: dict[str, list[ScanResult]] = {}
    
    for filepath in root.rglob("*.py"):
        if any(part in exclude_dirs for part in filepath.parts):
            continue
        if filepath.name.startswith("."):
            continue
            
        file_results = scan_file(filepath)
        for result in file_results:
            results_by_category.setdefault(result.category, []).append(result)
    
    return results_by_category


def generate_report(results: dict[str, list[ScanResult]], project_name: str) -> str:
    """Generate markdown audit report."""
    lines = [
        f"# Audit Report: {project_name}",
        f"**Generated**: {datetime.now().isoformat()}",
        f"**Project Root**: {results}",
        "",
        "## Summary",
        "",
    ]
    
    # Count by category
    for category, matches in sorted(results.items()):
        lines.append(f"- **{category}**: {len(matches)} matches")
    
    lines.append("")
    
    # Detailed findings
    for category, matches in sorted(results.items()):
        if not matches:
            continue
        lines.append(f"## {category.replace('_', ' ').title()}")
        lines.append("")
        
        # Group by file
        by_file: dict[str, list[ScanResult]] = {}
        for m in matches:
            by_file.setdefault(m.file, []).append(m)
        
        for file, file_matches in sorted(by_file.items()):
            rel_path = os.path.relpath(file, ".")
            lines.append(f"### `{rel_path}`")
            lines.append("")
            for m in file_matches[:10]:  # Limit per file
                lines.append(f"- Line {m.line}: `{m.match}`")
            if len(file_matches) > 10:
                lines.append(f"- ... and {len(file_matches) - 10} more")
            lines.append("")
    
    return "\n".join(lines)


def check_gaps(results: dict[str, list[ScanResult]]) -> list[str]:
    """Identify critical gaps (categories with zero matches)."""
    all_categories = set(CRITICAL_PATTERNS.keys())
    found_categories = set(results.keys())
    missing = all_categories - found_categories
    
    # Only report truly critical gaps
    critical = {
        "circuit_breaker", "retry", "timeout", "bulkhead", "rate_limit",
        "prometheus", "structured_logging", "distributed_tracing",
        "encryption_at_rest", "encryption_in_transit", "secrets_management",
        "gdpr", "ccpa", "tcpa", "can_spam",
        "row_level_security", "multi_tenant",
        "integration_test", "e2e_test", "load_test",
    }
    
    return sorted(critical & missing)


def main():
    parser = argparse.ArgumentParser(description="SaaS Production Hardening Audit Scanner")
    parser.add_argument("path", nargs="?", default=".", help="Project root path")
    parser.add_argument("-o", "--output", help="Output file (markdown)")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of markdown")
    args = parser.parse_args()
    
    root = Path(args.path).resolve()
    print(f"Scanning {root}...", file=sys.stderr)
    
    results = scan_project(root)
    
    # Print summary
    print("\n=== SCAN SUMMARY ===")
    for category, matches in sorted(results.items()):
        print(f"  {category}: {len(matches)}")
    
    gaps = check_gaps(results)
    if gaps:
        print("\n=== CRITICAL GAPS ===")
        for gap in gaps:
            print(f"  MISSING: {gap}")
    else:
        print("\n=== NO CRITICAL GAPS DETECTED ===")
    
    # Generate report
    if args.output or args.json:
        report = generate_report(results, root.name)
        if args.json:
            # Convert to JSON-serializable
            json_data = {
                "project": root.name,
                "timestamp": datetime.now().isoformat(),
                "summary": {k: len(v) for k, v in results.items()},
                "gaps": gaps,
                "details": [
                    {
                        "file": m.file,
                        "line": m.line,
                        "pattern": m.pattern,
                        "match": m.match,
                        "category": m.category,
                    }
                    for matches in results.values()
                    for m in matches
                ],
            }
            output_content = json.dumps(json_data, indent=2)
        else:
            output_content = report
        
        if args.output:
            Path(args.output).write_text(output_content)
            print(f"\nReport written to {args.output}")
        else:
            print(output_content)


if __name__ == "__main__":
    main()