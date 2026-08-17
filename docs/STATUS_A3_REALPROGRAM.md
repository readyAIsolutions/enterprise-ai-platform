STATUS: A3 Upgrade complete -- real-generation engine implemented.

SCOPE OWNED (all modified):
  enterprise/local_controller/build_provider.py
  enterprise/local_controller/tests/test_local_controller.py
  NEW: none (no new files needed)

WHAT I DID
----------
1. build_provider.py -- upgraded the one-prompt>program engine to produce REAL
   executable programs when an external LLM is configured, while keeping the
   deterministic scaffold fallback for the no-LLM case so existing tests stay
   green.

   Changes:
   - BuildProvider.__init__ now additionally accepts an optional llm_callable
     (injected LLM handle, used by tests) and reads env config:
       MP_LLM_URL, MP_LLM_KEY_ENV, MP_LLM_MODEL.
   - Added _real_llm_enabled(url, key_env): True when an external LLM is in
     play (injected callable OR explicit url+key_env OR env MP_LLM_URL+KEY_ENV).
   - Added _llm_generate(): produces real python per step via the callable,
     else the HTTP endpoint, then _extract_python() strips ```python fences.
   - Added _compile_and_smoke(): REAL validation = py_compile (PyCompileError
     caught) then a smoke run (exec module, call main() if present).
   - Rewrote _attempt_task: in real mode -> up to 3 attempts (initial + 2
     retries), appends "PREVIOUS TEST ERROR..." to the prompt on each retry;
     validates via py_compile+smoke; marks final result ok=True with status
     "ok" on success, ok=False + error on exhaustion. Scaffold mode unchanged
     (2 attempts, test_hint-based, deterministic).
   - Added helper _extract_python().

   ALL public API signatures preserved: BuildProvider, plan_runner.run_plan,
   /program endpoint behavior (controller.py untouched).

2. tests/test_local_controller.py -- added 4 new tests proving the real path:
   - test_real_generation_compiles_and_runs: fake LLM -> all steps ok=True,
     real files written, "external-llm" how.
   - test_real_generation_retries_on_failure: broken first program -> retried
     with the error appended -> final ok=True.
   - test_real_generation_via_env_config: env MP_LLM_* + monkeypatched HTTP
     -> real path active.
   - test_real_generation_exhausts_retries_then_marks_failed: forever-broken
     -> 3 attempts, all failed, ok=False.

TEST RESULTS
------------
  cd /home/hunter/Desktop/Enterprise\ Builder && \
  PYTHONPATH=... python3 -m pytest enterprise/local_controller -q
  -> 17 passed (13 original + 4 new). ALL GREEN.

NOTE on full-suite: `pytest enterprise -q` fails during COLLECTION on
skills_pack template tests (missing pyproject.toml, missing _qt module).
These are unrelated to this workstream, pre-existing, and in files I do not
own (skills_pack/*). The scoped local_controller suite is fully green.

FILES MODIFIED
--------------
  /home/hunter/Desktop/Enterprise Builder/enterprise/local_controller/build_provider.py
  /home/hunter/Desktop/Enterprise Builder/enterprise/local_controller/tests/test_local_controller.py

ISSUES ENCOUNTERED
------------------
- One new test initially patched the wrong module identity (enterprise.* vs
  local_controller.*); fixed by patching sys.modules[BuildProvider.__module__].
- Full-suite collection errors in skills_pack are pre-existing/unrelated.
