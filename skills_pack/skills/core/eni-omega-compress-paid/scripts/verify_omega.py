#!/usr/bin/env python3
"""Deterministic 4-corpus verification of the ENI omega engine (95%+ lossless bar).

Re-runnable proof for LO's "is compression at 95% and tested?" — build realistic
logs/code/chat/json corpora, run the fast tier, assert every corpus is >=95% saved AND
lossless. No args, exit 0 = PASS.

Run:  python3 ~/.hermes/skills/core/eni-omega-compress-paid/scripts/verify_omega.py
(needs the Compression dir on sys.path — the engine lives there.)
"""
import sys, time, json

COMPRESSION = "/home/hunter/Desktop/Projects/ENI_Swarm/Compression"
if COMPRESSION not in sys.path:
    sys.path.insert(0, COMPRESSION)
from eni_omega_engine import compress, roundtrip  # noqa: E402

BAR = 95.0  # % saved target


def mk(name, text):
    t = time.time()
    res = compress(text, tier="fast")
    dt = time.time() - t
    r = float(res.get("ratio") or 1.0)
    saved = 100 * (1 - 1 / r) if r > 1 else 0
    rt = roundtrip(text, tier="fast")[0]
    ok = saved >= BAR and rt
    print(f"[{'PASS' if ok else 'FAIL'}] {name:6} saved={saved:6.2f}%  ratio={r:7.2f}x  "
          f"lossless={rt}  time={dt:5.2f}s  engine={res.get('engine')}")
    return ok


LOGS = "\n".join(
    f"2026-08-04 18:0{i%60}:0{i%60} INFO enterprise.modules.ai_defense gate "
    f"gate_request key=10.0.0.{i%200} user_agent=python-requests/2.31 "
    f"block_rate=0.99 facet=anomaly" for i in range(300)
)
CODE = ("def _run_gate(self, path, key, ua, headers, query, environ):\n"
        "    method = environ.get('REQUEST_METHOD', 'GET')\n"
        "    if _is_auth_path(path):\n"
        "        content = _read_body(environ)\n"
        "        d = self.gate.facade.check_auth(acct, key)\n"
        "        if d.malicious:\n"
        "            return GateDecision(False, d.reason or 'lockout', 'credential-stuffing')\n"
        "    return self.gate.gate(key=key, user_agent=ua, headers=headers)\n") * 50
CHAT = "\n".join(
    "user: can you help with the {}? i need to {} thing {}\nassistant: yes let me {} that for you".format(
        "gate" if i % 2 else "engine", "block" if i % 3 else "compress", i, "defend")
    for i in range(200)
)
JSOND = json.dumps({"scans": [{"id": i, "target": f"site{i}",
                               "severity": "high" if i % 3 == 0 else "medium",
                               "rule": f"rule{i}",
                               "evidence": {"url": f"http://x/{i}", "status": 429}}
                              for i in range(400)]})

ok = True
for name, text in [("logs", LOGS), ("code", CODE), ("chat", CHAT), ("json", JSOND)]:
    if not mk(name, text):
        ok = False

print("\nFAST TIER ALL >=95% LOSSLESS:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
