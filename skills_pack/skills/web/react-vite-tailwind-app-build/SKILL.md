---
name: react-vite-tailwind-app-build
description: Boot, repair, and finish React + Vite + Tailwind web apps — fixing broken downloaded templates, the vite/lightningcss Tailwind-compile gap, restoring wiped static pages, and shipping feature-complete real-data (no fake/mock) sites. For the class of "got handed a half-broken web template, boot it and flush it out to 100%".
version: 1.0.0
tags: [web, react, vite, tailwind, build, template-repair]
---

# React + Vite + Tailwind App Build / Repair / Finish

Use when handed a downloaded or half-broken React+Vite+Tailwind project and asked to
"boot it", "tell me what this is", "flush out what's unfinished", or "make it 100% done".
Covers the build-pipeline pitfalls that trip up almost every template, plus LO's
hard product rules for shipping these sites.

## The #1 pitfall: Tailwind never compiles in `vite build`

Vite's default CSS minifier (`lightningcss`) does **NOT** process `@tailwind` or `@apply`
directives. `vite build` "succeeds" but the emitted `.css` asset still contains the literal
text `@tailwind base; @tailwind components; @tailwind utilities;` and unstyled utilities.
The app renders dark-body but all layout classes (flex/grid/card bg) are missing.

Fix — run Tailwind CLI AFTER vite build, overwriting the built asset:

    node_modules/.bin/vite build
    CSSFILE=$(ls frontend/build/assets/index-*.css)
    node_modules/.bin/tailwindcss -c ./tailwind.config.js -i ./src/index.css -o "$CSSFILE"

- Use `-c ./tailwind.config.js` (config-driven content). The CLI `--content` glob often
  misses `.tsx` files and only scans index.html, producing a near-empty stylesheet.
- Crank content paths in tailwind.config.js to `./src/**/*.{js,ts,jsx,tsx}`.
- Verify a real utility exists after compile: `grep -c 'bg-primary' $CSSFILE` should be >0.

Wrap vite + tailwind into `build.sh` so the full pipeline is one reproducible command
(check with the user before running a script when they've been cautious about it).

## `emptyOutDir: true` wipes prebuilt static pages — recreate them in `public/`

Vite's `outDir` with `emptyOutDir: true` deletes everything in the dist dir. Templates
often ship extra standalone pages (signup.html, login.html, admin.html) that live ONLY in
the prebuilt dist. After your first build they 404. Fix: recreate them under `<root>/public/`
(nginx-style), because Vite copies every file in `public/` into `outDir` on every build —
so they survive `emptyOutDir`. Keep them self-contained (inline CSS, no CDN dependency) and
POST to the real API (jwt to localStorage).

## Breaking open a downloaded template

1. Inspect: `package.json`, `server.js`, `SPEC.md`, tree. Identify backend (Express/API) vs frontend (React).
2. The zip often ships `node_modules` WITHOUT the frontend deps (react absent). Install:
   `npm i react react-dom` and `npm i -D vite @vitejs/plugin-react typescript @types/react @types/react-dom`.
3. Fix dead absolute paths in `vite.config.js` (e.g. a hardcoded `/home/nova/...` from another machine).
4. Fix corrupt JSX — common in hand-zipped templates:
   - An SVG `className="..."` opened with a double-quote but containing `${}` interpolation and a stray quote → convert to a real template literal ``className={`...${cond ? 'a' : 'b'}`}``.
   - Unbalanced closing tags ("Adjacent JSX elements must be wrapped in an enclosing tag").
   - When one component has multiple breaks, just rewrite the whole small file cleanly.
5. Rebuild in background (the terminal guard misreads `vite build` as a long-lived server — use background=true).

## shadcn `@apply` token mismatch

A shadcn-style `index.css` uses `@apply border-border;`, `bg-background`, etc. referencing
colors NOT in `tailwind.config.js` → `tailwindcss: The X class does not exist`. The CSS is
often a franken-merge of two theming systems (shadcn HSL vars + hex tokens). Fix: either add
every token to `theme.extend.colors` (e.g. `border`, `foreground`, `text-secondary`, bare
`green/yellow/purple/gray/red` used as `bg-green` etc.), or rewrite `index.css` to a clean
`@tailwind`-directives + plain body/scrollbar stylesheet and drop the broken `@apply` layers.
Map actual used utility classes via `grep -rhoE '(bg|text|border|ring|ring|bg)-[a-z]+' src`.

## Real data over fake/mock — LO's non-negotiable

- Never ship fake seed profiles, hardcoded marketing totals ("1,250+ profiles"), mock arrays,
  or `/api/placeholder` images. A real site's listing + count derive from REAL registered users.
- Build a shared in-memory store (`data/store.js`) as the single source of truth; auth/register
  writes users there; the roster = registered escort users; the frontend count = `listEscorts().length`.
- Registration must NOT auto-verify users — verification is a real manual/partner process.
- Purge dead-code files that contain fake data even if not bundled (they still pollute the repo
  before a push); confirm they're not imported first (`grep` the live import graph / the bundle).

## Feature-complete sections (no "coming soon", no placeholders)

LO wants a FULLY finished site — hunt down and remove:
- Literal "coming soon" / "comming" text and `note: 'coming soon'` placeholders (make CTA real + wired).
- Fake contact addresses like `support@example.com` (use the real domain).
- "Under construction", "not implemented", TODO/FIXME markers.
Leave form-field `placeholder="..."` hints alone (valid CSS/HTML, not unfinished content).
Verify by `grep -rniE 'coming soon|comming|example\.com|mock|lorem'` on the live source.

## Privacy-first + third-party delegation (LO's product rules)

- Platform collects ~NOTHING: no billing/card data, no ID/criminal documents, no tracking.
  Privacy policy says so plainly; only minimal account data held.
- Billing/payments and licensing/criminal background checks are handled by trusted THIRD
  PARTIES (Stripe, a licensed screening partner like CertiTrust) under their own policies;
  the platform stores only a pass/fail verification result.
- Payment model: escorts connect their OWN Stripe (Stripe Connect onboard) and get paid per
  booking; the platform earns ONLY via subscriptions. Build this with a transparent sandbox
  fallback so the flow is testable end-to-end with no keys, flipping to real Stripe when
  `STRIPE_SECRET_KEY` is set.

## Swarm pattern for heavy content builds

Fan out content-section authoring to parallel subagents (delegate_task batch), each writing an
INDEPENDENT file (e.g. `src/sections/<Name>.tsx`) with a shared design-token spec, then integrate
and wire anchors yourself. Independent files avoid merge conflicts on a single big App.tsx.
Always require "100% English, no Chinese" in the subagent context (LO hard rule).

## Verification: trust DOM, not vision

After rebuild, confirm via browser console
`getComputedStyle` + `document.getElementById(...)` presence + grep of built assets. Vision
AI on screenshots can HALLUCINATE (phantom cards/text that aren't in the DOM) — use DOM/console
checks as authoritative, not the vision description.

## Build ordering summary

server.js (backend routes + store) restart → vite build → tailwind CLI → reload → console verify.

See references/ for a worked example.
