# ENI ENTERPRISE BUILDER — Go-To-Market & Pricing Playbook
**Owner:** LO / readyAIsolutions | **Date:** 2026-08-16 | **Status: v1 draft**

## 1. What we're selling
Not a software license. A **horizontal cooperative build capability**: a team of
developers + their AI, all on the same shared codebase at the same time, each machine
contributing compute and model keys, coordinated by one server with a live board. The
pitch: "we compress a quarter of engineering into days, using machines you already own."

## 2. What it's worth (the anchor)
- A typical senior engineering seat: $80k–250k/yr fully loaded.
- This tool makes a team meaningfully more coherent/faster => buyers can justify
  5–10% of ONE seat for the whole cluster. Real anchor = the labor problem it replaces,
  NOT what an "AI tool" normally costs. That anchoring is the whole pricing strategy.

## 3. Tier ladder (product -> price)
| Tier | Who | Price | Delivered |
|---|---|---|---|
| Self-host, Free | dev-tools evaluators | Free up to 10 builders | full repo, make install, one prompt -> program |
| Team | companies using it daily | $12k–25k/yr flat | unlimited builders, multi-tenancy, priority support |
| Pro per-seat | freelancers/shops | 2.5k/yr per builder after free tier | per-machine licenses |
| Hosted SaaS | won't self-host | infra pass-through + $10/builder/mo | we run it, they use it |
| White-label | agencies / resellers | 30–60% margin per session | their logo, their onboarding |

## 4. The funnel
1. Free self-host tier with **15-minute demo path**: `curl | make install` -> live
   dashboard in ~90s -> "one prompt -> program + tests" wow moment.
2. Live multi-machine board is the proof-of-value (2 PCs -> visible speedup).
3. Sell Team / Hosted / White-label on top.

## 5. Build priorities (matches current work)
- Setup must be trivial (setup >> features). `eni` CLI + skillpack installer + docker.
- Demo: one-prompt -> program -> tests. (local_controller)
- Product: multiplayer server + client, merge-safe, live board, provenance ledger.
- Deployment: single Makefile install, docker compose up.
- Monetization: tenancy + licensing module now (console uses it later).
- Selling docs: README pitch + demo script + pricing one-pager + partner deck.

## 6. Notes / open questions (to tighten with LO later)
- Confirm pricing ranges feel right for target vertical (SMBs vs shops vs agencies).
- Named vs scope: "per N active builder machines" is the simplest legal unit.
- Open-source-core vs source-available: keep repo private/entrepreneurial license until
  productized; consider LATER MIT of kernel + LPGL of plugins. Don't decide today.
- Managed SaaS needs a billing provider (Stripe) + multi-tenancy (tenancy/ module).

_This file is a draft; the concrete licensing enforcement lives in ../licensing/_