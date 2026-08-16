---
name: vite-react-tailwind-boot
description: Boot, finish, and ship a Vite + React + Tailwind + Express web project pulled from a download/export (zip, repo clone, template). Covers the breakages that make these apps fail to render — Vite 8/lightningcss leaving Tailwind directives unprocessed, dead hardcoded vite input paths, corrupt JSX, emptyOutDir wiping static pages — plus the real-data refactor and swarm content-authoring patterns that turn a fake-seeded template into a working product. Use whenever handed an existing frontend project that won't build/run or is loaded with mock data.
version: 1.0.0
category: web
tags: [vite, react, tailwind, express, build, boot, template, lightningcss, swarm]
---

# Vite + React + Tailwind Web Project Boot

Pattern for taking a half-baked, downloaded/exported web template and getting it to
**build, render, and behave like a real product**. These projects ship broken in
predictable, repeatable ways — the fixes below are the class-level playbook.

## When to use
- You're given a `project-master.zip` / repo / template and told to "boot it" or "finish it".
- A React page loads blank or unstyled even though the API returns data.
- A project is filled with **mock/fake data** and the user wants it to reflect real registered users (often: "that number should be a real tally of users when live").

## Boot sequence (the fast path)
1. **Inspect**: read `package.json`, the entry `index.html`, the main `src/*.tsx`, and the vite config FIRST. `find . -maxdepth 2 -not -path '*/node_modules/*'` before anything.
2. **Install frontend deps** — downloaded zips often ship only the *backend* node_modules, or none:
   `npm install react react-dom` then `npm install -D vite @vitejs/plugin-react typescript @types/react @types/react-dom` + `tailwindcss@3 postcss autoprefixer`.
3. **Fix the vite config** (see pitfalls): dead hardcoded input path, wrong outDir.
4. **Fix corrupt JSX** (the source may not even parse — see pitfalls).
5. **Build, then compile Tailwind AFTER vite** (see the big pitfall below).
6. **Restore wiped static pages** into `public/`.
7. **Verify** with `curl /api/health`, a browser load, then a computed-style check (not just assumptions).

## PITFALL — Vite 8 doesn't compile Tailwind (the #1 silent killer)
With modern Vite (rolldown/lightningcss), `vite build` does **NOT** expand `@tailwind`
directives. You'll see `[lightningcss minify] Unknown at rule: @apply / @tailwind`
warnings and the emitted `.css` asset will **literally contain `@tailwind base;...`**
unprocessed (0.3–4KB instead of tens of KB) → the page is unstyled/bare.
**Fix: run the Tailwind CLI against the emitted asset AFTER every vite build:**
```bash
CSSFILE=$(ls frontend/build/assets/index-*.css)
node_modules/.bin/tailwindcss -c ./tailwind.config.js -i ./src/index.css -o "$CSSFILE"
```
Wire both steps into a `build.sh` so a single command reproduces a shipped dist.

## PITFALL — Tailwind CLI `--content` flag missed the source
Passing `--content "./src/**/*.{js,ts,jsx,tsx}"` on the CLI only generated classes from
`index.html`, not the TSX. **Rely on the `content:` array in `tailwind.config.js`**
and invoke with `-c ./tailwind.config.js` (no `--content` flag). Verify class coverage
afterwards: `grep -c '\.bg-primary' <out.css>`.

## PITFALL — mismatched theming / un-resolvable tokens
Templates often franken-merge two systems (shadcn HSL vars + hex tokens). `@apply`
fails with "class does not exist" for tokens like `border-border`. Fix by either adding
the missing color tokens to `tailwind.config.js` `theme.extend.colors`, or rewriting
`src/index.css` as a clean stylesheet and removing broken `@apply` component layers.
Grep the source for which `bg-/text-/border-/ring-*` tokens are REALLY used, then make
the config cover exactly those.

## PITFALL — vite `emptyOutDir` wipes static HTML pages
If you point `outDir` at the served static folder and set `emptyOutDir: true`, any
standalone `.html` pages (signup/login/admin) living there get deleted. Vite copies
everything under `public/` into the build output automatically — **put static pages in
`public/`, not in the outDir**, so they survive rebuilds.

## PITFALL — corrupt JSX in shipped source
Templates ship files that don't even parse: a JSX attribute opened with a `"` but
containing `${}` interpolation and a stray quote, or unbalanced `</div>` counts.
Symptoms: `Unterminated string`, `Adjacent JSX elements must be wrapped in an enclosing
tag`. Don't patch around it — **rewrite the whole file cleanly** and iterate (build is
fast, ~100ms).

## Real-data refactor (killing fake/mock data)
When the user says the platform is full of fake profiles/numbers and the "1,250+"
should be a real tally:
- Introduce a **shared in-memory store module** (`data/store.js`) as the single source of
  truth: `users[]` + `profiles Map` + helpers (`listEscorts()`, `upsertProfile`, `findUser*`).
  Every route reads/writes through it — this module is the seam where a real DB plugs in later.
- **Never seed fake data.** The roster is built from real registered users. Registration
  pushes to the store; listing derives from it. Empty store ⇒ empty-correct tally.
- Auth route: drop the seed array, `const users = store.users` (same live reference).
- Verification/trust: build a real per-stage pipeline (identity / photo / references /
  criminal background / license) with a **licensed third-party screening partner** seam
  (`data/screening.js`), results recorded by authorised admin — nothing auto-approved.
- Fake-profile/abuse detection: a `data/moderation.js` that scores real profiles on honest
  heuristics (no photo, no media, unverified, no/too-short bio, brand-new account,
  off-platform link, no rates) and surfaces flags to admin. Never fabricates, never auto-bans.

## Swarm content-authoring pattern
To write many content sections fast without file conflicts:
- Give each subagent **one independent file** (`src/sections/<Name>.tsx`, default-export,
  self-contained, only imports react) produced to a **shared design spec** (exact Tailwind
  tokens, container pattern, section `id`s, English-only rule).
- Fan out via `delegate_task` batch (file toolset), then the parent **assembles** them into
  the shell App and wires nav/footer anchors to the section `id`s.
- Verify all sections resolve in the browser (`document.getElementById(...)` for each id).

## Verify before declaring done
- `curl /api/health`, hit every new API route with real requests (register → appears in
  roster → verify → badges).
- Browser: check `browser_snapshot` has the sections, then a **computed-style** probe
  (body/card `backgroundColor`, not just DOM presence) to confirm Tailwind actually applied.
- Confirm the displayed count is from `data.total`, not a hardcoded string.

See `references/vite-react-tailwind-boot.md` for a concrete end-to-end walkthrough.
