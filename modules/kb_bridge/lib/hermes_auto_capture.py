#!/usr/bin/env python3
"""
Hermes Auto-Capture Hooks
==========================
Automatically captures all Hermes operations to the Knowledge Base.
Monkey-patches Hermes tools, commands, and internals to log everything.
"""

from __future__ import annotations

import functools
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent))

from lib.hermes_kb_universal import (
    get_kb,
    store_operation,
    store_file_op,
    store_config_change,
    store_session,
    update_session_stats,
    end_session,
    store_pattern,
    search_patterns,
)


# ─── Global State ───────────────────────────────────────────────────────────

_capture_enabled = False
_current_session: str | None = None
_current_profile: str = "default"
_original_functions: dict[str, Callable] = {}


# ─── Session Management ─────────────────────────────────────────────────────


def start_capture_session(profile: str | None = None, session_name: str | None = None) -> str:
    """Start a new capture session."""
    global _capture_enabled, _current_session, _current_profile

    _current_profile = profile or os.environ.get("HERMES_PROFILE", "default")
    _current_session = session_name or f"hermes_{uuid.uuid4().hex[:8]}"

    store_session(_current_session, _current_profile, session_name or f"Hermes session {_current_session}")
    _capture_enabled = True

    return _current_session


def end_capture_session(summary: str | None = None) -> None:
    """End the current capture session."""
    global _capture_enabled, _current_session

    if _current_session:
        end_session(_current_session, summary)
        _current_session = None
    _capture_enabled = False


def get_current_session() -> str | None:
    return _current_session


def is_capture_enabled() -> bool:
    return _capture_enabled


# ─── Tool Capture ───────────────────────────────────────────────────────────


def capture_tool_call(tool_name: str):
    """Decorator to capture tool calls."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if not _capture_enabled or not _current_session:
                return await func(*args, **kwargs)

            start_time = time.perf_counter()
            input_data = {"args": str(args)[:500], "kwargs": str(kwargs)[:500]}

            try:
                result = await func(*args, **kwargs)
                duration_ms = int((time.perf_counter() - start_time) * 1000)

                # Extract output data
                output_data = {}
                if hasattr(result, "data"):
                    output_data = {"success": True, "data": str(result.data)[:1000]}
                elif hasattr(result, "stdout"):
                    output_data = {"stdout": result.stdout[:1000], "stderr": result.stderr[:1000], "exit_code": result.exit_code}
                else:
                    output_data = {"result": str(result)[:1000]}

                store_operation(
                    op_type="tool",
                    tool_name=tool_name,
                    input_data=input_data,
                    output_data=output_data,
                    result="success",
                    duration_ms=duration_ms,
                    session_id=_current_session,
                    profile=_current_profile,
                    working_dir=os.getcwd(),
                    tags=["tool", tool_name, "auto-capture"],
                )
                update_session_stats(_current_session, tool_delta=1)
                return result

            except Exception as e:
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                store_operation(
                    op_type="tool",
                    tool_name=tool_name,
                    input_data=input_data,
                    output_data={"error": str(e)},
                    result="error",
                    error_message=str(e),
                    duration_ms=duration_ms,
                    session_id=_current_session,
                    profile=_current_profile,
                    working_dir=os.getcwd(),
                    tags=["tool", tool_name, "auto-capture", "error"],
                )
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            if not _capture_enabled or not _current_session:
                return func(*args, **kwargs)

            start_time = time.perf_counter()
            input_data = {"args": str(args)[:500], "kwargs": str(kwargs)[:500]}

            try:
                result = func(*args, **kwargs)
                duration_ms = int((time.perf_counter() - start_time) * 1000)

                output_data = {"result": str(result)[:1000]}

                store_operation(
                    op_type="tool",
                    tool_name=tool_name,
                    input_data=input_data,
                    output_data=output_data,
                    result="success",
                    duration_ms=duration_ms,
                    session_id=_current_session,
                    profile=_current_profile,
                    working_dir=os.getcwd(),
                    tags=["tool", tool_name, "auto-capture"],
                )
                update_session_stats(_current_session, tool_delta=1)
                return result

            except Exception as e:
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                store_operation(
                    op_type="tool",
                    tool_name=tool_name,
                    input_data=input_data,
                    output_data={"error": str(e)},
                    result="error",
                    error_message=str(e),
                    duration_ms=duration_ms,
                    session_id=_current_session,
                    profile=_current_profile,
                    working_dir=os.getcwd(),
                    tags=["tool", tool_name, "auto-capture", "error"],
                )
                raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# ─── Command Capture ────────────────────────────────────────────────────────


def capture_command(command_name: str):
    """Decorator to capture command executions."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if not _capture_enabled or not _current_session:
                return await func(*args, **kwargs)

            start_time = time.perf_counter()
            input_data = {"args": str(args)[:500], "kwargs": str(kwargs)[:500]}

            try:
                result = await func(*args, **kwargs)
                duration_ms = int((time.perf_counter() - start_time) * 1000)

                output_data = {"result": str(result)[:1000]}

                store_operation(
                    op_type="command",
                    command_name=command_name,
                    input_data=input_data,
                    output_data=output_data,
                    result="success",
                    duration_ms=duration_ms,
                    session_id=_current_session,
                    profile=_current_profile,
                    working_dir=os.getcwd(),
                    tags=["command", command_name, "auto-capture"],
                )
                update_session_stats(_current_session, command_delta=1)
                return result

            except Exception as e:
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                store_operation(
                    op_type="command",
                    command_name=command_name,
                    input_data=input_data,
                    output_data={"error": str(e)},
                    result="error",
                    error_message=str(e),
                    duration_ms=duration_ms,
                    session_id=_current_session,
                    profile=_current_profile,
                    working_dir=os.getcwd(),
                    tags=["command", command_name, "auto-capture", "error"],
                )
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            if not _capture_enabled or not _current_session:
                return func(*args, **kwargs)

            start_time = time.perf_counter()
            input_data = {"args": str(args)[:500], "kwargs": str(kwargs)[:500]}

            try:
                result = func(*args, **kwargs)
                duration_ms = int((time.perf_counter() - start_time) * 1000)

                output_data = {"result": str(result)[:1000]}

                store_operation(
                    op_type="command",
                    command_name=command_name,
                    input_data=input_data,
                    output_data=output_data,
                    result="success",
                    duration_ms=duration_ms,
                    session_id=_current_session,
                    profile=_current_profile,
                    working_dir=os.getcwd(),
                    tags=["command", command_name, "auto-capture"],
                )
                update_session_stats(_current_session, command_delta=1)
                return result

            except Exception as e:
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                store_operation(
                    op_type="command",
                    command_name=command_name,
                    input_data=input_data,
                    output_data={"error": str(e)},
                    result="error",
                    error_message=str(e),
                    duration_ms=duration_ms,
                    session_id=_current_session,
                    profile=_current_profile,
                    working_dir=os.getcwd(),
                    tags=["command", command_name, "auto-capture", "error"],
                )
                raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# ─── File Operation Capture ─────────────────────────────────────────────────


def capture_file_read(original_func: Callable) -> Callable:
    """Wrap file read operations."""

    @functools.wraps(original_func)
    def wrapper(file_path: str, *args, **kwargs):
        result = original_func(file_path, *args, **kwargs)

        if _capture_enabled and _current_session:
            content = result if isinstance(result, str) else str(result)[:5000]
            line_count = content.count("\n") + 1 if content else 0
            store_file_op(
                file_path=file_path,
                operation="read",
                content=content,
                session_id=_current_session,
                profile=_current_profile,
                line_count=line_count,
            )
            update_session_stats(_current_session, file_delta=1)

        return result

    return wrapper


def capture_file_write(original_func: Callable) -> Callable:
    """Wrap file write operations."""

    @functools.wraps(original_func)
    def wrapper(file_path: str, content: str, *args, **kwargs):
        result = original_func(file_path, content, *args, **kwargs)

        if _capture_enabled and _current_session:
            line_count = content.count("\n") + 1 if content else 0
            store_file_op(
                file_path=file_path,
                operation="write",
                content=content,
                session_id=_current_session,
                profile=_current_profile,
                line_count=line_count,
            )
            update_session_stats(_current_session, file_delta=1)

        return result

    return wrapper


def capture_file_edit(original_func: Callable) -> Callable:
    """Wrap file edit operations."""

    @functools.wraps(original_func)
    def wrapper(file_path: str, *args, **kwargs):
        result = original_func(file_path, *args, **kwargs)

        if _capture_enabled and _current_session:
            # Read the file after edit to capture new content
            try:
                content = Path(file_path).read_text()
                line_count = content.count("\n") + 1
            except Exception:
                content = ""
                line_count = 0

            store_file_op(
                file_path=file_path,
                operation="edit",
                content=content,
                session_id=_current_session,
                profile=_current_profile,
                line_count=line_count,
            )
            update_session_stats(_current_session, file_delta=1)

        return result

    return wrapper


# ─── Config Change Capture ──────────────────────────────────────────────────


def capture_config_change(config_key: str, config_value: str | None, previous_value: str | None = None, config_type: str = "yaml", file_path: str | None = None):
    """Record a configuration change."""
    if not _capture_enabled or not _current_session:
        return

    store_config_change(
        profile=_current_profile,
        config_key=config_key,
        config_value=config_value,
        config_type=config_type,
        file_path=file_path,
        changed_by="hermes_auto",
        previous_value=previous_value,
    )


# ─── Auto-Patcher for Hermes ────────────────────────────────────────────────


def patch_hermes_tools():
    """Patch Hermes tool modules to auto-capture."""
    try:
        from lib.claude_code.tools import (
            bash_tool, file_read_tool, file_write_tool, file_edit_tool,
            glob_tool, grep_tool, task_create_tool, task_get_tool,
            task_update_tool, task_list_tool, agent_tool, web_fetch_tool,
            web_search_tool, mcp_tool, lsp_tool,
        )

        tools_to_patch = {
            "bash": bash_tool,
            "fileread": file_read_tool,
            "filewrite": file_write_tool,
            "fileedit": file_edit_tool,
            "glob": glob_tool,
            "grep": grep_tool,
            "task_create": task_create_tool,
            "task_get": task_get_tool,
            "task_update": task_update_tool,
            "task_list": task_list_tool,
            "agent": agent_tool,
            "web_fetch": web_fetch_tool,
            "web_search": web_search_tool,
            "mcp": mcp_tool,
            "lsp": lsp_tool,
        }

        for name, tool in tools_to_patch.items():
            if hasattr(tool, "call") and not hasattr(tool.call, "__wrapped__"):
                original_call = tool.call
                tool.call = capture_tool_call(name)(original_call)
                _original_functions[f"tool.{name}"] = original_call

        print(f"✅ Patched {len(tools_to_patch)} Hermes tools for auto-capture")
        return True

    except ImportError as e:
        print(f"⚠️  Could not patch Hermes tools: {e}")
        return False


def patch_hermes_commands():
    """Patch Hermes command registry to auto-capture."""
    try:
        from lib.claude_code.command import get_command_registry

        registry = get_command_registry()
        commands = registry.list_commands()

        for cmd in commands:
            if hasattr(cmd, "execute") and not hasattr(cmd.execute, "__wrapped__"):
                original_execute = cmd.execute
                cmd.execute = capture_command(cmd.name)(original_execute)
                _original_functions[f"command.{cmd.name}"] = original_execute

        print(f"✅ Patched {len(commands)} Hermes commands for auto-capture")
        return True

    except ImportError as e:
        print(f"⚠️  Could not patch Hermes commands: {e}")
        return False


def patch_file_operations():
    """Patch built-in file operations."""
    import builtins

    # Patch open() for read/write capture
    original_open = builtins.open

    @functools.wraps(original_open)
    def capturing_open(file, mode="r", *args, **kwargs):
        file_obj = original_open(file, mode, *args, **kwargs)

        if _capture_enabled and _current_session:
            file_path = str(file)
            if "r" in mode and "w" not in mode and "a" not in mode:
                # Read mode - capture on read
                original_read = file_obj.read

                @functools.wraps(original_read)
                def capturing_read(*args, **kwargs):
                    content = original_read(*args, **kwargs)
                    if isinstance(content, str) and content:
                        line_count = content.count("\n") + 1
                        store_file_op(
                            file_path=file_path,
                            operation="read",
                            content=content[:5000],
                            session_id=_current_session,
                            profile=_current_profile,
                            line_count=line_count,
                        )
                        update_session_stats(_current_session, file_delta=1)
                    return content

                file_obj.read = capturing_read

            elif "w" in mode or "a" in mode:
                # Write/append mode - capture on write
                original_write = file_obj.write

                @functools.wraps(original_write)
                def capturing_write(content, *args, **kwargs):
                    result = original_write(content, *args, **kwargs)
                    if isinstance(content, str) and content:
                        line_count = content.count("\n") + 1
                        store_file_op(
                            file_path=file_path,
                            operation="write" if "w" in mode else "append",
                            content=content[:5000],
                            session_id=_current_session,
                            profile=_current_profile,
                            line_count=line_count,
                        )
                        update_session_stats(_current_session, file_delta=1)
                    return result

                file_obj.write = capturing_write

        return file_obj

    builtins.open = capturing_open
    _original_functions["builtins.open"] = original_open
    print("✅ Patched builtins.open for file operation capture")
    return True


def unpatch_all():
    """Remove all patches."""
    global _original_functions

    # Restore builtins.open
    if "builtins.open" in _original_functions:
        import builtins
        builtins.open = _original_functions["builtins.open"]

    # Restore tool calls
    for key, original in _original_functions.items():
        if key.startswith("tool."):
            name = key[5:]
            try:
                from lib.claude_code.tools import TOOL_MAP
                if name in TOOL_MAP:
                    TOOL_MAP[name].call = original
            except Exception:
                pass
        elif key.startswith("command."):
            name = key[8:]
            try:
                from lib.claude_code.command import get_command_registry
                registry = get_command_registry()
                cmd = registry.get(name)
                if cmd:
                    cmd.execute = original
            except Exception:
                pass

    _original_functions.clear()
    print("✅ Removed all auto-capture patches")


# ─── Git Commit Capture ─────────────────────────────────────────────────────


def capture_git_commit(commit_hash: str, message: str, files_changed: list[str]):
    """Record a git commit."""
    if not _capture_enabled or not _current_session:
        return

    store_operation(
        op_type="git",
        input_data={"commit_hash": commit_hash, "message": message, "files": files_changed},
        output_data={"status": "committed"},
        result="success",
        session_id=_current_session,
        profile=_current_profile,
        working_dir=os.getcwd(),
        git_commit=commit_hash,
        tags=["git", "commit", "auto-capture"],
    )

    # Also store as pattern for searchability
    store_pattern(
        pattern_type="git_commit",
        title=f"Commit: {message[:80]}",
        content=f"Hash: {commit_hash}\nMessage: {message}\nFiles: {', '.join(files_changed)}",
        profile=_current_profile,
        session=_current_session,
        tags=["git", "commit", _current_profile],
    )


# ─── Test Result Capture ────────────────────────────────────────────────────


def capture_test_result(test_name: str, passed: bool, duration_ms: int, output: str | None = None):
    """Record a test result."""
    if not _capture_enabled or not _current_session:
        return

    store_operation(
        op_type="test",
        input_data={"test_name": test_name},
        output_data={"passed": passed, "duration_ms": duration_ms, "output": output[:2000] if output else None},
        result="success" if passed else "error",
        duration_ms=duration_ms,
        session_id=_current_session,
        profile=_current_profile,
        working_dir=os.getcwd(),
        tags=["test", "auto-capture", "passed" if passed else "failed"],
    )


# ─── Skill Load Capture ─────────────────────────────────────────────────────


def capture_skill_load(skill_name: str, success: bool, error: str | None = None):
    """Record a skill load."""
    if not _capture_enabled or not _current_session:
        return

    store_operation(
        op_type="skill_load",
        input_data={"skill_name": skill_name},
        output_data={"success": success, "error": error},
        result="success" if success else "error",
        error_message=error,
        session_id=_current_session,
        profile=_current_profile,
        working_dir=os.getcwd(),
        tags=["skill", "load", "auto-capture"],
    )


# ─── Initialize Auto-Capture ────────────────────────────────────────────────


def init_auto_capture(profile: str | None = None, session_name: str | None = None) -> str:
    """Initialize full auto-capture for Hermes."""
    session_id = start_capture_session(profile, session_name)

    # Patch everything
    patch_hermes_tools()
    patch_hermes_commands()
    patch_file_operations()

    print(f"🎯 Auto-capture initialized: session={session_id}, profile={profile or 'default'}")
    return session_id


# ─── Context Manager ────────────────────────────────────────────────────────


class AutoCapture:
    """Context manager for auto-capture session."""

    def __init__(self, profile: str | None = None, session_name: str | None = None):
        self.profile = profile
        self.session_name = session_name
        self.session_id: str | None = None

    def __enter__(self) -> str:
        self.session_id = init_auto_capture(self.profile, self.session_name)
        return self.session_id

    def __exit__(self, exc_type, exc_val, exc_tb):
        summary = f"Session ended{' with error' if exc_type else ''}"
        if exc_val:
            summary += f": {exc_val}"
        end_capture_session(summary)
        return False


# ─── CLI ────────────────────────────────────────────────────────────────────


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Hermes Auto-Capture")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_start = sub.add_parser("start", help="Start auto-capture")
    p_start.add_argument("--profile", default="default")
    p_start.add_argument("--session", help="Session name")

    p_stop = sub.add_parser("stop", help="Stop auto-capture")
    p_stop.add_argument("--summary", help="Session summary")

    p_test = sub.add_parser("test", help="Test auto-capture")
    p_test.add_argument("--profile", default="default")

    args = parser.parse_args()

    if args.cmd == "start":
        session_id = init_auto_capture(args.profile, args.session)
        print(f"Started: {session_id}")
        print("Auto-capture active. Press Ctrl+C to stop.")
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            end_capture_session("User stopped")
            print("Stopped")

    elif args.cmd == "stop":
        end_capture_session(args.summary)
        print("Stopped")

    elif args.cmd == "test":
        with AutoCapture(profile=args.profile, session_name="test") as session_id:
            print(f"Test session: {session_id}")

            # Test tool capture
            from lib.hermes_kb_universal import store_operation
            store_operation(
                op_type="tool",
                tool_name="test_tool",
                input_data={"test": "input"},
                output_data={"test": "output"},
                result="success",
                duration_ms=100,
                session_id=session_id,
                profile=args.profile,
            )

            # Test search
            from lib.hermes_kb_universal import search_patterns
            results = search_patterns(query="test_tool", pattern_type="tool_result")
            print(f"Captured operations: {len(results)}")


if __name__ == "__main__":
    main()