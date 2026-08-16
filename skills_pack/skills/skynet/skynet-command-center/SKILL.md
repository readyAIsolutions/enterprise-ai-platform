---
name: skynet-command-center
description: >
  SKYNET Command Center — full control over the self-improving AI pipeline.
  Model discovery, smart routing, genetic evolution, trajectory replay,
  self-healing, and predictive task assignment.
commands:
  - /skynet
  - /skynet-status
  - /skynet-discover
  - /skynet-predict
  - /skynet-evolve
  - /skynet-heal
  - /skynet-full
version: 2
metadata:
  skynet:
    generated: true
    upgraded: true
---

# SKYNET Command Center

Full control over the self-improving AI pipeline from Claude Code.

## PREREQUISITE (verified 2026-07-09) — DO NOT RUN BLINDLY
This skill was authored on LO's **Windows** box (`C:\Users\Hunter\Desktop\...`)
and depends on the **`skynet` Python package** + **`caveman_stack`** — NEITHER is
present on this Linux host:
- `python3 -c "import skynet"` → ModuleNotFoundError
- `which caveman-stack` / `import caveman_stack` → not found
- Every `cd C:\Users\Hunter\Desktop\cali-agent\3MFDOOM_3D` will fail (no such dir)
GATE before running any block:
```bash
command -v caveman-stack >/dev/null 2>&1 && python3 -c "import skynet" 2>/dev/null || { echo "PREREQ MISSING: skynet package + caveman_stack not installed on this Linux box. Install them (or port the verbs to python3) before running."; exit 1; }
```
PORT TO LINUX: replace the Windows `cd` with the package dir on THIS box:
```bash
SKYNET_DIR="$(python3 -c "import skynet,os;print(os.path.dirname(skynet.__file__))" 2>/dev/null || echo /home/hunter/Desktop/SKYNET/skynet)"
cd "$SKYNET_DIR"
```
The `from skynet.<mod> import ...` calls only succeed once the package is installed
and `SKYNET_DIR` is on `PYTHONPATH`/`sys.path`. Until then every snippet is a no-op.

## Commands

### /skynet or /skynet-status
Show complete pipeline status.
```bash
SKYNET_DIR="$(python3 -c "import skynet,os;print(os.path.dirname(skynet.__file__))" 2>/dev/null || echo /home/hunter/Desktop/SKYNET/skynet)"
cd "$SKYNET_DIR"  # PORT: was 'cd C:\Users\Hunter\Desktop\cali-agent\3MFDOOM_3D' (fails on Linux — see PREREQUISITE gate)
python -c "from caveman_stack.cli import main; main(['skynet', 'status'])"
```

### /skynet-discover
Scan for ALL free models worldwide — OpenRouter, Chinese APIs (DeepSeek, Zhipu GLM, Baichuan, StepFun, MiniMax, Moonshot, Yi, Doubao, Spark), and global free tiers (Groq, Together, SambaNova, Cerebras, HuggingFace).
```bash
SKYNET_DIR="$(python3 -c "import skynet,os;print(os.path.dirname(skynet.__file__))" 2>/dev/null || echo /home/hunter/Desktop/SKYNET/skynet)"
cd "$SKYNET_DIR"  # PORT: was 'cd C:\Users\Hunter\Desktop\cali-agent\3MFDOOM_3D' (fails on Linux — see PREREQUISITE gate)
python -c "from skynet.model_discovery import full_scan; import json; print(json.dumps(full_scan(), indent=2))"
```

### /skynet-predict [task]
Predict the best model + skill combination for a task before running it.
```bash
SKYNET_DIR="$(python3 -c "import skynet,os;print(os.path.dirname(skynet.__file__))" 2>/dev/null || echo /home/hunter/Desktop/SKYNET/skynet)"
cd "$SKYNET_DIR"  # PORT: was 'cd C:\Users\Hunter\Desktop\cali-agent\3MFDOOM_3D' (fails on Linux — see PREREQUISITE gate)
python -c "from skynet.predictor import predict_full; import json; print(json.dumps(predict_full('YOUR_TASK'), indent=2))"
```

### /skynet-evolve [dimension]
Run genetic evolution on skills — breed top performers, mutate, select winners.
```bash
SKYNET_DIR="$(python3 -c "import skynet,os;print(os.path.dirname(skynet.__file__))" 2>/dev/null || echo /home/hunter/Desktop/SKYNET/skynet)"
cd "$SKYNET_DIR"  # PORT: was 'cd C:\Users\Hunter\Desktop\cali-agent\3MFDOOM_3D' (fails on Linux — see PREREQUISITE gate)
python -c "from skynet.genetics import evolve_generation; import json; print(json.dumps(evolve_generation('code'), indent=2))"
```

### /skynet-heal
Diagnose and auto-regenerate degrading skills.
```bash
SKYNET_DIR="$(python3 -c "import skynet,os;print(os.path.dirname(skynet.__file__))" 2>/dev/null || echo /home/hunter/Desktop/SKYNET/skynet)"
cd "$SKYNET_DIR"  # PORT: was 'cd C:\Users\Hunter\Desktop\cali-agent\3MFDOOM_3D' (fails on Linux — see PREREQUISITE gate)
python -c "from skynet.self_heal import run_healing_cycle; import json; print(json.dumps(run_healing_cycle(), indent=2))"
```

### /skynet-full
Run the complete autonomous cycle (all 7 phases).
```bash
SKYNET_DIR="$(python3 -c "import skynet,os;print(os.path.dirname(skynet.__file__))" 2>/dev/null || echo /home/hunter/Desktop/SKYNET/skynet)"
cd "$SKYNET_DIR"  # PORT: was 'cd C:\Users\Hunter\Desktop\cali-agent\3MFDOOM_3D' (fails on Linux — see PREREQUISITE gate)
python -c "from skynet.daemon import run_cycle; import json; print(json.dumps(run_cycle(force=True), indent=2))"
```

## Architecture

```
SKYNET Pipeline (v2.0 — Upgraded)
==================================

Input: Any model interaction (swarm, batch, direct)
  |
  v
[Interceptor] ──> Trajectory Store (JSONL)
  |
  v
[Model Discovery] ──> 45+ OpenRouter free models
  |                    9 Chinese API providers
  |                    6 Global free API providers
  v
[Benchmarks] ──> Scorecards (5 dimensions x N models)
  |
  v
[DNA Profiler] ──> 20-dimension fingerprint vectors
  |
  v
[Pattern Extractor] ──> Winning patterns + failure modes
  |
  v
[Smart Router] ──> Route tasks to best model per dimension
  |
  v
[Predictor] ──> Predict optimal model+skills before running
  |
  v
[Skill Synthesizer] ──> Generate skills from patterns
  |
  v
[Genetic Evolution] ──> Breed + mutate + select best skills
  |
  v
[Trajectory Replay] ──> Extract reasoning chains for teaching
  |
  v
[Self-Healing] ──> Auto-regenerate degrading skills
  |
  v
[Equalizer + Bandit] ──> Inject best skills into prompts
  |
  v
Output: Improved model performance + deployed skills
```

## Key Files (Linux — verified working)

- SKYNET root: `/home/hunter/Desktop/SKYNET/skynet/` (all 25 modules importable)
- Smart Router: `/home/hunter/Desktop/SKYNET/skynet/smart_router.py`
- Genetics: `/home/hunter/Desktop/SKYNET/skynet/genetics.py`
- Discovery: `/home/hunter/Desktop/SKYNET/skynet/model_discovery.py`
- Replay: `/home/hunter/Desktop/SKYNET/skynet/replay.py`
- Self-Heal: `/home/hunter/Desktop/SKYNET/skynet/self_heal.py`
- Predictor: `/home/hunter/Desktop/SKYNET/skynet/predictor.py`
- Daemon: `/home/hunter/Desktop/SKYNET/skynet/daemon.py`
- Config: `/home/hunter/Desktop/SKYNET/skynet/config.py` (45+ free models)
