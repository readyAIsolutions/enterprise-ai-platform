---
name: web-template-rebuild
description: Boot and finish a downloaded / discovered web application template (zip or repo) into a fully working, production-grade site. Covers un-breaking the frontend build (Vite + Tailwind), building a real data layer with no fake seed, and delivering a 100%-finished product per LO's quality bar.
tags: [web, template, rebuild, vite, tailwind, node, react, fullstack]
---

# Web Template Rebuild — boot it, then FINISH it

## When to use
User hands you a downloaded app template (zip or repo) and says "tell me what
this is and boot it", "make it a fully finished site", or "hunt down everything
unfinished". These templates ship broken: missing frontend deps, dead build
paths, uncompiled CSS, corrupt JSX, and fake/mock seed data.

LO's standing quality bar for these: 100% finished, NO "coming soon", NO fake
info/mock profiles, every feature discussed actually works. "100 is pussy shit"
— push the whole thing to done.

## Workflow

### 1. Inspect before touching
- `file` the archive; unzip; read `SPEC.md` / `SUMMARY.md` / `package.json`.
- NOTE: `node_modules/` in the zip usually has ONLY backend deps. The React
  frontend deps are frequently NOT installed — check before assuming.

### 2. Boot the backend first
- `npm install` (adds missing deps), then `node server.js` in background.
- Verify with `curl /api/health` and the API routes. Get a baseline of what works.

### 3. Make the frontend actually render
A "static" landing that shows nothing is usually a React shell whose
`index.html` references an unbuilt `/src/main.tsx`. The fix is a real build:
- Install React deps when missing: `npm i react react-dom` + dev
  `vite @vitejs/plugin-react typescript @types/react @types/react-dom`.
- Fix `vite.config.js`: these templates hardcode a dead input path like
  `/home/<other-user>/.../index.html`. Point `input` at the real index and set
  `outDir` correctly.
- Corrupt JSX (unterminated string in an SVG className, unbalanced divs) is
  common in zip dumps — just rewrite that component cleanly; don't debug It.

### 4. Vite + Tailwind — the classic two-step trap
- Under Vite 8 the CSS minifier (lightningcss) leaves `@tailwind` / `@apply`
  directives literally in the built CSS (page has dark bg but NO layout
  utilities). Tailwind is NOT run by vite.
- Fix: run the Tailwind CLI AFTER vite build, into the built asset:
  ```bash
  node_modules/.bin/vite build
  CSS=$(ls frontend/build/assets/index-*.css)
  node_modules/.bin/tailwindcss -c ./tailwind.config.js -i ./src/index.css -o "$CSS"
  ```
- If the custom-color utilities still don't generate, the CLI `--content` flag
  may only scan `index.html`. Drop `--content` and rely on the globs already in
  `tailwind.config.js` (`./src/**/*.{js,ts,jsx,tsx}`).
- `emptyOutDir: true` wipes sibling static pages (signup/login/admin) in the
  dist. Recreate them in `public/` — Vite auto-copies `public/*` into the build
  and `emptyOutDir` won't remove them. Verify with `ls frontend/build/*.html`.

### 5. Real data layer — never ship fake info (LO rule)
- Templates hardcode "1,250+ profiles"-style claims and mock arrays. Replace
  with REAL data: a shared store module (`data/store.js`) as the single source
  of truth; wire auth/registration/listing routes through it; the headline
  count becomes the real registry length. Empty roster = 0, real registrations
  increment it. No fake seed users/profiles.
- Logged-out/demo creds die when you remove fake seeds — that's expected and
  correct per LO.

### 6. Finish EVERY section and feature (LO rule)
- No "coming soon", no placeholder buttons, no `example.com` in visible copy,
  no `/api/placeholder/photo/...` image refs.
- Wire every nav/footer anchor to a real section `id`.
- Purge dead fake-data code files that aren't part of the shipped bundle
  (verify not imported first: `grep -rn "pages/" src`, and confirm the built JS
  has no reference). Keep a recovery note or the user's original zip.
- Use the swarm (delegate_task) to author independent section/component files
  in parallel — give every subagent the exact design tokens and the ENGLISH-ONLY
  rule so their output integrates.

### 7. Verify with the DOM/console, NOT vision
- `browser_console` computed styles / element counts are authoritative. This
  session's vision model HALLUCINATED cards, a phantom extra pricing tier and
  wrong text — trust `document.getElementById` presence + innerText checks, not
  the screenshot description.

## LO preferences to honor (embed in the build)
- English only everywhere.
- Privacy-first: he wants the platform to collect ~nothing; bill/process
  payment through a third party (Stripe) and delegate licensing/criminal checks
  to a licensed partner — write copy to say exactly that.
- If auth-via-Google is mentioned, it's staged AFTER the site is fully flushed;
  don't half-wire it.
- When a billing feature is requested ("escorts get paid"), model revenue
  correctly: escorts plug in their OWN payment account and get paid per
  booking; the platform earns ONLY via subscriptions. Build a sandbox Stripe
  seam that flips to real Stripe when a key is set, so the flow is testable now.

## Pitfalls
- `process(action=...)` guards flag `vite build` as a "long-lived server" — run
  it with background=true + notify_on_complete.
- npm install can get misread as a long-lived process; background it.
- After builds, re-run the Tailwind step every time (vite regenerates the css
  asset filename each build).
