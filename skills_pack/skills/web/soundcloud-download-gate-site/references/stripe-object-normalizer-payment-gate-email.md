# Stripe object normalization, payment fulfillment, login-gate whitelisting, email + font lessons (Aug 2026)

Condensed hard-won lessons from hardening an AC PE$0-style gate site. All durable patterns — reuse the fix, don't re-diagnose.

## 1. Stripe lib v15: StripeObject has NO `.get()` → 500s everywhere
The installed `stripe` lib (v15.x) returns `_stripe_object.StripeObject` for API reads. It supports `obj["key"]` and `obj.to_dict()` but **NOT `.get()`** (calling `.get()` raises `AttributeError`). Any stripe read that did `obj.get(...)` crashed.

Impact (one bug → many symptoms):
- `POST /stripe/webhook` → **500** every time (so paid Stripe sessions never flipped site orders to `paid`).
- `_confirm_stripe_payment` (return-to-merchant path) crashed → orders stuck `pending` forever.
- Beatpack product auto-sync crashed → `stripe_product_id/price_id` never persisted → product absent/unlinked in the Stripe catalog.

Log signature: `POST /stripe/webhook 500` + a traceback through `_stripe_object.py` ending in `KeyError: 'get'` / `AttributeError: get`.

Fix — normalize at the edge of every Stripe read:
```python
def _sd(obj):
    if isinstance(obj, dict):        return {k: _sd(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)): return [_sd(v) for v in obj]
    if hasattr(obj, "to_dict_recursive"): return obj.to_dict_recursive()
    if hasattr(obj, "to_dict"):        return _sd(obj.to_dict())   # v15 uses to_dict()
    return obj
```
Wrap: `sess = _sd(stripe_pay.checkout.Session.retrieve(...))`, `sess = _sd(event["data"]["object"])`, `existing = _sd(stripe_pay.Price.list(...))`. Then existing `.get()` code works. Regression test: fake object with `__getitem__`, `.to_dict()`, but NO `.get()` — prove `_confirm_stripe_payment` flips an order to paid through it.

Because `db.get_setting()` JSON-decodes (strips quotes), a setting stored as `'"sk_..."'` is fine for the app but **invalid if passed raw to an API** — always test Stripe with the app's parsed value, not a raw SQL read.

## 2. Stripe receipt email
Add `payment_intent_data={"receipt_email": email}` to every checkout `Session.create` so Stripe emails the buyer a receipt on payment. The master "send receipts" toggle is in Stripe Dashboard Settings → Emails (not reliably API-controllable). Separately, ship your own delivery email so the buyer always gets the product regardless.

## 3. Owned-state on the paid beatpack page
`beatpack_page` previously never checked ownership → always rendered the "Get the pack" checkout form even for returning owners. Add `_fan_owns_beatpack(fan, bp_id)` → `(owns, dl_url)` returning True only for a **paid** order (match by fan_id or email), using the order's secret-token download URL. Template: when `owns`, render a green "✓ You already own this pack. Stripe confirmed your purchase." block with a "Download your pack" button instead of the checkout form.

## 4. Login-gate whitelisting (don't wall off the download ecosystem)
`_LoginGate` middleware: a `_PUBLIC_PATH_PREFIXES` set checked FIRST (passes straight through), then a `_PROTECTED_PAGE_PREFIXES` set (anonymous → 303 `/login`). Pitfalls discovered:
- SoundCloud "Free DL" buy-links point to `/release/{slug}`. If that's in protected, clicking a Free-DL link bounces fans into the login page instead of the download gate. The LIKE/COMMENT/FOLLOW gate (not a login screen) is the real engagement. Make the whole free-download/content flow public: `/releases`, `/release/*`, `/g/*`, `/free-for-profit`, `/download/*`, `/press/*`, `/blog`, plus home `/`.
- Post-payment order URL `/beatpack/order/{token}` MUST be public: the unguessable `download_token` is itself the credential, and payment is re-confirmed server-side, so a just-paid guest must be able to fetch the file without a login bounce.
- Keep genuinely identity functions gated: paid storefront `/beatpacks*`, personal analyzer, community chat, `/history`.

## 5. Gmail attachments cap at ~25MB
Attach the product file only when `len(data) <= ~24MB`; otherwise (and always for safety) include a personal download-link button (`/beatpack/order/{token}`). Never email-attach a 60MB zip — it fails. `gmailapi.build_message/send` accept `attachments=[(filename, bytes)]` (add `MIMEApplication` import).

## 6. SoundCloud repost API is dead → owner-approved manual fallback
v1 `POST /me/track_reposts/{id}` is decommissioned (→ `405 unknown route`); v2 is blocked from server-side. Like/comment/follow still auto-verify. The user explicitly authorized ("make repost work idc how"): attempt the real repost; when SC won't confirm, **accept the step (manual self-confirm)** so the gate never stalls — mark `ok=True` + `method="manual"`, keep `verified_against_soundcloud` honest (False), and complete the step so `all_complete` unlocks. Frontend shows the server's `data.msg` (per-case: auto vs manual).

## 7. Email HTML rendering (no button-overlap blob)
Don't build the CTA as a padded inline `<a>` containing a long product title — in many clients it becomes a huge wrapping red blob that overlaps the text. Use a clean single-column card: header bar strip, heading (product title here), short spaced paragraphs, then a **full-width block button** `display:block; text-align:center; padding:15px 20px` with a short label ("DOWNLOAD YOUR PACK"). All inline styles (email-safe), no web fonts needed.

## 8. Fonts: brand wordmark vs nav buttons (readability)
When a user says "the top buttons are unreadable with this font change," audit EVERY top-bar element, not just the one you changed. A blackletter/display-brand font looks cool large (hero splash, wordmark) but is **illegible on small nav buttons**, especially with `text-transform:uppercase`, tight `letter-spacing`, and a blurry `text-shadow` glow (that was the actual synth-nav culprit). Rule: decorative/blackletter OK for the brand wordmark + hero, but nav links/CTA buttons go in a readable geometric sans (Space Grotesk / Inter / Anton), normal case, no text-glow blur.

## 9. Front-page text is owner-owned & permanent
Tagline/hero/OG text: the site owner controls it via the Admin "Save front page text" form; the save handler must treat **blank = keep current** (never write `''` over a blank box → that resets to the template fallback and looks like the site "changed my text"). Nothing should auto-edit/regenerate front-page copy.
