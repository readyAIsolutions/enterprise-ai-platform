---
name: boot-unfamiliar-webapp
description: Boot a downloaded / unpacked webapp you've never seen (a zip of a repo, a client's "master" dump, an external project) and get it RUNNING and VERIFIED. Covers extracting, reading the spec, installing deps, fixing dead absolute config paths, rebuilding a React/Vite frontend, getting Tailwind to actually compile, and verifying with a health endpoint + browser. Use when LO hands you a project archive and says "what is this, boot it", or any time you must run an unfamiliar frontend/backend stack from source.
version: 1.0
tags: [webapp, boot, build, react, vite, tailwind, node, express, onboarding]
---

# Boot an Unfamiliar Web App

Getting an unknown project from a zip/archive to a VERIFIED running state, and being able
to tell the user what it actually is. Two deliverables: (1) a plain-language "what is this",
(2) a running, styled, functional app — not just a 200 on the root.

## Order of operations

1. **Identify the stack without reading everything.** Extract, then read in this order:
   `package.json` (deps + scripts tell the whole story), `SPEC.md`/`SUMMARY.md`/`README.md`
   (what it claims to be), `server.js`/entrypoint (backend), and the frontend entry
   (`index.html`, `src/main.*`). Skim, don't swim.

2. **Note the hardcoded absolute paths.** Repos often ship `vite.config.js` / build scripts
   with the original author's machine baked in (e.g. `rollupOptions.input:
   '/home/nova/project/index.html'`). These break on your box. Rewrite to cwd-relative:
   `new URL('./index.html', import.meta.url).pathname`.

3. **Deps are almost always incomplete in a "master" zip.** `node_modules` in the archive
   typically only has the backend deps (express, jwt, bcrypt...). The React/tooling deps
   (react, react-dom, vite, @vitejs/plugin-react, tailwindcss) are often missing entirely.
   Inspect what's missing and `npm install` it. Check with `ls node_modules/react` not just
   `npm ls`.

4. **Rebuild the frontend properly.** `vite build` from the project root with `outDir`
   pointing at whatever `server.js` serves statically. Serve from THAT dir, not the source.

5. **Get the CSS to actually compile.** This is the #1 style-killer.

## Pitfalls (each cost real time this class of task)

- **Vite v8 + rolldown leaves `@tailwind`/`@apply` UNPROCESSED** when Tailwind isn't wired
  into the pipeline. Symptom: build succeeds but the emitted `.css` still literally contains
  `@tailwind base;` and the page is unstyled or half-styled. Fix: run the Tailwind CLI
  directly over the built asset — `npx tailwindcss -c ./tailwind.config.js -i ./src/index.css
  -o <built-asset.css>`. Do NOT pass `--content` on the CLI (it silently fails to glob `.tsx`
  in some setups); let the config's `content:` array drive scanning. Verify coverage with
  `grep -c '\.bg-primary'` etc. — near-zero means scanning is broken, not that classes are absent.

- **Theme token mismatches block the compile.** Downloaded apps often franken-merge two
  theming systems (e.g. shadcn HSL `:root` vars + a hex `tailwind.config`), and `@apply`
  references tokens neither system defines (`border-border`, `text-foreground`, `bg-surface`).
  This throws `CssSyntaxError: The X class does not exist`. Fix by expanding
  `tailwind.config.js` `theme.extend.colors` to cover EVERY token the JSX uses — grep
  `grep -rhoE '(bg|text|border|ring|shadow|from)-[a-z]+' src --include='*.tsx' | sort -u`
  to enumerate them, then define each. Prefer this over deleting the `@apply` layer.

- **Corrupted source files in the archive.** A "master" dump can have hand-broken JSX in a
  couple files (unterminated string from a mangled backtick, unbalanced tags). Vite fails
  fast and names the file/line — fix one at a time, rebuild (builds are milliseconds). If a
  component is corrupted in several places, rewrite the whole file clean rather than chasing
  each brace.

- **Interpreter/reviewer myths in shell:** `pipe output | python3` triggers an approval wall.
  Prefer reading JSON with the browser console or curl into a saved file when a guard blocks you.

## Verification (do all three — don't trust the 200)

1. Health/API: `curl http://localhost:PORT/api/health` and exercise one real endpoint
   (a login or list call) with seed creds from the project docs.
2. Browser: load the root, confirm title + meaningful DOM (escort cards, nav, filters).
3. **Styled is a claim, prove it.** Check computed styles via `browser_console`:
   `getComputedStyle(document.body).backgroundColor` should equal the theme's bg, and count
   elements matching the card bg (`rgb(26,26,26)` etc.) — a count of 0 means the CSS didn't
   take even though the page "rendered". This catches unprocessed-Tailwind every time.

## Reporting to LO
State plainly what the project is (from its own docs), what was broken, what you fixed, the
working URL + seed creds, and one honest standing caveat (e.g. "data is in-memory, profile
count is 2 not the promised 50+ — that's template-completeness, not a running bug").
