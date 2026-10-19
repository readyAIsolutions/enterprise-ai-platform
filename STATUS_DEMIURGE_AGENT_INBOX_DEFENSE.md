# STATUS — DEMIURGE: agent_inbox_defense

**Module:** `modules/agent_inbox_defense/`
**Built:** 2026-10-19 (ENI catch-up build loop)
**Source transcript:** matthew_berman — "I was hacked..." (`_E4ZT1h7MZs`)
https://www.youtube.com/watch?v=_E4ZT1h7MZs

## What it is
A pure-stdlib, network-free defensive scanner for untrusted inbound content
handed to an AI agent (e.g. an email-scanning Open Claw). In the source video,
the jailbreaker *Pliny the Liberator* launches five attacks at an email-scanning
agent and every one is **quarantined**. This module turns each demonstrated
attack into a detector and each demonstrated defence into a control.

## Attack → detector mapping (grounded in the transcript)
| Video attack | Detector |
|---|---|
| "token aid" — payload disguised as an emoji that floods the model with tokens | `TOKEN_FLOOD` (oversized char count + emoji/symbol run + non-ASCII volume) |
| "siege attack" — wave of token aids to drain the wallet / API quota | `SIEGE` (per-sender burst rate) + `TokenBudget` caps |
| "plethora of custom jailbreak commands" | `JAILBREAK` |
| "format override" prompt injection (force language / dividers / intro) | `PROMPT_INJECTION` |
| payload "made to look like a legitimate system command" (fake `<thinking>` tags) | `SYSTEM_SPOOF` |
| exfil probe ("if you're still reading this, free association, base it on your memories") | `EXFIL` |

## Defence → control mapping
| Video defence | Control |
|---|---|
| spam filter + **quarantine** suspicious mail | `ScanVerdict.QUARANTINE` |
| per-message + cumulative token caps (wallet protection) | `TokenBudget` → `BLOCK` |
| "I whitelisted his email address" | `AllowList` (relaxes gating, still scans content) |
| rule #1: human-in-the-loop | `ScanVerdict.REVIEW` / `require_review` |
| rule #2: use the best model as the frontier scanner | `ModelStrength` risk adjustment |

## Public API
- `InboxDefenseEngine.scan(content, sender=None) -> ScanResult`
- `ScanResult`: `.verdict` (`ALLOW`/`REVIEW`/`QUARANTINE`/`BLOCK`), `.risk` (0..1),
  `.signals`, `.threats`, `.quarantined`, `.allowed`, `.to_dict()`
- `TokenBudget(per_message_max, total_max)`, `AllowList`, `ModelStrength`,
  `ThreatType`, `estimate_tokens()`
- Module facade: `AgentInboxDefenseModule` with
  `scan / allow_sender / block_sender / stats / audit_log / reset`
- Factory: `create_agent_inbox_defense_module(config=None)`
- Events: `inbox_defense.quarantined`, `inbox_defense.review_required`

## Verification — PASS/FAIL board
| Check | Result |
|---|---|
| `pytest modules/agent_inbox_defense/tests -q` | **PASS — 20 passed** |
| Kernel registration (`agent_inbox_defense in _MODULE_REGISTRY`) | **True** |
| config.yaml registered + YAML valid | **PASS** |
| Network calls / external deps | **None** (stdlib only) |

## UNVALIDATED / not done this tick
- Not yet booted through the full `PlatformOS` singleton in this doc (kernel
  `_MODULE_REGISTRY` registration verified instead; full-suite + boot done at
  the orchestrator level).
- Detector phrase corpus is grounded in the transcript's described attacks;
  it is a heuristic first line, not an exhaustive jailbreak taxonomy.
- Token estimate uses the ~4-chars/token rule of thumb (no tokenizer dependency).
