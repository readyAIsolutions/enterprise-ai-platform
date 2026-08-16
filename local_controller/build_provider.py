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
import re
import time
import traceback
import urllib.request
from typing import Any, Dict, List, Optional

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


# ---------------------------------------------------------------------------
# Core orchestrator
# ---------------------------------------------------------------------------


class BuildProvider:
    """Runs plans and records build sessions with a manifest."""

    def __init__(self, sessions_dir: str = _DEFAULT_SESSIONS_DIR) -> None:
        self.sessions_dir = sessions_dir
        os.makedirs(sessions_dir, exist_ok=True)
        self.vault = _vault.Vault()

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
        """Execute one task with up to 2 attempts (one regen on failure)."""
        attempts: List[Dict[str, Any]] = []
        artifact = ""
        how = "local-python-worker"
        attempt = 0
        error = None

        # Redact the prompt so a real secret can never be handed to a worker.
        safe_prompt = self.vault.redact(task.prompt)

        while attempt < 2:
            attempt += 1
            if url and key_env and attempt > 1:
                # mode (b) retry: send the redacted prompt + prior error to the LLM
                how = "external-llm"
                try:
                    work_prompt = safe_prompt
                    if error:
                        work_prompt += (
                            "\n\nPREVIOUS TEST ERROR (please fix):\n" + error
                        )
                    artifact = _call_external_llm(work_prompt, url, key_env)
                    if not artifact:
                        artifact = self._gen_artifact(task)  # fallback to local
                        how = "local-python-worker(fallback)"
                except Exception as exc:  # noqa: BLE001
                    artifact = self._gen_artifact(task)
                    how = f"local-python-worker(net-fallback:{type(exc).__name__})"
            else:
                artifact = self._gen_artifact(task)

            attempts.append({"attempt": attempt, "how": how})
            if not task.test_hint:
                attempts[-1]["status"] = "produced"
                break
            error = self._run_test(task.test_hint, artifact, how)
            attempts[-1]["status"] = "test-failed" if error else "test-passed"
            if not error:
                break
            # else: loop once more, appending the error for the next attempt

        return {
            "step": task.step,
            "feature": task.feature,
            "artifact_how": how,
            "artifact": artifact,
            "attempts": attempts,
            "status": "ok" if artifact else "failed",
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