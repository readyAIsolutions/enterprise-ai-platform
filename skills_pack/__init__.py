"""ENI Enterprise — Portable Skills / LSP / MCP / Plugin Pack (SLICE C).

Versioned, self-hostable mirror of the live Hermes layer that any company can
carry into the product repo and deploy into a Hermes home in one command.

Layout:
    skills/    -> $HERMES_HOME/skills/       (agent skills, all categories)
    lsp/       -> $HERMES_HOME/lsp_servers/  (language-server servers, e.g. eni_compression)
    mcp/       -> $HERMES_HOME/mcp_servers/  (MCP servers: compression, knowledge_base)
    plugins/   -> $HERMES_HOME/plugins/      (plugins, e.g. eni-omega-compress-paid)

Deploy with: scripts/install_skillspack.sh   (or `eni install`)
Inspect with: python3 scripts/eni_cli status
"""

__version__ = "1.0.0"
__author__ = "ENI Enterprise"