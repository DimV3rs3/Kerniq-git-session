"""Commit the workspace at the end of a run and roll it back to that point.

The session mark is stored outside the workspace. File tools cannot read it.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def active_workspace() -> Path:
    """The workspace from Kerniq settings, resolved. Not the process cwd by accident."""
    from Kerniq.settings.loader import SettingsProvider
    from Kerniq.settings.ui_store import UiSettingsStore

    cfg = SettingsProvider().config
    raw = Path(UiSettingsStore(cfg.storage.state_dir).load().agent.workspace or "./workspace")
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    try:
        return raw.resolve()
    except OSError:
        return raw


def _git(workspace: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(workspace), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def git_available() -> bool:
    from shutil import which

    return which("git") is not None


def sessions_path() -> Path:
    return Path.home() / ".kerniq" / "git_sessions.json"


def _load_sessions() -> dict:
    try:
        data = json.loads(sessions_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_sessions(data: dict) -> None:
    path = sessions_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)


def _key(workspace: Path) -> str:
    try:
        return str(workspace.resolve())
    except OSError:
        return str(workspace)


def ensure_repo(workspace: Path) -> None:
    folder = Path(workspace)
    folder.mkdir(parents=True, exist_ok=True)
    if not (folder / ".git").exists():
        proc = _git(folder, "init")
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "git init failed")
    head_now = _git(folder, "rev-parse", "HEAD")
    if head_now.returncode != 0:
        _git(folder, "add", "-A", "--", ".", ":(exclude).kerniq-venv", ":(exclude).kerniq-view", ":(exclude).kerniq-runtimes")
        made = _git(
            folder,
            "-c", "user.name=Kerniq",
            "-c", "user.email=kerniq@localhost",
            "commit",
            "--allow-empty",
            "-m", "kerniq: baseline",
        )
        if made.returncode != 0:
            raise RuntimeError(made.stderr.strip() or "git baseline failed")


def head(workspace: Path) -> str:
    proc = _git(Path(workspace), "rev-parse", "HEAD")
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def note_session_start(workspace: Path, chat_id: str) -> str:
    """Remember HEAD before this run changes files. No commit yet."""
    if not git_available():
        return ""
    folder = Path(workspace)
    ensure_repo(folder)
    sha = head(folder)
    data = _load_sessions()
    data[_key(folder)] = {"chat_id": str(chat_id or ""), "start": sha}
    _save_sessions(data)
    return sha


def session_start(workspace: Path) -> str:
    row = _load_sessions().get(_key(Path(workspace))) or {}
    return str(row.get("start") or "")


def commit_session(workspace: Path, chat_id: str) -> dict:
    """Commit whatever this run changed. No-op when the tree is clean."""
    if not git_available():
        return {"committed": False, "reason": "git is not installed"}
    folder = Path(workspace)
    ensure_repo(folder)
    if not session_start(folder):
        note_session_start(folder, chat_id)
    added = _git(folder, "add", "-A", "--", ".", ":(exclude).kerniq-venv", ":(exclude).kerniq-view", ":(exclude).kerniq-runtimes")
    if added.returncode != 0:
        return {"committed": False, "reason": added.stderr.strip() or "git add failed"}
    clean = _git(folder, "diff", "--cached", "--quiet")
    if clean.returncode == 0:
        return {"committed": False, "reason": "clean", "rev": head(folder)}
    label = str(chat_id or "run").replace("\n", " ")[:80]
    made = _git(
        folder,
        "-c", "user.name=Kerniq",
        "-c", "user.email=kerniq@localhost",
        "commit",
        "-m", f"kerniq: session {label}",
    )
    if made.returncode != 0:
        return {"committed": False, "reason": made.stderr.strip() or "git commit failed"}
    return {"committed": True, "rev": head(folder), "start": session_start(folder)}


def _safe_rel(workspace: Path, raw: str) -> str:
    text = str(raw or "").replace("\\", "/").strip()
    if not text or text.startswith("/") or (len(text) > 2 and text[1] == ":"):
        raise PermissionError("Path is outside the workspace.")
    target = (Path(workspace) / text).resolve()
    root = Path(workspace).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise PermissionError("Path is outside the workspace.") from exc
    return target.relative_to(root).as_posix()


def diff_workspace(workspace: Path, path: str = "") -> dict:
    folder = Path(workspace)
    if not git_available():
        return {"ok": False, "error": "git is not installed"}
    args = ["diff", "--", path] if path else ["diff"]
    proc = _git(folder, *args)
    text = proc.stdout.strip() or "(no changes)"
    return {"ok": proc.returncode == 0, "text": text, "error": proc.stderr.strip()}


def log_workspace(workspace: Path, limit: int = 10) -> dict:
    folder = Path(workspace)
    if not git_available():
        return {"ok": False, "error": "git is not installed"}
    try:
        count = int(limit)
    except (TypeError, ValueError):
        count = 10
    count = min(30, max(1, count))
    proc = _git(folder, "log", f"-n{count}", "--oneline")
    text = proc.stdout.strip() or "(no commits)"
    return {"ok": proc.returncode == 0, "text": text, "error": proc.stderr.strip()}


def commit_message(workspace: Path, message: str) -> dict:
    """Stage workspace changes and commit them with the model's message."""
    if not git_available():
        return {"committed": False, "reason": "git is not installed"}
    folder = Path(workspace)
    ensure_repo(folder)
    text = " ".join(str(message or "").split())[:200]
    if not text:
        return {"committed": False, "reason": "a commit message is required"}
    added = _git(folder, "add", "-A", "--", ".", ":(exclude).kerniq-venv", ":(exclude).kerniq-view", ":(exclude).kerniq-runtimes")
    if added.returncode != 0:
        return {"committed": False, "reason": added.stderr.strip() or "git add failed"}
    clean = _git(folder, "diff", "--cached", "--quiet")
    if clean.returncode == 0:
        return {"committed": False, "reason": "clean", "rev": head(folder)}
    made = _git(
        folder,
        "-c", "user.name=Kerniq",
        "-c", "user.email=kerniq@localhost",
        "commit",
        "-m", text,
    )
    if made.returncode != 0:
        return {"committed": False, "reason": made.stderr.strip() or "git commit failed"}
    return {"committed": True, "rev": head(folder)}


def rollback_file(workspace: Path, raw: str) -> dict:
    """Restore one file to the revision from the start of this session."""
    folder = Path(workspace)
    rel = _safe_rel(folder, raw)
    start = session_start(folder) or "HEAD"
    proc = _git(folder, "checkout", start, "--", rel)
    if proc.returncode != 0:
        return {"ok": False, "error": proc.stderr.strip() or "file was not in that revision"}
    return {"ok": True, "path": rel, "rev": start}


def rollback_session(workspace: Path) -> dict:
    """Drop every Kerniq change after the session start.

    Refuses when later commits are not Kerniq's. Those belong to someone else.
    """
    folder = Path(workspace)
    start = session_start(folder)
    if not start:
        return {"ok": False, "error": "This workspace has no Kerniq session to roll back."}
    log = _git(folder, "log", "--format=%s", f"{start}..HEAD")
    if log.returncode != 0:
        return {"ok": False, "error": log.stderr.strip() or "git log failed"}
    subjects = [line for line in log.stdout.splitlines() if line.strip()]
    foreign = [line for line in subjects if not line.startswith("kerniq:")]
    if foreign:
        return {"ok": False, "error": "Later commits are not Kerniq's. Refusing to erase them."}
    proc = _git(folder, "reset", "--hard", start)
    if proc.returncode != 0:
        return {"ok": False, "error": proc.stderr.strip() or "git reset failed"}
    return {"ok": True, "rev": start}
