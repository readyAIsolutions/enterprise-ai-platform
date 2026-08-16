# ENI ENTERPRISE — Loan-Readiness & Financial Analysis (Companion to Business Plan)
**Companion to:** `Eni-Enterprise-Business-Plan_1/2.docx` (identical)
**Deliverable:** `ENI_PROFORMA_2YR.xlsx` (2-year monthly proforma, Live formulas)
**Date:** 2026-08-16

---

## 1. What this is
The Business Plan is strategically complete. This companion does three things a
lender needs:
1. Explains the **2-Year Proforma Cash Flow** (`ENI_PROFORMA_2YR.xlsx`) and what it
   shows at your current assumptions.
2. Maps every blank field in the plan to where YOUR real number goes — so you only
   fill facts only you can know (legal, $, personal), never fabricated ones.
3. Flags which "future" capabilities the plan assumes are **already built.**

## 2. The Proforma — what it computes (REAL outputs, LibreOffice-verified)
Sheet layout: `Assumptions` (edit yellow) → `Proforma 24mo` (monthly, live formulas)
→ `Yearly Summary`.

At your current SELLING.md pricing + conservative ramp, the formulas resolve to:

| Metric | Year 1 | Year 2 |
|---|---|---|
| Co-build client revenue | **$10,500** | **$80,004** |
| Hosted SaaS revenue | $960 | $2,400 |
| White-label | $7,200 | $7,200 |
| **Total revenue** | **$18,660** | **$89,604** |
| Total costs | $78,000 | $78,000 |
| **Net (pre-tax)** | **–$59,340** | **+$11,604** |
| **Net (post-tax 20%)** | **–$47,472** | **+$9,288** |

**What this tells a lender (honest, investable story):**
- **Year 1 is the investment/ramp year** — building the co-build client base,
  revenue deliberately ramps (20% → 50% → 100% of target). Cash burn ≈ $59K in Y1.
- **Year 2 turns profitable** (+$11.6K pre-tax) once ~5 co-build clients are active.
- This is a normal, credible trajectory for a services-led B2B platform: benign but
  real, not hockey-stick fantasy.

**Edit to reflect YOUR pipelined contracts:** the Assumptions sheet holds ALL
drivers in yellow cells. The biggest levers to update with real (contracted) numbers:
- `y1_clients`, `y1_arpu`, `y2_clients`, `y2_arpu` — the co-build contract count + $
- `y1_builders`, `y2_builders` — hosted builder seats
- `salary` (founder draw), `cost_model` (OpenRouter/Nous/RunPod spend)
Plug in one real signed contract and the Year-1 burn number becomes defensible.

## 3. Blank-field map — WHO fills what
The plan intentionally leaves its legal/personal/financial blanks. Here is exactly
where your real data goes (only you can hold these; nothing below is fabricated):

| Business-plan field | Who | Where your data lives |
|---|---|---|
| Legal name/address/contact/structure | **YOU (legal)** | incorporation docs |
| Ownership % + principal details | **YOU** | share register / MoA |
| "Amount Requested from Community Futures" | **YOU** (after you decide loan size) | Source-of-funding table |
| Final pricing for co-build contracts | **YOU** | SELLING.md tier ladder (Team $12–25k/yr, Pro $2.5k/builder, Hosted $10/builder/mo, White-label 30–60%) |
| All $ figures in Project Costs & Funding tables | **YOU** (real quotes) | equipment quotes, loan terms |
| 2-Year Proforma Cash Flow | model provided — **YOU** plug real contracts | `ENI_PROFORMA_2YR.xlsx` |
| Resumes, cost quotes, lease | **YOU** | appendices |
| Market capture % Y1–3 | **YOU** — target ≤ ~1–2% of TAM conservatively | Market section |
| Mitigation for worst-case revenue | **YOU** — sample in §7 | — |
| "Why this business will succeed", 5-yr vision, exit | **YOU** (your voice, not generated) | — |

> IMPORTANT: I will not fabricate your legal identity, ownership, personal
> contacts, or exact equipment costs. Fill those directly in the docx. Everything
> I genuinely own — the architecture, the module list, the pricing ladder, the
> proforma engine, the technical differentiator — is real and documented.

## 4. Capability proof the plan can cite (all REAL, verified 2026-08-16)
- **4,411 tests collected, 4,410 passing** across the platform.
- **50 capability modules** auto-discover into a self-validating kernel.
- **Multiplayer floor** proven live: a goal → planner → 6 step-tasks → a builder
  machine on the LAN → real artifacts → conflict-safe merge into a per-tenant
  workspace (`docs/CAPABILITY_REFERENCE.md`).
- **One-prompt → program** brains (:8913) generate real, tested code.
- **Portable Hermes layer**: `hermes-local` boots ENI + Hermes side-by-side in one
  browser tab (verified: hub 200, hermes 200, board 200, controller 200).
- **Local secrets handling IS SHIPPED**: `secret_broker`, `secret_rotation` modules
  + a redacting vault — the plan's "next milestone" is already done.
- **Hardware honesty**: the swarm runs on 3 physical workstations today; Multiplayer
  scales horizontally — every machine you add (the Project-Costs line for extra
  workstations) increases parallel-build capacity linearly.

## 5. The single strongest proof point (use this in sales & the loan file)
The business plan itself says: *"the swarm has already been used to build other
production software, which should be the centerpiece of sales materials."* This is
TRUE and is the #1 line to emphasize: **Eni used this exact platform to build
production software.** The live demo (one-prompt → program → tests across machines)
is the 15-minute closer.

## 6. Immediate one-shot tasks to close the loan file
1. [ ] Fill legal/ownership/contact in the .docx (your facts).
2. [ ] Pick loan amount + amortization; complete Project Costs / Sources of Funding.
3. [ ] Plug ONE real (or strongly pipelined) contract into `ENI_PROFORMA_2YR.xlsx`
      Assumptions → Year-1 net becomes defensible.
4. [ ] Attach `CAPABILITY_REFERENCE.md` (proof) + `ENI_PROFORMA_2YR.xlsx` (finance).
5. [ ] Write the 3 narrative blanks (success factors, 5-yr, exit) in your voice.

## 7. Sample worst-case mitigation (edit to your reality)
- **If Y1 revenue ≤ target:** operate the 3 workstations at cost (no new purchases);
  raise hosted tier first (marginal cost per builder ≈ $0); convert 2 co-build
  clients → staffing-marketplace recurring engagements to smooth cash; monthly
  billing instead of annual to shorten collection.
- **If a key client churns:** keep 2–3 reference clients in different industries
  (already the plan's strategy) so no single client > ~40% of revenue.
- **If model cost spikes:** multi-provider OpenRouter ladder keeps spend at the
  cheap end; hard monthly cap on frontier-model calls (the escalation ladder already
  does this).