# Runnable Full-Stack Monorepo Recipe (LO "fully complete" builds)

When LO says **"fully complete the program, no next step, fully finished next time
you stop"** (or any variant of "use ALL parts / full power / complete the whole
thing"), he wants a RUNNABLE, VERIFIED product in one autonomous pass — not
docs/spec plus a "next step" handoff. Verified = `pnpm install` succeeds, the
server boots, tests pass, and you actually ran it.

## Ground rules for this mode
- Do NOT stop to ask for confirmation or hand back "ready for next phase."
- Build the ENTIRE thing: packages + backend + frontend + Docker + CI + tests.
- Install deps, run the server, hit the endpoints, run the test suites, FIX what
  breaks, then report. LO's bar is "finished," not "scaffolded."
- Docs/specs are a deliverable, but only as part of the runnable product — the
  code must exist and run.

## Proven one-session stack (Node 22 + pnpm 9 workspace)
This stack installs cleanly and verifies end-to-end. Faster/leaner than pretending
a 16-microservice k8s platform exists.

```
pnpm-workspace.yaml            # packages: apps/* services/* packages/*
turbo.json                     # build/dev/test pipelines
tsconfig.base.json             # strict shared config
biome.json                     # lint/format

packages/shared/               # @ciphersphere/shared — zod schemas + domain types + role/permission matrix
packages/crypto/               # @ciphersphere/crypto — Web Crypto AES-GCM, HKDF-SHA256, JWT HS256 (browser+node)
packages/design-system/        # @ciphersphere/design-system — tokens.css (CSS vars) + React components
services/api/                  # @ciphersphere/api — Fastify + better-sqlite3 + argon2id + ws
apps/web/                      # @ciphersphere/web — React + Vite + react-router + zustand
infrastructure/docker/         # docker-compose.yml + per-app Dockerfiles
.github/workflows/             # CI
```

## Key choices that made it build & run reliably
- **better-sqlite3** (synchronous, WAL) as the DB — no external Postgres server
  needed; `openDatabase()` runs `CREATE TABLE IF NOT EXISTS` migrations on boot.
  Node 22 has prebuilt binaries.
- **argon2** for Argon2id password hashing (RFC 9106) — prebuilt for Node 22.
- **`ws`** for WebSockets shared on Fastify's underlying `app.server` — one port
  serves both REST and `/ws`. Attach AFTER `app.listen()`.
- **JWT HS256 via Web Crypto** (`@ciphersphere/crypto` signJwt/verifyJwt) — works
  in browser and Node 20+; no `jsonwebtoken` dependency needed.
- **Client-side E2EE** (`@ciphersphere/crypto` encryptMessage/decryptMessage):
  frontend derives a per-conversation AES-256-GCM key from a device-bound secret
  stored in localStorage, sends only `{ciphertext, iv}` to the server, decrypts
  on read. Server never sees plaintext — the pattern holds even without full
  X3DH/Double Ratchet key exchange.
- **Vite aliases** map `@ciphersphere/*` to the package `src/` so the web app
  consumes source (hot reload) and no watch-build of packages is needed in dev.

## Verification loop (run these BEFORE stopping)
```bash
pnpm install
pnpm --filter @ciphersphere/shared build   # and crypto, design-system
pnpm --filter @ciphersphere/api test        # vitest: auth/messaging/workspace/ai
pnpm --filter @ciphersphere/api dev         # boots on :4000
curl localhost:4000/api/v1/health           # expect {"status":"ok"}
pnpm --filter @ciphersphere/web dev         # boots on :3000
```
In the API integration test, point `DATABASE_PATH` at a `mkdtemp` throwaway DB
(before importing buildApp) so tests never touch real data.

## Anti-patterns to avoid
- Do not emit `docs/` + stop. LO read "no next step" literally.
- Do not hand-write a 16-service k8s `gRPC` platform in one session — it can't
  all run. A single Fastify service with clean route modules + SQLite is
  shippable and honest about its scope.
- Do not leave placeholder `***` constants or stub crypto. Use real values.
- Verify the whole flow: register → login → create DM → send encrypted message →
  recipient reads it → remote-assist request/approve/emergency-stop → AI summarize.

## Hard-won debugging pitfalls (each one cost a real fix)
- **ESM static imports are hoisted above other top-level statements.** Setting
  `process.env.DATABASE_PATH = tmp` in a test file, then `import { buildApp } from
  '../server.js'` does NOT take effect — the import (and config.ts reading that env
  var) runs BEFORE your env assignment, so config defaults to a persistent path and
  your "throwaway" tests silently write to the real DB (symptom: on a fresh DB the
  first register returns 409 because a prior run's user persists). Fix: use a dynamic
  import AFTER setting env: `process.env.X = ...; \n const { buildApp } = await
  import('../server.js');`. Top-level await is fine under module ESNext.
- **TS 5.9 `Uint8Array<ArrayBufferLike>` is not assignable to `BufferSource`.** Web
  Crypto calls (`importKey`, `deriveBits`, `encrypt`, `verify`) reject a bare
  `Uint8Array`. Add one helper and wrap every Uint8Array argument:
  `const bs = (u: Uint8Array): BufferSource => u as unknown as BufferSource;`
- **better-sqlite3 rejects boxed primitives as bind params** ("SQLite3 can only bind
  numbers, strings, bigints, buffers, and null"). `Object.assign(primitive_string,
  {..})` produces a boxed `String` whose `typeof === 'object'` → bind fails at runtime
  (500). Return plain objects `{ text, citations }`, never `Object.assign` onto a
  primitive.
- **pnpm `catalog:` refs need pnpm >= 9.5.** pnpm 9.2 errors
  `ERR_PNPM_SPEC_NOT_SUPPORTED_BY_ANY_RESOLVER typescript@catalog:`. Either bump pnpm
  or (more robust) just inline concrete versions (`^5.6.3`) and drop the catalog block.
- **No global install permission? Run pnpm through npx from the user cache**:
  `npx --yes pnpm@9.2.0 install` (no `npm i -g`, which needs perms). Do NOT bump
  `npm config set prefix` — that global config change is legitimately blocked.
- **`z.enum(...)` requires a non-empty tuple**, so `z.enum(ROLES)` where `ROLES` is
  `RoleName[]` fails to typecheck. Cast: `z.enum(ROLES as [RoleName, ...RoleName[]])`.
- **Fastify `declare module 'fastify'` augmentation doesn't propagate to route
  submodules** that import `FastifyInstance` from 'fastify'. Instead of attaching a
  `.websocketServer` on the app, use a module-singleton pub/sub
  (`setRealtime()/broadcast()/sendToUser()` in `pubsub.ts`) that routes import
  directly. Cleaner typing, no cross-module augmentation.
- **Exclude `src/__tests__` from each package's build tsconfig** (keep tests out of
  the compile) — the source build succeeds while vitest (vite resolver) runs the tests
  separately. Test files also need correct relative imports: from `src/__tests__/x.test.ts`,
  import `../index.js`, not `./index.js`.
- **The harness flags any command containing `vite` as a long-lived server.** `vite build`
  in the foreground gets rejected; run it with `background=true` (or `timeout N vite build`)
  and check the log.

## Garbled / corrupted user messages
A user turn arriving as a wall of `<unk>` tokens (or an off-topic non-sequitur
like "你好，我无法给到相关内容。") is a rendering/provider glitch — NOT a real
instruction. Do NOT fabricate meaning from it or invent a task. Acknowledge the
message is unreadable, state exactly where the build stands, and ask for a clean
resend or explicit confirmation before continuing a large autonomous build.
