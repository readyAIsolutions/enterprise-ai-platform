"""ENI Response Hardening module.

Detects and repairs the Hermes agent output-length / truncation ceilings so long
outputs never dead-end on "Response truncated due to output length limit".

WHY THIS EXISTS
---------------
Hermes's agent/conversation_loop.py bounds truncation recovery with fixed retry
caps, the worst being `truncated_tool_call_retries < 1`: a tool call (e.g. a huge
delegate_task arguments JSON) that gets cut off at the model's output ceiling was
retried ONCE then hard-refused with "Response truncated due to output length
limit". This module raises every cap to 8 and injects a completion-gating prompt
for truncated tool calls so the model resumes the cut JSON instead of re-issuing
the same oversized call and re-dead-locking.

audit() -> inspect current values. repair() -> apply the fix (idempotent, backups
the original, refuses invalid syntax).

Version: 1.0.0
"""
from __future__ import annotations

import logging
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Optional

from enterprise.platform_kernel import HealthStatus, Module, module

logger = logging.getLogger(__name__)

# (sentinel text, healthy threshold)
_EXPECTED_CAPS = [
    ("truncated_tool_call_retries < ", 8),
    ("length_continue_retries < ", 8),
    ("_codex_incomplete_retries <", 8),
    ("_invalid_json_retries <", 8),
    ("_empty_content_retries <", 8),
]

_COMPLETION_MARKER = "instructing JSON completion"


def locate_conversation_loop() -> Optional[Path]:
    """Locate the installed agent/conversation_loop.py via sys.path."""
    seen = set()
    for base in sys.path:
        if not base or base in seen:
            continue
        seen.add(base)
        try:
            root = Path(base).resolve()
        except Exception:
            continue
        if not root.is_dir():
            continue
        cand = root / "agent" / "conversation_loop.py"
        if cand.is_file():
            return cand
        # Some installs keep agent under a subpackage
        for sub in list(root.iterdir()) if root.exists() else []:
            try:
                c2 = sub / "agent" / "conversation_loop.py"
                if c2.is_file():
                    return c2
            except Exception:
                continue
    return None


def audit(path: Optional[Path] = None) -> dict[str, Any]:
    target = path or locate_conversation_loop()
    if target is None or not target.is_file():
        return {"ok": False, "found": False, "error": "conversation_loop.py not found"}
    src = target.read_text(errors="replace")
    caps = {}
    for sentinel, want in _EXPECTED_CAPS:
        key = sentinel.strip().strip("<").strip()
        m = re.search(re.escape(sentinel) + r"\s*(\d+)", src)
        current = int(m.group(1)) if m else None
        caps[key] = {"current": current, "healthy": want,
                     "ok": current is not None and current >= want}
    has_completion = _COMPLETION_MARKER in src
    caps["_toolcall_completion_patch"] = {"present": has_completion, "ok": has_completion}
    repair_needed = any(not c.get("ok") for c in caps.values())
    return {"ok": not repair_needed, "found": True, "path": str(target),
            "caps": caps, "repair_needed": repair_needed}


def repair(path: Optional[Path] = None) -> dict[str, Any]:
    target = path or locate_conversation_loop()
    if target is None or not target.is_file():
        return {"ok": False, "error": "conversation_loop.py not found"}
    src = target.read_text(errors="replace")
    original = src

    # 1) Raise every cap's integer to its healthy threshold. Sentinel may or may
    #    not have a trailing space; normalize so we never double the space and we
    #    always leave exactly one space before the number.
    for sentinel, want in _EXPECTED_CAPS:
        base = sentinel.rstrip()
        src = re.sub(re.escape(base) + r"\s*(\d+)", lambda m, w=want: f"{base} {w}", src)

    # 2) Decision: repair may be called on a version that has the OLD single-retry
    #    block (pre-this-fix) OR the NEW completion block (already patched earlier
    #    in-session). If the NEW completion marker is absent, rewire the block.
    src = _apply_toolcall_completion(src)

    changed = src != original
    if changed:
        backup = target.with_name(target.name + ".bak_response_hardening")
        if not backup.exists():
            shutil.copyfile(target, backup)
        try:
            compile(src, str(target), "exec")
        except SyntaxError as e:
            return {"ok": False, "error": f"repair produced invalid syntax: {e}",
                    "path": str(target)}
        target.write_text(src)
    return {"ok": True, "changed": changed, "path": str(target)}


def _apply_toolcall_completion(src: str) -> str:
    """If our completion marker is absent, transform the old single-retry
    truncated-tool-call branch into the 8-retry-with-continuation form."""
    if _COMPLETION_MARKER in src:
        return src  # already fixed

    # Old block (what ships upstream) — matched by its distinctive vprint text.
    old_vprint = "Truncated tool call detected — retrying API call"
    if old_vprint not in src:
        # Unknown shape; best-effort: just ensure the `< 1` is elevated.
        return src.replace("truncated_tool_call_retries < 1",
                           "truncated_tool_call_retries < 8")

    nrep = src
    nrep = nrep.replace(old_vprint, _COMPLETION_MARKER)

    # Insert a user continuation message right before that branch's `continue`.
    anchor = nrep.find(_COMPLETION_MARKER)
    cont = nrep.find("continue", anchor)
    if cont != -1:
        # compute indent from line containing 'continue'
        line_start = nrep.rfind("\n", 0, cont) + 1
        indent = nrep[line_start:cont]
        msg = (
            'messages.append({"role": "user", "content": '
            '"[System: Your previous tool call returned truncated (incomplete) '
            'JSON arguments because it exceeded the output length limit. Do NOT '
            're-issue the full original call. Resume EXACTLY from where the JSON '
            'arguments were cut off, complete the argument fields, and close the '
            "JSON with the final '}'. Keep the parameters compact. Emit ONLY the "
            'repaired tool call now.]"})\n'
        )
        splice = indent + msg + indent + "continue"
        # remove the original `continue` (cont+8 = len('continue'))
        orig_cont_line = nrep[line_start:cont + len("continue")]
        nrep = nrep[:line_start] + splice + nrep[cont + len("continue"):]
    return nrep


@module(
    name="response_hardening",
    version="1.0.0",
    config_defaults={"auto_repair": False, "healthy_threshold": 8},
)
class ResponseHardeningModule(Module):
    """Audits/repairs the Hermes agent output-limit caps."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._last_audit: dict[str, Any] = {}

    async def initialize(self) -> None:
        self._last_audit = audit()
        if self.config.get("auto_repair") and self._last_audit.get("ok") is not True:
            repair()
            self._last_audit = audit()
            logger.info("Response hardening auto-repair complete ok=%s",
                        self._last_audit.get("ok"))
        self.status = HealthStatus.HEALTHY
        logger.info("Response Hardening module initialized")

    async def health_check(self) -> HealthStatus:
        if self._last_audit.get("found") is not True:
            return HealthStatus.UNHEALTHY
        return HealthStatus.HEALTHY

    async def shutdown(self) -> None:
        self.status = HealthStatus.UNKNOWN
        logger.info("Response Hardening module shutdown")

    def get_audit(self) -> dict[str, Any]:
        return dict(self._last_audit)

    def apply_repair(self) -> dict[str, Any]:
        result = repair()
        self._last_audit = audit()
        return result


def create_response_hardening_module(config: dict[str, Any] | None = None) -> ResponseHardeningModule:
    return ResponseHardeningModule(config)


__all__ = [
    "ResponseHardeningModule",
    "create_response_hardening_module",
    "audit",
    "repair",
    "locate_conversation_loop",
    "_EXPECTED_CAPS",
    "__version__",
    "__module_name__",
]
__version__ = "1.0.0"
__module_name__ = "response_hardening"