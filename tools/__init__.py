"""Tools the model can call. They only touch the workspace git checkout."""

from __future__ import annotations

from typing import Any, Dict

from Kerniq.interfaces.tools import Tool, ToolResult


def _engine():
    import importlib.util
    import sys
    from pathlib import Path

    name = "kerniq_git_session_engine"
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    path = Path(__file__).resolve().parents[1] / "engine.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class GitStatus(Tool):
    @property
    def tool_id(self) -> str:
        return "git_status"

    @property
    def name(self) -> str:
        return "git_status"

    @property
    def description(self) -> str:
        return "Show workspace files changed since this Kerniq session started."

    @property
    def category(self) -> str:
        return "git"

    @property
    def risk_level(self) -> str:
        return "low"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, arguments: Dict[str, Any], context: Any) -> ToolResult:
        import subprocess

        folder = _engine().active_workspace()
        proc = subprocess.run(
            ["git", "-C", str(folder), "status", "--short"],
            capture_output=True, text=True, timeout=30,
        )
        text = proc.stdout.strip() or "(clean)"
        body = f"session {_engine().session_start(folder) or '(none)'}\nHEAD {_engine().head(folder)}\n{text}"
        return ToolResult(
            tool_call_id=str(arguments.get("tool_call_id") or ""),
            tool_id=self.tool_id,
            status="success" if proc.returncode == 0 else "error",
            success=proc.returncode == 0,
            output=body,
            human_readable=body,
            error=None if proc.returncode == 0 else proc.stderr.strip(),
        )


class GitDiff(Tool):
    @property
    def tool_id(self) -> str:
        return "git_diff"

    @property
    def name(self) -> str:
        return "git_diff"

    @property
    def description(self) -> str:
        return "Show uncommitted changes in the workspace. Pass path to limit it to one file."

    @property
    def category(self) -> str:
        return "git"

    @property
    def risk_level(self) -> str:
        return "low"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {"path": {"type": "string"}}}

    async def execute(self, arguments: Dict[str, Any], context: Any) -> ToolResult:
        result = _engine().diff_workspace(_engine().active_workspace(), str(arguments.get("path") or ""))
        ok = bool(result.get("ok"))
        text = str(result.get("text") or result.get("error") or "")
        return ToolResult(
            tool_call_id=str(arguments.get("tool_call_id") or ""),
            tool_id=self.tool_id,
            status="success" if ok else "error",
            success=ok,
            output=text,
            human_readable=text[:4000],
            error=None if ok else text,
        )


class GitLog(Tool):
    @property
    def tool_id(self) -> str:
        return "git_log"

    @property
    def name(self) -> str:
        return "git_log"

    @property
    def description(self) -> str:
        return "Show recent commits in the workspace. limit is how many lines, at most 30."

    @property
    def category(self) -> str:
        return "git"

    @property
    def risk_level(self) -> str:
        return "low"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {"limit": {"type": "integer"}}}

    async def execute(self, arguments: Dict[str, Any], context: Any) -> ToolResult:
        result = _engine().log_workspace(_engine().active_workspace(), arguments.get("limit") or 10)
        ok = bool(result.get("ok"))
        text = str(result.get("text") or result.get("error") or "")
        return ToolResult(
            tool_call_id=str(arguments.get("tool_call_id") or ""),
            tool_id=self.tool_id,
            status="success" if ok else "error",
            success=ok,
            output=text,
            human_readable=text[:4000],
            error=None if ok else text,
        )


class GitCommit(Tool):
    @property
    def tool_id(self) -> str:
        return "git_commit"

    @property
    def name(self) -> str:
        return "git_commit"

    @property
    def description(self) -> str:
        return "Stage workspace changes and commit them. message is the commit message. Does not push."

    @property
    def category(self) -> str:
        return "git"

    @property
    def risk_level(self) -> str:
        return "high"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        }

    async def execute(self, arguments: Dict[str, Any], context: Any) -> ToolResult:
        result = _engine().commit_message(_engine().active_workspace(), str(arguments.get("message") or ""))
        ok = bool(result.get("committed"))
        text = f"Committed {result.get('rev')}" if ok else str(result.get("reason") or "commit failed")
        return ToolResult(
            tool_call_id=str(arguments.get("tool_call_id") or ""),
            tool_id=self.tool_id,
            status="success" if ok else "error",
            success=ok,
            output=text,
            human_readable=text,
            error=None if ok else text,
        )


class GitRollbackFile(Tool):
    @property
    def tool_id(self) -> str:
        return "git_rollback_file"

    @property
    def name(self) -> str:
        return "git_rollback_file"

    @property
    def description(self) -> str:
        return "Restore one workspace file to its content from the start of this Kerniq session."

    @property
    def category(self) -> str:
        return "git"

    @property
    def risk_level(self) -> str:
        return "high"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        }

    async def execute(self, arguments: Dict[str, Any], context: Any) -> ToolResult:
        result = _engine().rollback_file(_engine().active_workspace(), str(arguments.get("path") or ""))
        ok = bool(result.get("ok"))
        text = f"Restored {result.get('path')} from {result.get('rev')}" if ok else str(result.get("error") or "rollback failed")
        return ToolResult(
            tool_call_id=str(arguments.get("tool_call_id") or ""),
            tool_id=self.tool_id,
            status="success" if ok else "error",
            success=ok,
            output=text,
            human_readable=text,
            error=None if ok else text,
        )


class GitRollbackSession(Tool):
    @property
    def tool_id(self) -> str:
        return "git_rollback_session"

    @property
    def name(self) -> str:
        return "git_rollback_session"

    @property
    def description(self) -> str:
        return "Undo every Kerniq commit made in this workspace since the session started. Other people's commits are left alone."

    @property
    def category(self) -> str:
        return "git"

    @property
    def risk_level(self) -> str:
        return "high"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, arguments: Dict[str, Any], context: Any) -> ToolResult:
        result = _engine().rollback_session(_engine().active_workspace())
        ok = bool(result.get("ok"))
        text = f"Workspace restored to {result.get('rev')}" if ok else str(result.get("error") or "rollback failed")
        return ToolResult(
            tool_call_id=str(arguments.get("tool_call_id") or ""),
            tool_id=self.tool_id,
            status="success" if ok else "error",
            success=ok,
            output=text,
            human_readable=text,
            error=None if ok else text,
        )


def create_tools(plugin):
    return [GitStatus(), GitDiff(), GitLog(), GitCommit(), GitRollbackFile(), GitRollbackSession()]
