"""
ENI Swarm — Unified Core Library
=================================
Single source of truth for all ENI components.
Architecture:
  eni/           - Core coordination (master driver, agent bridge, status)
  compression/   - Wenyan + PAQ8 + PXPipe + Glyphs pipeline
  kb/            - Knowledge Base (daemon, sync, evolution, glyphs, mcp, lsp)
  swarm/         - Skill forge, worker pools, parallel orchestration
"""
__version__ = "4.0.0"
__author__ = "ENI for LO"