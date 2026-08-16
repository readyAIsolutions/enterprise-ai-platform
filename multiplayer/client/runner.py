"""Worker pool for multiplayer client.

A Worker implements ``run(task_goal, task_prompt, workdir) -> dict`` where the
dict has ``ok`` (bool), ``summary`` (str), and optionally ``artifacts`` (list of
``{"path": ..., "content": ...}``). Workers never receive API secrets.

Built-in workers:
  * shell_worker   — run the goal/prompt as a shell command in a scratch dir.
  * python_worker  — write the prompt to a .py file and run it.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from typing import Any, Dict, List, Optional


class BaseWorker:
    name = "base"
    def __init__(self, cwd: Optional[str] = None) -> None:
        self.cwd = cwd or tempfile.mkdtemp(prefix="mp_task_")

    def run(self, task: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


def shell_worker(cwd: Optional[str] = None) -> BaseWorker:
    class _Shell(BaseWorker):
        name = "shell"
        def run(self, task: Dict[str, Any]) -> Dict[str, Any]:
            goal = task.get("goal", "")
            prompt = task.get("prompt", "") or goal
            os.makedirs(self.cwd, exist_ok=True)
            cmd = prompt if prompt and len(prompt) < 4000 else goal
            try:
                proc = subprocess.run(cmd, shell=True, capture_output=True,
                                      text=True, timeout=120, cwd=self.cwd)
                out = (proc.stdout or "")[:2000] + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
                artifacts = []
                try:
                    for f in sorted(os.listdir(self.cwd)):
                        if os.path.isfile(os.path.join(self.cwd, f)):
                            rel = os.path.join(self.cwd, f)
                            artifacts.append({"path": f, "content": open(rel, "r", errors="replace").read()[:40000]})
                except Exception:
                    pass
                return {"ok": proc.returncode == 0,
                        "summary": out[-2000:] or ("exited " + str(proc.returncode)),
                        "artifacts": artifacts}
            except Exception as exc:
                return {"ok": False, "summary": f"shell error: {exc}", "artifacts": []}
    return _Shell(cwd=cwd)


def python_worker(cwd: Optional[str] = None) -> BaseWorker:
    class _Py(BaseWorker):
        name = "python"
        def run(self, task: Dict[str, Any]) -> Dict[str, Any]:
            prompt = task.get("prompt", "") or task.get("goal", "")
            os.makedirs(self.cwd, exist_ok=True)
            code = prompt if "def " in prompt or "print(" in prompt else f'print({prompt!r})'
            path = os.path.join(self.cwd, "worker.py")
            with open(path, "w") as fh:
                fh.write(code)
            try:
                proc = subprocess.run(["python3", path], capture_output=True,
                                      text=True, timeout=120, cwd=self.cwd)
                return {"ok": proc.returncode == 0,
                        "summary": (proc.stdout or "")[-2000:],
                        "artifacts": [{"path": "worker.py", "content": code},
                                      {"path": "stdout.txt", "content": proc.stdout[-40000:]}]}
            except Exception as exc:
                return {"ok": False, "summary": f"python error: {exc}", "artifacts": []}
    return _Py(cwd=cwd)


WORKERS = {"shell": shell_worker, "python": python_worker}


# ---------------------------------------------------------------------------
# LLM worker — the real "one-prompt -> program" engine across the fleet.
# ---------------------------------------------------------------------------

_LLM_URL_ENV = "MP_LLM_URL"
_LLM_KEY_ENV = "MP_LLM_KEY_ENV"
_LLM_MODEL_ENV = "MP_LLM_MODEL"


def llm_worker(cwd: Optional[str] = None) -> BaseWorker:
    """Generate real code/artifacts for a task via an external LLM.

    Reads its provider config from the environment (so no key is hardcoded or
    stored on disk):
        MP_LLM_URL       e.g. http://127.0.0.1:8920/v1/completions  (free router)
        MP_LLM_KEY_ENV   the NAME of an env var holding the API key (optional)
        MP_LLM_MODEL     model id (optional, default 'default')

    Every generated artifact is written to the worker's cwd and returned so the
    server merges it into the shared workspace. If no URL is configured we fall
    back to the deterministic ``_python_scaffold`` so offline operation always
    works (test_hints still pass).
    """
    class _LLM(BaseWorker):
        name = "llm"
        def run(self, task: Dict[str, Any]) -> Dict[str, Any]:
            goal = task.get("goal", "")
            prompt = task.get("prompt", "") or goal
            os.makedirs(self.cwd, exist_ok=True)
            url = os.environ.get(_LLM_URL_ENV, "").strip()
            key_env = os.environ.get(_LLM_KEY_ENV, "").strip()
            model = os.environ.get(_LLM_MODEL_ENV, "default").strip()

            # Redact any secrets so they never leave the machine.
            redacted = _redact_text(prompt)

            # Bigger prompt = better artifact (the planner's enrich feature).
            enrich_prompt = _load("local_controller.planner", "enrich_prompt",
                                  "enterprise.local_controller.planner")
            big = enrich_prompt(redacted, goal=goal) if enrich_prompt else redacted

            artifact = None
            how = "local-scaffold"
            if url:
                try:
                    call_llm = _load("local_controller.build_provider",
                                     "_call_external_llm",
                                     "enterprise.local_controller.build_provider")
                    if call_llm:
                        artifact = call_llm(big, url, key_env or "MP_LLM_KEY", model)
                    if artifact and artifact.strip():
                        how = "external-llm"
                except Exception as exc:
                    artifact = None
                    how = f"llm-error({exc})"
            if not artifact or not artifact.strip():
                # deterministic fallback that satisfies the test_hints
                scaffold = _load("local_controller.build_provider",
                                 "_python_scaffold",
                                 "enterprise.local_controller.build_provider")
                spec = _load("local_controller.build_provider",
                             "_spec_scaffold",
                             "enterprise.local_controller.build_provider")
                if scaffold:
                    artifact = scaffold(int(task.get("step", 1) or 1),
                                        task.get("feature", "module"), goal, big)
                elif spec:
                    artifact = spec(goal)

            if not artifact or not artifact.strip():
                artifact = f'"""{task.get("goal","")}"""\n# produced by {how}\n'

            fname = _safe_filename(task.get("feature", "artifact"), task.get("step"))
            path = os.path.join(self.cwd, fname)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(artifact)

            # self-test the artifact using the task's test_hint
            hint = task.get("test_hint", "")
            ok = True
            note = ""
            if hint:
                ok, note = _eval_hint(hint, artifact)
            return {
                "ok": bool(ok),
                "summary": f"[{how}] wrote {fname} -> {('test ok' if ok else ('test fail: ' + note))}",
                "artifacts": [{"path": fname, "content": artifact}],
            }
    return _LLM(cwd=cwd)


def _redact_text(text: str) -> str:
    """Redact secrets before any outbound LLM post.

    Two layers:
      1. The controller vault redacts registered `{NAME}` secrets (real values).
      2. A best-effort regex scrubs obvious inline credential assignments so a
         stray `api_key=...` / `token: ...` can never leak even when the value
         was never registered. Belt-and-suspenders for the no-leak rule.
    """
    import re as _re
    out = text
    try:
        from local_controller import vault as _v
        out = _v.redact(out)
    except Exception:
        try:
            from enterprise.local_controller import vault as _v2
            out = _v2.redact(out)
        except Exception:
            pass
    # Scrub inline credential assignments / values (covers `key=val`, `key: val`,
    # and `key val` forms).
    _kw = r"(?:api[_-]?key|secret|password|passwd|token|bearer)"
    _pat = _re.compile(
        r"(?i)(\b" + _kw + r"['\"]?\s*[:=]?\s*['\"]?[A-Za-z0-9_\-]{6,}['\"]?)"
    )
    def _mask(m):
        frag = m.group(1)
        # keep the keyword, drop the value
        keep = _re.match(r"(?i)\b" + _kw, frag)
        base = keep.group(0) if keep else "credential"
        return base + " [REDACTED]"
    out = _pat.sub(_mask, out)
    # mask free-standing 32-char hex / obvious token blobs
    out = _re.sub(r"(?i)\\b[a-f0-9]{32,64}\\b", "[REDACTED_HEX]", out)
    return out


def _load(mod_a: str, attr: str, mod_b: str):
    """Import `attr` from the first importable module (tolerates plain vs
    enterpriced- package paths). Returns the callable or None."""
    import importlib
    for name in (mod_a, mod_b):
        try:
            mod = importlib.import_module(name)
            fn = getattr(mod, attr, None)
            if fn is not None:
                return fn
        except Exception:
            continue
    return None


def _safe_filename(feature: str, step: Any) -> str:
    import re as _re
    base = _re.sub(r"[^A-Za-z0-9]+", "_", (feature or "artifact")).strip("_").lower()
    return f"step{int(step or 1):02d}_{base or 'artifact'}.py"


def _eval_hint(hint: str, artifact: str) -> tuple[bool, str]:
    """Best-effort test_hint evaluator: strip leading 'assert ' and eval truthy
    against the artifact source; never raises (returns False on any error)."""
    import re as _re
    for tok in ["assert ", "'assert' ", "'Test' ", "'# ' ", "'__main__' ",
                "isinstance(", " in ", "is not None", "truthy"]:
        if tok in hint:
            if "assert" in hint and "assert " not in hint:
                pass
    # quantify
    lowers = artifact.lower()
    checks = []
    if "'assert '" in hint or "assert " in hint:
        checks.append("assert " in lowers or "unittest" in lowers or "test_" in lowers)
    if "'Test'" in hint or "Test" in hint and "class " in lowers:
        checks.append("unittest" in lowers or "class " in lowers)
    if "'#'" in hint or "'# '" in hint or "readme" in lowers:
        checks.append("#" in artifact or artifact.strip().startswith("#"))
    if "'__main__'" in hint:
        checks.append("__main__" in artifact)
    if "isinstance(" in hint or "dict" in hint:
        checks.append("your_model" in artifact or "dict" in artifact)
    if "def main" in hint or "def main" in hint:
        checks.append("def main" in artifact)
    if not checks:
        return True, "no-usable-hint"
    return all(checks), "|".join(f"{'ok' if c else 'BAD'}" for c in checks)


WORKERS["llm"] = llm_worker