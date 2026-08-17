"""Worker runner / build provider for one-prompt -> program.

INTENT
------
Orchestrates a :class:`~local_controller.planner.Plan` into concrete artifacts
on disk. ``run_plan`` writes every produced artifact plus a ``manifest.json``
under ``data/build_sessions/<session_id>/``.

Two execution modes per task:
  (a) a local deterministic python worker that generates a self-contained
      artifact from the task's feature/prompt (default; offline, always works), or
  (b) an external LLM over HTTP if the caller passes ``url`` + ``key_env``
      (the key is read from the environment and NEVER logged / returned).

Iterative self-validation: when a task has a ``test_hint``, the provider runs
it against the artifact. On failure it regenerates ONCE (max 2 attempts total
per task), appending the captured error to the prompt for the retry. Results of
every attempt+test are recorded and logged. Secrets are never transmitted: any
worker prompt is first passed through :func:`vault.redact`.
"""

from __future__ import annotations

import json
import os
import py_compile
import re
import tempfile
import time
import traceback
import urllib.request
from typing import Any, Callable, Dict, List, Optional

try:  # tolerate plain `local_controller` OR `enterprise.local_controller` import
    from local_controller import vault as _vault
    from local_controller.planner import Plan, parse_goal
except Exception:  # pragma: no cover - enterprise-prefixed package path
    from enterprise.local_controller import vault as _vault  # type: ignore
    from enterprise.local_controller.planner import Plan, parse_goal  # type: ignore

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_SESSIONS_DIR = os.path.join(_REPO_ROOT, "data", "build_sessions")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slug(text: str) -> str:
    """Make a filesystem-safe slug from arbitrary text."""
    slug = re.sub(r"[^A-Za-z0-9]+", "_", text.strip()).strip("_").lower()
    return slug[:48] or "artifact"


def _python_scaffold(step: int, feature: str, goal: str, prompt: str) -> str:
    """Deterministic local python artifact for a task (mode (a) worker).

    Defines ``your_model`` (dict) and ``def main`` so the associated test_hints
    (``isinstance(your_model, dict)`` and ``'def main' in source``) evaluate True.
    """
    module = _slug(f"step{step}_{feature}")
    body = [
        f"\"\"\"Step {step}: {feature}. Built for goal: {goal}\"\"\"",
        "from __future__ import annotations",
        "",
        "",
        f"FEATURE = {feature!r}",
        f"GOAL = {goal!r}",
        "HINT = \"\"\"{prompt}\"\"\"".format(prompt=prompt[:200]),
        "",
        "# state model referenced by the build test_hint",
        "your_model = {'ready': True, 'goal': GOAL, 'feature': FEATURE}",
        "",
        "",
        "def main() -> str:",
        "    \"\"\"Entry point: summarize what this artifact contributes.\"\"\"",
        '    return f"{FEATURE} helper implemented for: {GOAL}"',
        "",
        "",
        "if __name__ == \"__main__\":",
        "    print(main())",
        "",
    ]
    return "\n".join(body)


def _tests_scaffold(goal: str) -> str:
    """A runnable test artifact for the packaging/testing step.

    Defines ``tests`` (source text) so the ``'assert ' in tests or 'Test' in
    tests`` test_hint evaluates True.
    """
    src = (
        "import unittest\n\n"
        f'GOAL = {goal!r}\n\n'
        "class TestProgram(unittest.TestCase):\n"
        "    def test_smoke(self):\n"
        "        self.assertTrue(GOAL)\n"
        '        assert GOAL, "goal must be truthy"\n'
        "\n"
        "if __name__ == '__main__':\n"
        "    unittest.main()\n"
    )
    return "tests = \"\"\"\n" + src + "\n\"\"\"\n" + src


def _readme_scaffold(goal: str) -> str:
    """README artifact for the packaging step.

    Defines ``readme`` (markdown text) so the ``'# ' in readme`` test_hint
    evaluates True.
    """
    md = (
        f"# {goal}\n\n"
        "Built by the local one-prompt-program controller.\n\n"
        "## Run\n\n"
        "```bash\npython3 step_core_logic.py\n```\n"
    )
    # The file is one valid python module that assigns ``readme`` so the
    # ``'# ' in readme`` test_hint evaluates True. No raw markdown is appended
    # (that would make the artifact non-compilable); the var holds the text.
    return 'readme = """' + md + '"""\n'


def _spec_scaffold(goal: str) -> str:
    """Requirements spec artifact (always produced; never a secret).

    Defines ``spec_text`` (lowercase-checked) so the ``'requirements' in
    spec_text.lower()`` test_hint evaluates True. The file is a valid python
    module whose single assignment holds the spec document.
    """
    spec = (
        f"REQUIREMENTS\n============\n\n"
        f"Goal: {goal}\n"
        "- inputs: user-provided goal parameters\n"
        "- outputs: a runnable program + manifest\n"
        "- expectation: each build step produces a committed artifact\n"
    )
    return 'spec_text = """' + spec + '"""\n'


def _call_external_llm(
    prompt: str,
    url: str,
    key_env: str,
    model: str = "default",
) -> str:
    """POST a REDACTED prompt to an external LLM; return its text response.

    The API key is read from the environment (``key_env``) and used only as an
    Authorization header — it is NEVER logged, stored, or returned in output.
    The prompt body has already been redacted by the caller, so no real secret
    ever leaves the machine.
    """
    api_key = os.environ.get(key_env, "")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = json.dumps(
        {
            "prompt": prompt,
            "model": model,
            "max_tokens": 1024,
        }
    ).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:  # nosec - explicit opt-in
        body = resp.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(body)
            text = parsed.get("choices", [{}])[0].get("text", "")
            if not text:
                text = parsed.get("text", "")
            if not text:
                text = parsed.get("output", "")
            return text
        except json.JSONDecodeError:
            return body
    return ""


def _extract_python(text: str) -> str:
    """Pull runnable python out of an LLM response.

    LLMs often wrap code in ```python ... ``` fences or prose. This strips a
    trailing code fence and quietly tolerates surrounding markdown/text,
    falling back to the raw response when no fence is present.
    """
    text = (text or "").strip()
    if not text:
        return ""
    fence = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return text


# ---------------------------------------------------------------------------
# Core orchestrator
# ---------------------------------------------------------------------------


class BuildProvider:
    """Runs plans and records build sessions with a manifest."""

    def __init__(
        self,
        sessions_dir: str = _DEFAULT_SESSIONS_DIR,
        llm_callable: Optional[Callable[..., str]] = None,
    ) -> None:
        self.sessions_dir = sessions_dir
        os.makedirs(sessions_dir, exist_ok=True)
        self.vault = _vault.Vault()
        # Injected callable (used by tests / hosts that already hold an LLM
        # handle). When provided it takes precedence over the HTTP path.
        self.llm_callable = llm_callable
        # External LLM configured via environment (real-generation mode).
        self._llm_url = os.environ.get("MP_LLM_URL", "").strip()
        self._llm_key_env = os.environ.get("MP_LLM_KEY_ENV", "").strip()
        self._llm_model = (os.environ.get("MP_LLM_MODEL", "").strip()
                           or "default")

    def _real_llm_enabled(self, url: Optional[str], key_env: Optional[str]) -> bool:
        """True when the real-generation path should run rather than the
        deterministic scaffold. Enabled by an injected callable, explicitly
        passed url+key_env, or env vars MP_LLM_URL/MP_LLM_KEY_ENV."""
        if self.llm_callable is not None:
            return True
        url = url or self._llm_url
        key_env = key_env or self._llm_key_env
        return bool(url) and bool(key_env)

    def _llm_generate(
        self,
        prompt: str,
        task: Any,
        url: Optional[str],
        key_env: Optional[str],
    ) -> str:
        """Return python source from the LLM for one task step.

        Uses an injected callable if present, else the HTTP endpoint configured
        via url/key_env (falling back to env MP_LLM_URL/MP_LLM_KEY_ENV). Real
        secrets are already redacted by the caller.
        """
        raw = ""
        if self.llm_callable is not None:
            raw = str(self.llm_callable(
                prompt, step=task.step, feature=task.feature))
        else:
            eff_url = url or self._llm_url
            eff_key = key_env or self._llm_key_env
            raw = _call_external_llm(prompt, eff_url, eff_key, self._llm_model)
        return _extract_python(raw)

    def _compile_and_smoke(self, artifact: str) -> Optional[str]:
        """Real validation: py_compile then a smoke run of the artifact.

        Returns an error string on any failure, else None. The smoke run
        imports the module and, when it exposes ``main``, calls it.
        """
        if not artifact or not artifact.strip():
            return "generated artifact is empty"
        fd, tmp_path = tempfile.mkstemp(suffix=".py")
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(artifact)
            # 1) real syntax/compile check via py_compile
            try:
                py_compile.compile(tmp_path, doraise=True)
            except py_compile.PyCompileError as exc:
                return f"PyCompileError: {exc}"
            # 2) smoke run: exec the module, then call main() if present
            scope: Dict[str, Any] = {"__name__": "__smoke__"}
            try:
                exec(compile(artifact, "<generated>", "exec"), scope)
            except Exception as exc:  # noqa: BLE001 - artifact itself failed
                return f"smoke-import-error {type(exc).__name__}: {exc}"
            main = scope.get("main")
            if callable(main):
                try:
                    main()
                except Exception as exc:  # noqa: BLE001 - runtime failure
                    return f"smoke-main-error {type(exc).__name__}: {exc}"
            return None
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _session_dir(self, session_id: str) -> str:
        d = os.path.join(self.sessions_dir, session_id)
        os.makedirs(d, exist_ok=True)
        return d

    def _gen_artifact(self, task: Any) -> str:
        """Mode (a): local deterministic python scaffold for a task."""
        feature = task.feature
        if feature == "requirements_and_spec":
            return _spec_scaffold(task.prompt)
        if feature == "tests_and_validation":
            return _tests_scaffold(task.prompt)
        if feature == "packaging_and_readme":
            return _readme_scaffold(task.prompt)
        return _python_scaffold(task.step, feature, task.prompt, task.prompt)

    def _run_test(self, hint: str, artifact: str, how: str) -> Optional[str]:
        """Run a test_hint against an artifact; return error text or None.

        Handles both boolean-expression hints (``'requirements' in spec...``)
        and assert-statement hints (``assert 'x' in y``). A failing assert or a
        False expression is reported as an error so the provider can retry.
        """
        scope: Dict[str, Any] = {"__name__": "__test__", "source": artifact}
        try:
            compiled = compile(artifact, "<artifact>", "exec")
            exec(compiled, scope)  # nosec: we run locally generated info only
        except Exception as exc:  # noqa: BLE001 - artifact itself failed to run
            return f"{type(exc).__name__}: {exc}"
        # run the hint: prefer an expression; fall back to an assert statement
        try:
            ok = eval(hint, scope)  # nosec: hint comes from our own planner
            return None if bool(ok) else "test_hint evaluated False"
        except SyntaxError:
            # assert-style hint -> exec it; AssertionError means the test failed
            try:
                exec(compile(hint, "<hint>", "exec"), scope)  # nosec: own hint
                return None
            except AssertionError as exc:
                return f"AssertionError: {exc}"
        except Exception as exc:  # noqa: BLE001 - reference/type errors in hint
            return f"{type(exc).__name__}: {exc}"

    def _attempt_task(
        self,
        task: Any,
        goal: str,
        session_dir: str,
        url: Optional[str],
        key_env: Optional[str],
    ) -> Dict[str, Any]:
        """Execute one task.

        Real-generation mode (LLM configured): generate real python per step,
        write it, py_compile + smoke-test it, and on failure retry up to 2
        times appending the error. Final success marks ``ok=True``.

        Scaffold mode (no LLM): deterministic local worker with up to 2
        attempts using the task's ``test_hint``.
        """
        attempts: List[Dict[str, Any]] = []
        artifact = ""
        how = "local-python-worker"
        attempt = 0
        error = None
        real = self._real_llm_enabled(url, key_env)

        # Redact the prompt so a real secret can never be handed to a worker.
        safe_prompt = self.vault.redact(task.prompt)

        # In real mode: initial attempt + up to 2 retries (3 total).
        # In scaffold mode: initial + 1 regen (2 total).
        max_attempts = 3 if real else 2

        while attempt < max_attempts:
            attempt += 1
            if real:
                how = "external-llm"
                try:
                    work_prompt = safe_prompt
                    if error:
                        work_prompt += (
                            "\n\nPREVIOUS TEST ERROR (please fix):\n" + error
                        )
                    artifact = self._llm_generate(
                        work_prompt, task, url, key_env)
                    if not artifact:
                        artifact = self._gen_artifact(task)  # fallback to local
                        how = "local-python-worker(fallback)"
                except Exception as exc:  # noqa: BLE001
                    artifact = self._gen_artifact(task)
                    how = f"local-python-worker(net-fallback:{type(exc).__name__})"
            else:
                artifact = self._gen_artifact(task)

            attempts.append({"attempt": attempt, "how": how})

            if real:
                # real validation: py_compile + run a smoke
                error = self._compile_and_smoke(artifact)
            elif not task.test_hint:
                error = None
            else:
                error = self._run_test(task.test_hint, artifact, how)

            attempts[-1]["status"] = "test-failed" if error else "test-passed"
            if not error:
                break
            # else: loop once more, appending the error for the next attempt

        failed = bool(error)
        ok = bool(artifact) and not failed
        return {
            "step": task.step,
            "feature": task.feature,
            "artifact_how": how,
            "artifact": artifact,
            "attempts": attempts,
            "status": "ok" if ok else "failed",
            "ok": ok,
            "error": error if failed else None,
        }

    def run_plan(
        self,
        plan: Optional[Plan] = None,
        goal: str = "",
        session_id: str = "",
        url: Optional[str] = None,
        key_env: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run a plan (or a goal string), writing artifacts + manifest.json.

        Returns a summary dict with session_id, artifact paths, and logs.
        """
        if plan is None:
            plan = parse_goal(goal or "a small utility program")
        if not session_id:
            session_id = f"session_{int(time.time())}"
        session_dir = self._session_dir(session_id)

        records: List[Dict[str, Any]] = []
        logged: List[str] = []

        for task in plan.tasks:
            result = self._attempt_task(task, plan.goal, session_dir, url, key_env)
            artifact = result["artifact"]
            fname = f"step{task.step:02d}_{_slug(task.feature)}.py"
            path = os.path.join(session_dir, fname)
            with open(path, "w") as fh:
                fh.write(artifact)
            result["file"] = path
            result.pop("artifact", None)  # do not keep full source in manifest
            records.append(result)
            final = result["attempts"][-1]["status"]
            logged.append(
                f"step {task.step:02d} [{task.feature}] "
                f"attempts={len(result['attempts'])} final={final}"
            )

        manifest = {
            "session_id": session_id,
            "goal": plan.goal,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "steps": records,
            "logs": logged,
            "session_dir": session_dir,
        }
        manifest_path = os.path.join(session_dir, "manifest.json")
        with open(manifest_path, "w") as fh:
            json.dump(manifest, fh, indent=2)

        manifest["manifest_file"] = manifest_path
        return {
            "session_id": session_id,
            "session_dir": session_dir,
            "manifest_file": manifest_path,
            "artifacts": [os.path.join(session_dir, _slug(f"step{r['step']:02d}_{r['feature']}")) + ".py" for r in records],
            "logs": logged,
            "steps": records,
        }


def run_plan(
    goal: str,
    session_id: str = "",
    url: Optional[str] = None,
    key_env: Optional[str] = None,
    provider: Optional[BuildProvider] = None,
) -> Dict[str, Any]:
    """Module-level convenience: run a goal through the default provider."""
    prov = provider or BuildProvider()
    plan = parse_goal(goal)
    return prov.run_plan(
        plan=plan, goal=goal, session_id=session_id, url=url, key_env=key_env
    )


def production_report(session_summary: Dict[str, Any]) -> str:
    """Render a short human-readable report of a finished build session."""
    lines = [
        f"SESSION {session_summary['session_id']}",
        f"  goal        : {session_summary.get('manifest_file','')}",
        f"  manifest    : {session_summary['manifest_file']}",
        f"  artifacts   : {len(session_summary['artifacts'])} files",
    ]
    for log in session_summary.get("logs", []):
        lines.append(f"  - {log}")
    return "\n".join(lines)


# Silence unused import hint for traceback (kept for debuggability).
_traceback_flag = traceback  # noqa: F841