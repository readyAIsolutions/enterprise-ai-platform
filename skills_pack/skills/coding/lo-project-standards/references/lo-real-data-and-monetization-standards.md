# LO's Real-Data, Privacy & Monetization Standards (do NOT violate)

Hard preferences LO stated for building web products. Violating these = instant correction.

## 1. NEVER fill with fake data
- No seed/mock user profiles, no fake escort/client arrays, no fabricated stats or counts.
- A number like "1,250+ profiles across Canada" must NOT be hardcoded marketing candy — it must be a
  **real tally** derived from actual registered users (e.g. `GET /api/escorts -> total`).
- Store data through a single shared store keyed on real registrations; the roster is built from
  users who actually signed up. Empty is honest — show an empty state ("be the first to join"), not invented profiles.
- Verification status is a real, manual process — never auto-approve new accounts.

## 2. Privacy-first: collect ~nothing
- The platform should claim it collects almost nothing: an email + user-published profile content.
- No phone number required, no billing/payment data, no ID/criminal/medical documents stored by the platform.
- No ad/tracking/device profiling; essential cookies only.
- Put this plainly in the Privacy Policy ("we don't collect any of that shit").

## 3. Billing & licensing delegated to THIRD PARTIES
- Licensing, identity, and criminal background checks → licensed 3rd-party partner
  (e.g. "CertiTrust Background Screening"). Partner handles the sensitive data; platform only shows a
  pass/fail verification badge. Platform does NOT receive/store ID or record documents.
- Payments → payment processor (e.g. Stripe). Platform never sees card/bank details.

## 4. A logical revenue model (escorts paid via their OWN Stripe)
LO will NOT configure Stripe keys for escorts. Correct model:
- Each ESCORT connects their OWN Stripe (Stripe Connect / connected account) → receives booking
  payouts directly. Platform touches no booking money.
- The PLATFORM earns ONLY when people buy **subscriptions** (its own Stripe account).
- Build a clean sandbox fallback: no STRIPE_SECRET_KEY set → return deterministic `sandbox:true`
  results so the whole flow (onboard → connect → pay → subscribe) works end-to-end offline;
  it flips to real Stripe automatically when a key is present. Never block the feature on a missing key.

## 5. "Swarm it"
For large feature/content builds LO expects fan-out across parallel subagents (delegate_task): one
self-contained component/file per worker to avoid merge conflicts, then integrate.
