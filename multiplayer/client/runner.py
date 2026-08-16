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