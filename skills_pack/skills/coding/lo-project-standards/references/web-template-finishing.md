# Booting / finishing a downloaded or half-broken web template (React+Vite+Tailwind)

Reusable runbook for taking a "master.zip"-style web template and getting it to a polished, working,
production-shaped build. Hit these exact pitfalls repeatedly on LO builds.

## 1. Extract & inspect first
- `unzip` into an inspect dir; read package.json, SUMMARY.md, SPEC.md, server.js, vite config, .env.
- The zip's `node_modules` often ships only backend deps (express/stripe) with NO React → the React
  source exists but was never built. `npm install react react-dom` + `-D vite @vitejs/plugin-react typescript @types/react @types/react-dom`.

## 2. Fix the stale Vite config before building
- Template `vite.config.js` hardcodes another machine's path (e.g. `/home/nova/mycallgirl.ca/index.html`).
  Repoint: `rollupOptions.input` to the local index.html or drop it; `build.outDir` to the served static dir.
- `emptyOutDir: true` WIPES the prebuilt static HTML (signup/login/admin). Keep real, needed pages under
  `public/` — Vite auto-copies `public/*` into `outDir` on every build.

## 3. Corrupt JSX is common in these templates
- "Unterminated string" / "Adjacent JSX elements must be wrapped" errors = broken hand-edit.
  Fix directly: a JSX attribute opened with `"` but containing `${}` interpolation and a stray `"`
  becomes a template literal: `className={`...${cond ? 'a' : 'b'}`}`. Rebalance mismatched divs.
  When a file has 2+ corruption sites, rewrite the whole component cleanly instead of patching piecemeal.

## 4. Tailwind that never compiled (very common)
- Symptom: built CSS asset still literally contains `@tailwind base; …` / `@apply` and is ~0.4KB,
  so utility classes don't exist and the page is unstyled (dark body maybe, no layout).
- Fix: run the Tailwind CLI AFTER `vite build` and OVERWRITE the built CSS asset:
  `CSSFILE=$(ls frontend/build/assets/index-*.css) && npx tailwindcss -c ./tailwind.config.js -i ./src/index.css -o "$CSSFILE"`
- If `npx tailwindcss … --content ./src/**/*.{ts,tsx}` finds nothing, the CLI `--content` flag missed;
  rely on `tailwind.config.js` `content` instead (run with `-c ./tailwind.config.js`, no --content flags).
- Template often franken-merges two themes (shadcn HSL `:root` vars + hex tokens). Rewrite index.css clean
  to `@tailwind` directives + body colors and expand tailwind.config `colors` to cover EVERY utility token
  the JSX actually uses (`border-border` needs a `border` color token, etc.).
- `vite build` triggers a false "long-lived process" guard → run it via terminal background=true.

## 5. Real data over mock
- Templates ship hardcoded mock arrays and fake counts. Replace with a shared `data/store.js` and route
  reads through it; the frontend fetches `/api/escorts` and shows the live `total`.

## 6. Verification of a finished boot
- `/api/health` 200; runtime register → appears in roster; an end-to-end curl/inline-python test through
  the full business flow; browser console asserts section `id`s, dynamic count, and computed styles
  (body `#0a0a0a`, cards `#1a1a1a`). Write a STATUS file with a PASS/FAIL evidence board.
