# Stripe v15 ".get()" break, payment flow gotchas, email delivery

Session-derived (2026-08-02) — class-level pitfalls for the Stripe storefront
side of the download-gate site.

## 1. Stripe v15 returns StripeObject WITHOUT `.get()` — the #1 silent breaker
- Stripe Python lib bumped to v15.4.0. API reads return `_stripe_object.StripeObject`
  (class `stripe.checkout._session.Session`, etc.).
- A StripeObject supports `obj["key"]` and `obj.to_dict()` but **NOT** `obj.get()`.
  Calling `.get()` raises `AttributeError` (surfaced as a confusing
  `KeyError: 'get'` inside `_stripe_object.__getattr__` / `__getitem__`).
- Check which method exists: `hasattr(obj,'to_dict_recursive')` (older) vs
  **`hasattr(obj,'to_dict')`** (v15). v15 has only `.to_dict()`.
- Symptom this causes: every Stripe read path that used `sess.get(...)` crashes
  with HTTP **500**. The Stripe **webhook fires but returns 500**, so orders never
  flip to `paid`; `_confirm_stripe_payment` and the product auto-sync also crash.
- Tell-tale: buyer paid on Stripe (`payment_status=paid` on the Session) but the
  site order stays `pending`, nothing recorded in "My purchases", no email sent,
  and the product never links into the Stripe catalog.

### Fix: a single `_sd()` normalizer at the edge of every Stripe read
```python
def _sd(obj):
    if isinstance(obj, dict):
        return {k: _sd(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sd(v) for v in obj]
    if hasattr(obj, "to_dict_recursive"):
        return obj.to_dict_recursive()
    if hasattr(obj, "to_dict"):
        return _sd(obj.to_dict())   # stripe v15
    return obj
```
Wrap every Stripe object read: `sess = _sd(stripe_pay.checkout.Session.retrieve(...))`,
`existing = _sd(stripe_pay.Price.list(...))`, `sess = _sd(event["data"]["object"])`
in the webhook. Then the rest of the code can keep using `.get()`.
Regression test: fake a `_RealLikeStripeObj` that supports `[]` and `to_dict()`
but raises on `.get()`, feed it to `_confirm_stripe_payment`, assert the order
flips to paid. Also verify the real method name (`to_dict` not `to_dict_recursive`)
before shipping the normalizer.

## 2. Members-only login gate must whitelist payment success/order URLs
- The site is members-only (anonymous → `/login` via a middleware gate). A guest
  pays on Stripe (no site login needed), then Stripe redirects to
  `success_url = {site}/beatpack/order/{token}?session_id=...`.
- That path is under the protected `/beatpack/` prefix by substring match, so the
  returning guest got bounced to `/login` — "purchase redirect doesn't work".
- Fix: add `/beatpack/order/` to the PUBLIC path-prefix whitelist, BEFORE the
  protected `/beatpack/` check (public is checked first). Safe because the path
  is keyed by an unguessable `download_token` and payment is re-verified server-side.
- If you add any route a guest must reach (payment return, download by token,
  unauthenticated webhook/checkout POST), it must be on the public prefix or it
  will 303 to login mid-flow.

## 3. Owned-state on product pages (buy button keeps appearing)
- `beatpack_page` must detect whether the logged-in fan already has a **paid**
  order for that pack (match by `fan_id` OR by `email`) and pass `owns`/`dl_url`
  to the template; otherwise the template always shows the checkout form even
  after Stripe confirms.
- Pattern: `_fan_owns_beatpack(fan, bid)` returns `(owns, /beatpack/order/{token})`
  from a `status == "paid"` order. Owners see a green "✓ You already own this pack"
  + a **Download your pack** button; non-owners see the buy form. Only show it
  once the order is actually `paid` (flipped by the webhook), never on `pending`.
- Same idea works for any gated product page: don't re-ask for payment once confirmed.

## 4. Gmail attachment cap (25MB) → download-link fallback
- Gmail API rejects attachments over ~25MB. A beatpack can be 60MB.
- In `_email_beatpack_to_buyer`: attach the file ONLY if `len(data) <= 24*1024*1024`;
  ALWAYS include a personal download link (`/beatpack/order/{token}`, public after
  payment) with a big red `DOWNLOAD YOUR PACK` button so the buyer can always grab it.
- Add attachment support to the mailer: `gmailapi.send(to, subj, html, cfg, db,
  attachments=[(filename, bytes)])` → build a `MIMEMultipart("mixed")` with an inner
  `MIMEMultipart("alternative")` body + `MIMEApplication` parts.

## 5. Stripe receipt email
- To get Stripe to email a receipt to the buyer, set
  `payment_intent_data={"receipt_email": email}` on `checkout.Session.create`
  (both the catalog-price and inline-price_data branches).
- The master "send receipts" toggle lives in Stripe Dashboard → Settings → Emails —
  outside API control; mention this to the owner if receipts still don't arrive.

## 6. Email HTML: avoid the overlapping-button blob
- Pitfall: an inline `<a>` with `padding:...` whose label is the LONG pack title
  renders as a giant wrapping red block that overlaps surrounding text.
- Fix: clean single-column card — red header bar, pack title in the `<h2>` (not in
  the button), and a **`display:block; text-align:center;`** button labeled short
  ("DOWNLOAD YOUR PACK"), with its own row + margins above/below. Build and
  MIME-parse in a test to assert exactly one block button and no inline-pill.
