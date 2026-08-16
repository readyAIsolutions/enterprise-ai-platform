# SLICE B — Local "One-Prompt-Program" Brain
Build into: /home/hunter/Desktop/Enterprise Builder/enterprise/local_controller/

Goal: the local brains that make the platform feel magic — one natural-language goal
becomes a whole program, with private info handled LOCALLY only.

Files (stdlib python; a controller HTTP server that Hermes or the platform can call):
- vault.py        : Local secret vault. NEVER sends secrets to any network/cloud model.
                    Store secrets in a file under data/vault.json (mode 0600) with an
                    AES-GCM encrypt via `cryptography` IF available ELSE a clear
                    ::MODE:: sandbox that at least refuses to ever transmit values and
                    supports get(name)->Optional[str]. Methods: set(name, value),
                    get(name), placeholders() -> list. Redact() helper replaces
                    "{NAME}" placeholders in a prompt with NO secret values, only the
                    placeholder name (so cloud models never see real values).
- planner.py      : one goal -> task DAG. parse a natural-language GOAL string, produce
                    a list[BuildTask] each with {step, feature, prompt, deps[], test_hint}.
                    Deterministic template pipeline (goalify: spec -> epics -> tasks).
                    Include: a goal->plan decomposer that yields 4-8 cohesive steps with
                    test hints. Provide enrich_prompt(task) that expands a terse prompt
                    into a detailed one (this is the "make bigger prompts" feature).
- build_provider.py: orchestrate one-prompt->program. Worker runner that takes a plan,
                    for each task runs (a) a local python worker or (b) shells out to an
                    external LLM via HTTP if the caller passes a URL+key_env (NEVER logs
                    the key), collecting artifacts. Provide run_plan(plan) that writes
                    each artifact under data/build_sessions/<session_id>/ and a
                    manifest.json. Iterative: if a task's test_hint present, run the test
                    and if it fails, regenerate once (max 2 attempts) appending the error.
- controller.py    : a tiny local HTTP server (http.server on 8913) exposing:
                    POST /plan {goal} -> {plan:[...]}           (planner)
                    POST /enrich {prompt} -> {prompt: big_prompt}  (prompt enlarger)
                    POST /program {goal} -> {program_artifacts, session_id}
                      (calls build_provider; returns paths + logs)
                    GET  /health
                    These are the endpoints the platform's hermes_controller can call.

CONSTRAINTS:
- english comments; every module docstring states intent.
- NEVER transmit secret values. The only "network" allowed is an explicitly-injected
  HTTP POST to an LLM that uses placeholder redaction. Otherwise server is local-only.
- Tests: prove (1) redaction strips real secrets leaving placeholder names,
  (2) planner produces >=4 steps with deps, (3) build_provider run_plan produces files +
  manifest.json, (4) controller endpoints respond. Run pytest, FIX green, report counts.
- Port: 8913. Do not conflict with existing listeners; if 8913 busy, announce and pick 8914.

DELIVERABLE: files written + both unit and controller tests GREEN (real numbers), plus
STATUS_LOCAL_CONTROLLER.md with PASS/FAIL board + "what adds R / what to drop" +
UNVALIDATED. English-only.