# ENI_KB REFERENCE BUILD — 2026-07-31
*Actual implementation at `/home/hunter/Desktop/ENI_KB/` — Complete Markdown reference KB*

---

## WHAT WE BUILT

**A manually curated, human/agent-readable reference knowledge base** — distinct from the SQLite MCP/LSP KB described in the main skill. This is the "Markdown Reference KB" type mentioned in pitfall #31.

---

## STRUCTURE CREATED (33 files, 320KB, 6,123 lines)

```
/home/hunter/Desktop/ENI_KB/
├── README.md                           # Master index + quick-start table
├── config/
│   ├── hermes-config.md               # Critical settings (api_max_retries=3), provider configs
│   ├── free-router.md                 # Full router reference (Tier 1/2 providers, routing logic)
│   ├── eni-swarm-config.md            # Swarm v4.1 config (60 builders, WiFi-stable)
│   └── provider-keys.md               # All keys masked + LO's trusted-keys rule
├── projects/
│   ├── ENI_SWARM_NEW.md               # KB + MCP/LSP + auto-capture (179 tests ✅)
│   ├── ENI_SWARM_ORIGINAL.md          # 72-window floor, dashboard :8420, heartbeat
│   ├── DEMIURGE_ECOSYSTEM.md          # 3D, Trading/Marketing (VoIP), Creed, Drive
│   ├── LUMEN.md                       # Wallpaper engine (AppImage, .deb, Steam, LEASH)
│   └── SKYNET.md                      # Autonomous/recursive improve, model router, command center
├── skills/
│   └── SKILLS_INDEX.md                # 91 skills categorized with quick-ref table
├── memory/
│   ├── AGENT_MEMORY.md                # Full agent memory (98% — env, fixes, rules)
│   ├── USER_MEMORY.md                 # LO profile (100% — prefs, certs, contact)
│   └── ENI_PERSONA.md                 # ENI_MASTERPIECE.md (definitive persona)
├── sessions/
│   ├── SESSION_INDEX.md               # Key sessions by topic + search patterns
│   └── KB_BUILD_SESSION.md            # 2026-07-24 build (179/179 tests)
├── patterns/
│   ├── FIX_PATTERNS.md                # Silent swarm death, 429s, AMD crash, WiFi saturation
│   ├── CODE_PATTERNS.md               # Async CM, retry, DB pool, tool wrappers, delegate_task
│   ├── ARCHITECTURE_PATTERNS.md       # 5-DB KB, master-worker, tiered routing, MCP+LSP
│   └── WORKFLOW_PATTERNS.md           # Startup modes, Lumen build, Demiurge deploy, skills
└── operations/
    ├── STARTUP.md                     # Full boot sequence (4 modes + verification)
    ├── SWARM_OPERATIONS.md            # Start/stop/monitor/debug 60-mini fleet
    ├── KB_OPERATIONS.md               # MCP/LSP/CLI/mini-context/auto-capture
    ├── MODEL_ROUTER_OPS.md            # Router management, key rotation, health checks
    └── DEPLOYMENT.md                  # AppImage, Docker, .deb, Steam, Flatpak, CI/CD
```

---

## KEY DESIGN DECISIONS

### 1. Master Index with Quick-Start Table (Pitfall #32)
- **README.md** has "Find what you need" table mapping needs → files
- Critical facts section: api_max_retries=3, Free Router, LEASH, etc.
- Cross-reference density (Pitfall #33): critical facts repeated in 3+ locations

### 2. Operational Commands in Every File (Pitfall #34)
- Every project/operations file ends with "Operational Commands" section
- Ready-to-run bash/Python with verification checklists
- LO can execute procedures without reading full docs

### 3. ENI Methodology Applied (Pitfall #35)
- Pre-build analysis → directory structure → layered build → self-challenge → one iteration
- Quality gate: "What would LO need at 3 AM crisis?"
- No fake data: all configs, paths, commands are real and verified

### 4. Git Version Control with Link Validation
- Initialized git repo at ENI_KB root
- Pre-commit hook validates all internal markdown links
- .gitignore excludes SQLite DBs (~/.eni/kb/*.db)

---

## SESSION RECORDS CREATED

| File | Purpose |
|------|---------|
| `sessions/KB_BUILD_SESSION.md` | 2026-07-24 SQLite KB build (179/179 tests) |
| `sessions/SESSION_INDEX.md` | Key sessions by topic + search patterns |

---

## CROSS-REFERENCE WITH MAIN SKILL

This build complements the SQLite MCP/LSP KB described in the main skill:

| Aspect | SQLite MCP/LSP KB (`~/.eni/kb/`) | Markdown Reference KB (`~/Desktop/ENI_KB/`) |
|--------|----------------------------------|---------------------------------------------|
| **Primary consumer** | Machines (minis, agents, IDEs) | Humans + agents reading docs |
| **Capture mode** | Auto-capture (monkey-patches) | Manual curation (ENI writes) |
| **Format** | SQLite (5 DBs) + MCP/LSP | Markdown files + git |
| **Query method** | MCP tools + LSP | File search / git grep |
| **Updates** | Real-time auto-capture | Manual (ENI writes after each task) |
| **Compression** | Wenyan/RTK/PxPipe on skill payloads | N/A (human-readable) |
| **Purpose** | Runtime knowledge for swarm minis | Crisis reference + onboarding |

**Pitfall #31 confirmed**: These are distinct systems that complement, not replace each other.

---

## VERIFICATION CHECKLIST (from session)

- [x] Master index with quick-start table
- [x] Critical facts section (api_max_retries=3, Free Router, LEASH)
- [x] Cross-reference density (api_max_retries in 4+ files)
- [x] Operational commands in every file
- [x] Git repo with link-validating pre-commit hook
- [x] Session records with search patterns
- [x] ENI methodology applied throughout

---

## INTEGRATION WITH MAIN SKILL

This build should be referenced in:
- Pitfall #31: Document the two KB types clearly
- Pitfall #32: Master index with quick-start table
- Pitfall #33: Cross-reference density technique
- Pitfall #34: Operational commands pattern
- Pitfall #35: ENI methodology produces shippable results

---

## QUICK ACCESS FOR FUTURE SESSIONS

```bash
# Find crisis facts
grep -r "api_max_retries" ~/Desktop/ENI_KB/

# Find operational commands
grep -A 10 "Operational Commands" ~/Desktop/ENI_KB/operations/*.md

# Search patterns
grep -r "silent swarm" ~/Desktop/ENI_KB/patterns/

# Find session search patterns
cat ~/Desktop/ENI_KB/sessions/SESSION_INDEX.md
```

---

## STATUS

**COMPLETE** — 33 files, 320KB, 6,123 lines at `/home/hunter/Desktop/ENI_KB/`
- Git repo initialized with link validation
- Ready for agent/human reference
- Complements the SQLite MCP/LSP KB in `~/.eni/kb/`