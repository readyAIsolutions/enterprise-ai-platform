---
name: hermes-mcp-management
description: >-
  Connect, authenticate, test, and manage MCP (Model Context Protocol) servers
  in Hermes — both OAuth-protected HTTP servers and stdio/command servers. Covers
  `hermes mcp add/server/login/list/test`, the interactive OAuth browser flow
  (HTTP servers like viewmax.io/api/mcp that require a bearer token), the
  connect-timeout + save-config semantics, and how to point Hermes tools at a
  newly added server. Use whenever LO says "set this up as an MCP", "connect this
  MCP server", "add X as a tool server", or an MCP endpoint returns
  "Unauthorized: Authentication required".
---

# Hermes MCP management

Hermes has a dedicated MCP surface (`hermes mcp`) for connecting Model Context
Protocol servers that add tools to the agent.

## The command surface
- `hermes mcp add <name> --url <endpoint>` — HTTP/SSE server (discovery-first).
- `hermes mcp add <name> --command <cmd> --args ...` — stdio server.
- `hermes mcp add <name> --url <url> --auth oauth` — OAuth-protected HTTP server.
- `hermes mcp list` / `ls` — show configured servers.
- `hermes mcp test` — test a connection.
- `hermes mcp login` — force re-auth for an OAuth server.
- `hermes mcp serve` — run Hermes itself AS an MCP server (expose conversations).
- `hermes mcp configure` / `picker` — toggle which tools a server exposes.

## OAuth-protected MCP servers (e.g. viewmax.io/api/mcp)

Many hosted MCP endpoints are NOT public — they are OAuth resource servers. Probe
first:
```
curl -s -i https://HOST/api/mcp   # expect: jsonrpc error "Unauthorized: Authentication required" + www-authenticate: Bearer resource_metadata=...
curl -s https://HOST/.well-known/oauth-protected-resource
# -> shows authorization_servers, scopes_supported, jwks_uri
```
`hermes mcp add <name> --url <url> --auth oauth` handles this: it opens the
provider's authorization page in the browser automatically and acquires tokens
on first connection.

### Real gotchas (learned on viewmax, 2026-08-06)
1. The flow is INTERACTIVE: a browser tab opens and a human must log in /
   authorize on the provider's site. The agent on its own cannot complete this.
   Tell LO plainly which step needs them ("log in to viewmax in the browser").
2. There is a short connect timeout (~40s). If the human login takes longer, the
   initial connect step reports `Failed to connect ... timed out` EVEN THOUGH the
   OAuth config was written fine.
3. The CLI then asks `Save config anyway? [y/N]` — the config is only persisted
   if you answer `y`. Do NOT pipe a premature `echo "n"` (that discards the
   config before login finished) and do NOT blindly echo `y` into an interactive
   flow — answer after the human has authenticated.
4. After a successful add, `hermes mcp list` must show the server and
   `hermes mcp test` should pass; re-runs just call `hermes mcp login` to refresh.

## Where config lives
`mcp_servers: {}` section in `~/.hermes/config.yaml`, plus per-server state under
`~/.hermes/mcp_servers/`. `config.yaml` is a PROTECTED credential file — manage
servers via the `hermes mcp` CLI, not by editing the YAML.

## Pitfalls
- Don't assume a URL you were handed is reachable/unanonymous — probe it. A 200
  HTML page (Vercel/spa) with an OAuth resource-server MCP path is the norm for
  hosted AI-provider MCPs.
- Stdio servers need the runtime (node/npx/python) present; HTTP servers need the
  host reachable. If `test` fails, check reachability + auth before blaming the
  server.
