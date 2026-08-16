# Stripe Real Checkout (Starlette + sqlite) — pattern

Replaces a mock checkout that used to `status='paid'` on any POST.
Core rule: **the server never marks an order paid on its own — Stripe confirms it.**

## Setup
- `pip install --break-system-packages stripe` (PEP-668 externally-managed env; the
  systemd/system-python service needs it imported). Verify `import stripe`.
- Config keys (via `config.py` → DB settings, one source of truth):
  `STRIPE_SECRET_KEY→stripe_secret_key`, `STRIPE_PUBLISHABLE_KEY→stripe_publishable_key`,
  `STRIPE_WEBHOOK_SECRET→stripe_webhook_secret`, `STRIPE_CURRENCY→stripe_currency` (USD).
- DB: add `stripe_session_id`, `stripe_payment_id` columns to `orders` (idempotent migration
  in `_migrate`).

## Checkout flow (paid item)
1. Validate beatpack + email. `price<=0` → create order as `paid`, return `download_url`
   directly (genuinely free, no Stripe).
2. Paid → **require** a configured secret key; if absent return `400 "Payments aren't connected yet"`
   (never fake success).
3. Create `stripe.checkout.Session.create(mode="payment", customer_email=..., line_items=[...])`.
   - `unit_amount = int(round(price*100))` (cents).
   - `success_url = f"{SITE}/beatpack/order/{token}?session_id={{CHECKOUT_SESSION_ID}}"`.
   - `cancel_url = f"{SITE}/beatpack/{slug}"`.
   - `client_reference_id = order_id` + `metadata`.
4. Store `stripe_session_id`, return `{ok:true, checkout_url: session.url}`; front-end
   redirects there (JS: prefer `checkout_url`, fall back to `download_url`).

## Confirming payment (two paths)
- **On-return**: in the download endpoint, if order still pending + has session_id,
  `checkout.Session.retrieve(session_id)`; if `payment_status=='paid'` → mark paid, add
  subscriber, then serve file. If not paid → return 402.
- **Webhook** `/stripe/webhook` (POST): read body + `stripe-signature` header,
  `stripe.Webhook.construct_event(payload, sig, whsec)`. On `checkout.session.completed`,
  resolve order by metadata/client_reference_id or session_id, mark paid. 400 if whsec unset/bad sig.
- Admin manual "Mark paid" kept as an explicit override for offline/outside-Stripe payments
  (with a confirm warning), separate from automated Stripe confirmation.

## Front-end (app.js)
`fetch('/beatpack/checkout', POST)`: if `json.ok` → `checkout_url ? location=checkout_url : location=download_url`;
else show `json.error`.

## Tests (regression)
- `test_no_fake_stripe_orders_when_not_configured`: paid beatpack POST when Stripe off →
  400, and **no order created / none marked paid**.
- `test_free_beatpack_downloads_without_payment`: price=0 → 200 + download_url.

## Admin UI
- Admin → Settings → Stripe: secret/publishable/webhook/currency fields (POST to the same
  settings route; expose keys in the `_site()` dict so the template can show "Stripe connected").
- Orders table: show beatpack title (join), amount w/ currency, status badge, and a Stripe
  payment marker when `stripe_session_id` is set.
