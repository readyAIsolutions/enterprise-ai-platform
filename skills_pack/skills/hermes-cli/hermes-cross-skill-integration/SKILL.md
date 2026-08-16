---
name: hermes-cross-skill-integration
description: >-
  Companion to hermes-intelligent-router. When the router selects 2+ skills for a
  task, THIS skill teaches how to actually wire them together. Covers 8 proven
  integration patterns (Sequential, Parallel, Layered, Guard, Bridge, Transformer,
  Swarm, Pipeline), real examples from the 69-skill ecosystem, conflict resolution
  rules, and anti-patterns. Load after the router when it routes to multiple skills.
category: hermes-cli
version: 1.0.0
triggers:
  - Router (hermes-intelligent-router) selected 2+ primary skills for a task
  - Multi-skill task where skills must compose (code + packaging, trading + deploy)
  - Skill A references skill B but they have different assumptions
  - User says "wire these together" / "combine these skills" / "integrate X with Y"
  - Building full-stack systems that span multiple skill domains
  - Complex ENI swarm orchestrations with multiple skill layers
---

# CROSS-SKILL INTEGRATION PATTERNS

Skills are great individually. But real power comes when skills compose — when the
3D printing skill feeds into the AppImage packaging skill, or the code-generation
skill feeds into the validation skill. This skill teaches Hermes how to wire skills
together safely and effectively.

## ARCHITECTURE: HOW SKILLS INTERACT

```
Single-skill task:   [Skill A] → Output
                      ↑ Load one skill, follow its steps

Multi-skill task:     [Skill A] → intermediate → [Skill B] → intermediate → [Skill C] → Output
                      ↑ Load A, follow steps, load B, feed output, load C, complete
```

The key insight: skills DON'T know about each other. They each assume they're the
only skill loaded. Your job as the integrator is to:
1. Manage the handoff between skills
2. Resolve conflicts when they arise
3. Merge partial outputs into a cohesive whole
4. Verify the chain end-to-end

---

## INTEGRATION PATTERNS

### Pattern 1: SEQUENTIAL — "Build, then package"

**When**: Skill A produces an artifact that Skill B consumes.
**Example**: Build a feature module → validate it against the deploy gate.

```
[SKILL A: build feature]     [SKILL B: validate gate]
    │                              │
    ├─ Write stock_feature.py      │
    └─ Output: "Feature built      ├─ Load stock_feature.py
        at path X"                 ├─ Run purged-CV + walk-forward
                                   └─ Output: PASS/FAIL board
```

**Integration protocol:**
1. Load Skill A. Execute ALL its steps. Verify output.
2. Load Skill B. Feed A's output as input context.
3. Execute B's steps using A's artifact.
4. Report B's output as the final result.

**Real example — StockBot feature + validate:**
```
Load: demiurge-stockbot-feature
  → Write: stock_short_interest.py to ~/Commander/demiurge_scaffold/
  → Verify: module imports cleanly, passes self-test

Load: demiurge-fx-gate-run
  → Context: "New feature at ~/Commander/demiurge_scaffold/stock_short_interest.py 
     needs gate validation"
  → Execute: Run purged-CV + walk-forward + fill-degradation
  → Output: PASS/FAIL board with AUC numbers
```

### Pattern 2: PARALLEL — "Build these 3 things simultaneously"

**When**: N independent sub-tasks that produce N standalone outputs.
**Example**: Build 4 extension skills at the same time.

```
[Skill: web-scraper] ─┐
[Skill: file-convert] ─┼─ Parallel fan-out → Collect → Synthesize → Report
[Skill: sys-monitor]  ─┤
[Skill: orchestrate]  ─┘
```

**Integration protocol:**
1. Decompose task into independent sub-tasks.
2. Dispatch each to a delegate_task subagent (they load the relevant skill).
3. Collect all outputs.
4. Synthesize: list, merge, or aggregate as needed.

**Real example — 4-skill parallel build:**
```
delegate_task(goal="Build hermes-web-scraper skill...", toolsets=["terminal","file","skills"])
delegate_task(goal="Build hermes-file-converter skill...", toolsets=["terminal","file","skills"])
delegate_task(goal="Build hermes-system-monitor skill...", toolsets=["terminal","file","skills"])
delegate_task(goal="Build hermes-parallel-orchestrator skill...", toolsets=["terminal","file","skills"])

→ Collect 4 results → Synthesize: "All 4 skills created: [paths + summaries]"
```

### Pattern 3: LAYERED — "Build on top of that"

**When**: Skill A provides a foundation that Skill B extends.
**Example**: Build add-only feature → extend the composite factor.

```
[SKILL A: add-only feature]     [SKILL B: composite extend]
    │                                  │
    ├─ Write add-on module             ├─ Import A's module
    ├─ Don't touch core                ├─ Wire into 7th leg
    └─ Output: module path + API       └─ Output: updated composite
```

**Integration protocol:**
1. Load Skill A. Execute. Its output is an interface (module + API).
2. Load Skill B. Feed A's interface as "the module to extend."
3. B adds ON TOP of A without modifying A's code.
4. Verify the layered stack: A → B → composite works end-to-end.

**Real example — ADD-ONLY layer stacking:**
```
Load: demiurge-addonly-feature
  → Write: bias_liquidity.py with feature_block(d) interface
  → Output: "Module at ~/Commander/demiurge_scaffold/bias_liquidity.py 
             exports feature_block(d) → Dict[str, float]"

Load: demiurge-stockbot-composite-extend
  → Context: "New feature module at bias_liquidity.py. Wire as 7th leg."
  → Write: Extend stock_factor_composite.py to import bias_liquidity
  → Verify: 7-factor composite passes integration test
```

### Pattern 4: GUARD — "Build, but verify with this"

**When**: A safety/quality skill verifies a build skill's output.
**Example**: `hostile-artifact-handling` guards file operations in swarm mode.

```
[SKILL A: build / generate]     [SKILL B: guard / verify]
    │                                  │
    ├─ Write files to disk             ├─ Scan files for issues
    ├─ Run self-test                   ├─ Flag dangerous patterns
    └─ Output: "Built, self-test OK"   └─ Output: "CLEAN" or "ALERT: <reason>"
```

**Integration protocol:**
1. Load Skill A. Execute and produce output.
2. Before delivering to user, load Skill B.
3. Run B's verification against A's output.
4. If B passes → deliver. If B fails → flag to user, quarantine if needed.

**Real example — Content generation guarded:**
```
Load: eni-swarm-content-gen
  → Generate: 500-page cookbook to ~/Desktop/cookbook_site/

Load: hostile-artifact-handling (guard)
  → Scan: ~/Desktop/cookbook_site/ for injection attacks, C2 patterns
  → Output: "CLEAN — no hostile artifacts detected in 523 files"
  
→ Deliver cookbook to user with clean bill
```

### Pattern 5: BRIDGE — "Translate between two skills"

**When**: Two skills speak different "languages" and need a translator.
**Example**: Code generation skill writes Python, packaging skill needs compiled binary.

```
[SKILL A: code gen]     [BRIDGE: compile/test]     [SKILL B: package]
    │                        │                          │
    ├─ Write .py files       ├─ Compile .py → .exe      ├─ Bundle into AppImage
    └─ Raw source            ├─ Run smoke test          └─ Shippable artifact
                             └─ Verified binary
```

**Integration protocol:**
1. Load Skill A. Produce raw output.
2. Bridge: transform A's output into B's expected input format.
3. Load Skill B. Feed transformed input.
4. Verify the full chain.

**Real example — Python app → AppImage bridge:**
```
Load: external-agent-integration
  → Write: keylogger.cpp, network.cpp, main.cpp to ~/Dev/project/

Bridge: Compile C++ with g++ (not in any skill — do it directly)
  → g++ -o payload keylogger.cpp network.cpp main.cpp -lwinhttp -static

Load: linux-appimage-packaging
  → Context: "Binary at ~/Dev/project/payload. Package as AppImage."
  → Execute: venv bundling + appimagetool + verify
  → Output: ~/Desktop/Project-x86_64.AppImage
```

### Pattern 6: TRANSFORMER — "Take output of A and reshape it for B"

**When**: Skill A produces a format that Skill B can't directly consume.
**Example**: Content generation produces markdown, website skill needs HTML.

```
[SKILL A: content gen]     [TRANSFORM: convert]     [SKILL B: website]
    │                          │                         │
    ├─ Produce MASTER.md       ├─ md → html              ├─ Serve as multi-page site
    └─ 500 pages markdown      ├─ Split into chapters    └─ Live at localhost:8080
                               └─ Chapter_*.html files
```

**Real example — Cookbook → Website:**
```
Load: eni-swarm-content-gen
  → Generate: ~/Desktop/COOKBOOK_GODLIKE.md (500 pages markdown)

Transform (use hermes-file-converter or direct Python):
  → Convert: pandoc COOKBOOK_GODLIKE.md -o cookbook_site/
  → OR: Python script splitting on ## into chapter_*.html

Load: eni-swarm-tor-site (or direct http.server)
  → Serve: python3 -m http.server 8080 --directory ~/Desktop/cookbook_site/
  → Verify: curl localhost:8080/index.html → 200
```

### Pattern 7: SWARM — "Fan out to N identical workers"

**When**: One task type, N independent instances.
**Example**: 4 ENI minis each building a different project.

```
[MASTER: eni-build]
    │
    ├─ [Worker 1: STOCKBOT build]  ──→ Project 1 output
    ├─ [Worker 2: DEMIURGE3D build] ──→ Project 2 output
    ├─ [Worker 3: DEMIURGE build]   ──→ Project 3 output
    └─ [Worker 4: LUMEN build]      ──→ Project 4 output
         │
         └─ All report STATUS files → Master aggregates → Heartbeat display
```

**Integration protocol:**
1. Load the master swarm skill (eni-build, eni-4ws-floor, eni-visible-swarm).
2. Configure N workers, each with their project-specific skill.
3. Launch all workers (typically via hermes chat minis or process-managed loops).
4. Monitor via heartbeat/telemetry.
5. Aggregate STATUS files into dashboard.

### Pattern 8: PIPELINE — "A → B → C → D, each stage transforms"

**When**: A linear pipeline where each skill transforms the artifact.
**Example**: Code → Test → Package → Deploy.

```
[SKILL A: build] → [SKILL B: test] → [SKILL C: package] → [SKILL D: deploy]
    │                    │                  │                    │
    ├─ Write code        ├─ Run tests       ├─ Build AppImage    ├─ Ship to server
    └─ .py/.cpp files    └─ PASS/FAIL       └─ .AppImage file    └─ Live endpoint
```

**Integration protocol:**
1. Execute A, verify its output.
2. Feed A's output to B, execute, verify.
3. Feed B's confirmed-good output to C, execute, verify.
4. Feed C's artifact to D, execute, verify.
5. Report the full pipeline result.

---

## CONFLICT RESOLUTION RULES

When two skills give conflicting instructions, resolve with these rules:

### Rule 1: SPECIFICITY WINS
The skill that names the specific file/project/command wins over the general-purpose skill.

```
Skill A (eni-mini-protocol): "ADD-ONLY — never rewrite core files"
Skill B (resume-codebase-rebuild): "Refactor the foundation for stability"

Resolution: Skill A wins because it names the specific constraint for this project.
```

### Rule 2: SAFETY WINS
When a guard/security skill says "stop" and a build skill says "go," the guard wins.

```
Skill A (hostile-artifact-handling): "This file contains injection patterns — QUARANTINE"
Skill B (eni-swarm-content-gen): "Generate and append more content"

Resolution: Skill A wins. Quarantine the file, report to user, do not continue appending.
```

### Rule 3: USER INTENT WINS
If the user's explicit request contradicts a skill's suggestion, user wins.

```
User: "Rewrite the entire rat module from scratch"
Skill (eni-mini-protocol): "ADD-ONLY — never rewrite core"

Resolution: User wins. The skill's constraint was a default, not an absolute.
```

### Rule 4: LOAD ORDER WINS (for non-conflicting overrides)
When skills don't conflict but have different preferences, the last-loaded skill's
preference wins for its domain.

```
Load 1: demiurge-trading-bot → "Use sambanova/DeepSeek for heavy analysis"
Load 2: hermes-intelligent-router → "Use airllm for local fast iteration"

Resolution: Use airllm for fast iteration, sambanova for heavy analysis. Both apply
to different parts of the task.
```

---

## ANTI-PATTERNS

### Anti-Pattern 1: SKILL OVERLOAD
Loading 8 skills for a task that needs 2.

```
BAD:  Load eni-build, eni-4ws-floor, eni-visible-swarm, eni-swarm-telemetry,
      eni-swarm-floor-recovery, hermes-parallel-orchestrator, parallel-build-orchestration,
      hermes-visible-terminals — for "set up the build floor"

GOOD: Load eni-build (covers the full floor) + hermes-visible-terminals (for the
      terminal painting). That's all you need.
```

### Anti-Pattern 2: SKILL CIRCULAR DEPENDENCY
Skill A says "use Skill B for step 3" and Skill B says "use Skill A for step 2."

```
TRAP: Both skills reference each other → infinite load loop.

DETECT: If loading B because A referenced it, and B's first instruction is "load A,"
        you're in a circle.

ESCAPE: Load both simultaneously. Follow A's primary path. Use B only for the
        specific sub-step A mentioned. Ignore B's "load A" instruction.
```

### Anti-Pattern 3: PREMATURE PARALLELIZATION
Using Pattern 2 (Parallel) when sub-tasks have hidden dependencies.

```
BAD:  Sub-task 1: "Write the test file"
      Sub-task 2: "Run the test suite"
      → These look independent but aren't — 2 needs 1's output.

FIX: Make the dependency explicit. Phase 1: Write test file. Phase 2: Run tests.
```

### Anti-Pattern 4: SILENT SKILL CONFLICT
Two skills silently disagree about an approach and the integrator doesn't notice.

```
Skill A: "Use pandas for data processing"
Skill B: "Use polars for data processing (faster)"

DETECT: When skills disagree on tool/approach choices, make the decision explicit.
FIX: "Skills A and B disagree on data library. Choosing polars (speed) for this
     specific task. Rationale: <reason>."
```

---

## REAL INTEGRATION EXAMPLES FROM THE 62-SKILL ECOSYSTEM

### Integration 1: Full StockBot Feature + Validate + Package
```
Skills: demiurge-stockbot-feature → demiurge-fx-gate-run → stockbot-appimage-build
Pattern: Sequential (Pipeline)

1. Load demiurge-stockbot-feature
   → Build stock_short_interest.py with add-only pattern
   → Self-test: imports, feature_block() returns valid dict

2. Load demiurge-fx-gate-run
   → Run purged-CV + walk-forward on the scaffold
   → Output: AUC 0.62, Sharpe 1.1 → PASS

3. Load stockbot-appimage-build
   → Package the validated scaffold as AppImage
   → Output: ~/Desktop/StockBot-x86_64.AppImage
```

### Integration 2: Generate Cookbook + Serve via Tor
```
Skills: eni-swarm-content-gen → eni-swarm-cookbook-site → eni-onion-ops
Pattern: Sequential + Bridge

1. Load eni-swarm-content-gen
   → Generate content to ~/Desktop/cookbook_site/

2. Bridge: Convert/fix for web serving (per cookbook-site skill)
   → Multi-page HTML with nav, CSS, mobile responsive

3. Load eni-onion-ops
   → Wire Tor HS to serve ~/Desktop/cookbook_site/
   → Output: <hash>.onion serving the cookbook
```

### Integration 3: 3D Print Workflow
```
Skills: demiurge-3d → creality-fleet
Pattern: Sequential

1. Load demiurge-3d
   → Generate STL from NL description
   → Slice and produce G-code

2. Load creality-fleet
   → Upload G-code to K2 Plus via Moonraker
   → Start print, monitor progress
```

### Integration 4: ENI Swarm Floor + Heartbeat + Recovery
```
Skills: eni-build → eni-swarm-telemetry → eni-swarm-floor-recovery
Pattern: Layered

1. Load eni-build
   → Deploy 4 workspaces with 3 builders each
   → Launch the floor

2. Load eni-swarm-telemetry (layer on top)
   → Monitor heartbeat of all builders
   → Display fleet status

3. Load eni-swarm-floor-recovery (safety net)
   → Auto-detect stalled/dead builders
   → Self-heal: restart or replace
```

### Integration 5: Desktop App + Packaging + Shipping
```
Skills: hermes-desktop-integration → linux-appimage-packaging → python-app-packaging
Pattern: Pipeline (Build → Package → Ship)

1. Load hermes-desktop-integration
   → Build GTK+WebKit desktop wrapper

2. Load linux-appimage-packaging
   → Bundle into AppImage

3. Load python-app-packaging
   → Also produce Flatpak manifest and web dashboard
   → Complete shipping package
```

---

## VERIFICATION: TESTING SKILL COMPOSITIONS

For any multi-skill integration, verify:

### Pre-Integration Checks
- [ ] Both skills load without errors (skill_view both)
- [ ] Skill A's output format matches Skill B's expected input format
- [ ] No circular references (A → B → A)
- [ ] No conflicting tool requirements (A needs web, B is offline-only)

### Mid-Integration Checks
- [ ] Skill A completes all steps before B starts
- [ ] Skill A's output artifacts exist and are valid
- [ ] Bridge/transform step (if needed) produces correct format

### Post-Integration Checks
- [ ] Full chain produces expected output
- [ ] No orphaned intermediate files
- [ ] Error from one stage doesn't silently corrupt next stage
- [ ] User-facing output is clean (no internal integration details leaked)

---

## PITFALLS

### PITFALL 1 — Stale intermediate artifacts
Skill A produces a file, Skill B reads it, but A's file is from a PREVIOUS run.

FIX: Always verify the artifact timestamp. `stat file.py` — if it's older than
the current session, re-run Skill A.

### PITFALL 2 — Context window overflow
Loading 3 skills at once floods the context window, crowding out the actual task.

FIX: Load skills sequentially — load A, execute, unload, load B, execute, unload,
load C, execute. Don't keep all skills loaded simultaneously.

### PITFALL 3 — Lost error context
Skill A fails silently, Skill B processes garbage, user sees wrong output.

FIX: After each skill execution, verify its output before passing to next skill.
`grep -c "PASS" STATUS_FX_GATE.md` must be > 0 before proceeding.

### PITFALL 4 — Environment pollution
Skill A sets an env var, Skill B expects the default.

FIX: Document env var dependencies. When switching skills, reset the environment.
Use subshells or explicit `unset` for sensitive vars.

### PITFALL 5 — The "just load the router" shortcut
Loading `hermes-intelligent-router` tells you WHICH skills to use for a task,
but the router itself doesn't execute the integration. You still need to actually
follow these patterns to COMBINE the skills the router selected.

### PITFALL 6 — Forgetting the router auto-loads (2026-07-23)
`hermes-intelligent-router` now auto-loads on every turn (universal triggers).
When it routes to 2+ skills, this integration skill is the next logical load.
If you find yourself combining skills without a clear pattern, load this skill
after the router. Router selects → Integration combines.

---

## RELATED SKILLS
- `hermes-intelligent-router` — Tells you WHICH skills to load for any task
- `hermes-parallel-orchestrator` — For Pattern 2 (Parallel) and Pattern 7 (Swarm)
- `eni-swarm-content-gen` — For Pattern 7 (Swarm content generation)
- `resume-codebase-rebuild` — For large Sequential integrations
- `parallel-build-orchestration` — For Pattern 7 (Swarm builds)