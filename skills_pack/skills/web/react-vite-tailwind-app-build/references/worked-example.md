# Worked example: flushing out a half-broken downloaded React/Vite/Tailwind template

Session: booted `mycallgirl-master.zip` and pushed it to a finished, real-data, monetized site.
Steps that mattered, condensed:

## Boot sequence that worked
1. `unzip -o` → `find` tree, read `SPEC.md`, `SUMMARY.md`, `package.json`, `server.js`.
2. Identified in-memory Express API + React/Vite frontend, no DB.
3. `npm i react react-dom` + `npm i -D vite @vitejs/plugin-react typescript @types/...`
   (the zip's node_modules had NO react).
4. Fixed `vite.config.js`: dead `/home/nova/...` input path → `new URL('./index.html', import.meta.url).pathname`; `outDir: 'frontend/build'`.
5. Fixed corrupt `src/components/Dropdown.tsx`:
   - SVG `className="w-4 ... ${ isOpen ? 'rotate-180' : '' } " fill="none"` — double-quote attr can't hold `${}` → ``className={`...`}``.
   - then "Adjacent JSX elements" (extra `</div>`) → rewrote whole small file cleanly.
6. Run builds in background (terminal guard flags `vite build` as a long-lived server).

## Tailwind gap (the big one)
- `vite build` produced CSS still containing literal `@tailwind base;@tailwind components;@tailwind utilities;`.
- `tailwindcss -c ./tailwind.config.js -i ./src/index.css -o <built asset>` (config-driven content,
  NOT CLI `--content` which only scanned index.html) → 0.37KB → 40KB, utilities present.
- `@apply border-border` failed because `border` color wasn't in `theme.extend.colors` → added
  `border`, `text-secondary`, bare `green/yellow/purple/gray/red`, `surface`.

## emptyOutDir wiped static pages
- After build, `/signup.html` & `/login.html` 404 — they'd lived only in the prebuilt dist.
- Recreated as self-contained pages under `public/` → vite copies them into outDir each build.
- Form posts to `/api/auth/register` & `/api/auth/login`, JWT → localStorage.

## Real data layer
- `data/store.js`: `users[]` + `profiles` map + `listEscorts()` (roster from REAL registered
  escort users). Auth/register wrote there; `/api/escorts` returned `listEscorts()`; frontend
  count = `total`. Hardcoded "1,250+ profiles" replaced with live total.
- Registration sets `verificationStatus:'pending'` (never auto-verified).

## Verification + payments (third-party delegation)
- `data/screening.js` verification record: identity/photo/references/criminal/license; admin
  records stage results; licensed partner name surfaced in copy.
- `services/stripe.js`: sandbox fallback when no `STRIPE_SECRET_KEY`, real Stripe Connect when set.
- `/api/stripe/onboard` (escort connects own Stripe), `/api/bookings` pays the escort's connected
  account, `/api/stripe/subscribe` is the ONLY platform revenue (VIP $29 / Escort Pro $19).

## Content via swarm
- delegate_task batch → 6 subagents wrote independent `src/sections/*.tsx` (HowItWorksSafety,
  ReviewsPricing, ForEscorts, FaqContact, Legal, VerificationWhy) + 3 `src/components/*`
  (BookingModal, StripeConnect, SubscribePanel). Integrated anchors/imports myself.

## Finish sweep
- `grep -rniE 'coming soon|comming|example.com|mock|placeholder|lorem'` → fixed pricing
  "coming soon" (made live with real prices + API wiring), `support@example.com` → real domain.
- Purged dead fake-data code (`src/pages/*`, `ClientApp.tsx`, `components/App.tsx`,
  `MediaUploader.tsx`) after confirming they weren't imported/bundled.
- Verified via browser console `getComputedStyle` + element presence + asset grep (vision AI
  hallucinated a phantom plan card — DOM was authoritative).

## Privacy policy (LO stance)
- Platform collects ~nothing; no billing/ID/criminal data; billing = Stripe, licensing/checks =
  licensed third party; only essential cookies; delete-on-request.
