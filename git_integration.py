"""
git_integration.py – Git integration for agent self-versioning.

Allows the agent to:
1. Auto-commit its own code changes and learned skills
2. Push to a private GitHub repo for backup
3. Rollback to previous versions
4. Track evolution history
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(os.getenv("AGENT_DATA_DIR", Path.home() / ".ai-agent"))
EVOLUTION_LOG = DATA_DIR / "evolution.jsonl"

# ---------------------------------------------------------------------------
# Git operations
# ---------------------------------------------------------------------------

async def _git(args: str, cwd: str | None = None, timeout: int = 30) -> dict[str, Any]:
    """Run a git command and return output."""
    cmd = f"git {args}"
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        stdout_str = stdout.decode("utf-8", errors="replace").strip()
        stderr_str = stderr.decode("utf-8", errors="replace").strip()

        return {
            "stdout": stdout_str,
            "stderr": stderr_str,
            "returncode": proc.returncode,
            "success": proc.returncode == 0,
        }
    except asyncio.TimeoutError:
        return {"stdout": "", "stderr": "Git command timed out", "returncode": -1, "success": False}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "returncode": -1, "success": False}


# ---------------------------------------------------------------------------
# Core git tools
# ---------------------------------------------------------------------------

async def git_status() -> dict[str, Any]:
    """Get git status of the repository."""
    return await _git("status --short")


async def git_diff() -> dict[str, Any]:
    """Get uncommitted changes."""
    result = await _git("diff")
    return result


async def git_diff_staged() -> dict[str, Any]:
    """Get staged changes."""
    return await _git("diff --staged")


async def git_log(n: int = 10) -> dict[str, Any]:
    """Get recent git log."""
    return await _git(f"log --oneline -{n}")


async def git_commit(message: str, files: list[str] | None = None) -> dict[str, Any]:
    """Stage and commit changes.

    Args:
        message: Commit message
        files: Specific files to stage (None = all changed)
    """
    # Stage files
    if files:
        for f in files:
            result = await _git(f"add {f}")
            if not result["success"]:
                return result
    else:
        result = await _git("add -A")
        if not result["success"]:
            return result

    # Commit
    # Escape message for shell
    escaped_msg = message.replace("'", "'\\''")
    return await _git(f"commit -m '{escaped_msg}'")


async def git_push(remote: str = "origin", branch: str | None = None) -> dict[str, Any]:
    """Push changes to remote."""
    if branch:
        return await _git(f"push {remote} {branch}")
    return await _git(f"push {remote}")


async def git_pull(remote: str = "origin", branch: str | None = None) -> dict[str, Any]:
    """Pull changes from remote."""
    if branch:
        return await _git(f"pull {remote} {branch}")
    return await _git(f"pull {remote}")


async def git_checkout(branch: str) -> dict[str, Any]:
    """Switch to a branch."""
    return await _git(f"checkout {branch}")


async def git_create_branch(name: str) -> dict[str, Any]:
    """Create and switch to a new branch."""
    return await _git(f"checkout -b {name}")


async def git_rollback(commit: str) -> dict[str, Any]:
    """Rollback to a specific commit."""
    return await _git(f"reset --hard {commit}")


async def git_clone(url: str, destination: str | None = None) -> dict[str, Any]:
    """Clone a repository."""
    cmd = f"clone {url}"
    if destination:
        cmd += f" {destination}"
    return await _git(cmd, timeout=60)


# ---------------------------------------------------------------------------
# Agent-specific git operations
# ---------------------------------------------------------------------------

async def git_auto_commit(
    description: str,
    files: list[str] | None = None,
    auto_push: bool = False,
) -> dict[str, Any]:
    """Auto-commit agent changes with descriptive message.

    Automatically formats the commit message for agent evolution tracking.
    """
    timestamp = time.strftime("%Y-%m-%d %H:%M")
    message = f"[agent-evolution] {description}\n\n🤖 Auto-committed by AI Agent\nTimestamp: {timestamp}"

    result = await git_commit(message, files)

    if result["success"] and auto_push:
        push_result = await git_push()
        result["push"] = push_result

    # Log evolution
    _log_evolution(description, files)

    return result


async def git_save_state(label: str) -> dict[str, Any]:
    """Save current agent state (memory + procedures + code) as a commit."""
    # Stage known agent files
    agent_files = [
        "agent.py", "llm.py", "memory.py", "tools.py", "security.py",
        "nl_cron.py", "consolidator.py", "telegram_bot.py",
        "requirements.txt", "README.md",
    ]

    # Also stage data files if they exist
    data_dir = Path(os.getenv("AGENT_DATA_DIR", Path.home() / ".ai-agent"))
    for f in ["long_term.jsonl", "procedural.jsonl", "procedures_index.json", "cron_jobs.json"]:
        data_path = data_dir / f
        if data_path.exists():
            agent_files.append(str(data_path))

    # Filter to existing files
    existing = [f for f in agent_files if Path(f).exists()]

    if not existing:
        return {"result": "No agent files to save."}

    result = await git_auto_commit(
        f"State snapshot: {label}",
        files=existing,
    )

    if result["success"]:
        return {"result": f"Agent state saved: {label}", "commit": result.get("stdout", "")}
    return {"error": result.get("stderr", "Commit failed")}


async def git_rollback_agent(target: str) -> dict[str, Any]:
    """Rollback agent to a previous state.

    Args:
        target: Commit hash, branch name, or "last" for previous commit
    """
    if target == "last":
        target = "HEAD~1"

    result = await git_rollback(target)
    if result["success"]:
        return {"result": f"Agent rolled back to {target}"}
    return {"error": result.get("stderr", "Rollback failed")}


async def git_list_snapshots(n: int = 20) -> dict[str, Any]:
    """List recent agent evolution snapshots."""
    result = await git_log(n)
    if result["success"]:
        lines = result["stdout"].split("\n")
        snapshots = [l for l in lines if "[agent-evolution]" in l.lower() or "agent" in l.lower()]
        if snapshots:
            return {"result": "\n".join(snapshots[:n])}
        return {"result": "No agent evolution snapshots found."}
    return {"error": result.get("stderr", "Failed to list snapshots")}


async def git_diff_evolution(from_commit: str, to_commit: str = "HEAD") -> dict[str, Any]:
    """Show changes between two agent versions."""
    result = await _git(f"diff {from_commit}..{to_commit}")
    if result["success"]:
        diff = result["stdout"]
        if len(diff) > 6000:
            diff = diff[:6000] + "\n... (truncated)"
        return {"result": diff}
    return {"error": result.get("stderr", "Diff failed")}


async def git_init_repo(path: str | None = None) -> dict[str, Any]:
    """Initialize a git repo for the agent (if not already initialized)."""
    if path:
        result = await _git(f"init {path}")
    else:
        result = await _git("init")

    if result["success"]:
        # Create .gitignore
        gitignore = Path(path or ".") / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(
                "# Agent data (optional – include if you want to track)\n"
                "# .ai-agent/\n\n"
                "# Python\n"
                "__pycache__/\n"
                "*.pyc\n"
                ".env\n"
                "*.egg-info/\n"
                "venv/\n"
                ".venv/\n",
                "utf-8",
            )
    return result


async def git_setup_remote(repo_url: str) -> dict[str, Any]:
    """Add or update the remote origin."""
    # Check if remote already exists
    check = await _git("remote get-url origin")
    if check["success"]:
        # Update existing remote
        return await _git(f"remote set-url origin {repo_url}")
    else:
        # Add new remote
        return await _git(f"remote add origin {repo_url}")


# ---------------------------------------------------------------------------
# Evolution logging
# ---------------------------------------------------------------------------

def _log_evolution(description: str, files: list[str] | None = None) -> None:
    """Log an evolution event."""
    entry = {
        "timestamp": time.time(),
        "description": description,
        "files": files or [],
    }
    try:
        EVOLUTION_LOG.parent.mkdir(parents=True, exist_ok=True)
        with EVOLUTION_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

GIT_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "git_commit",
            "description": "Stage and commit changes to the agent's git repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Commit message describing the change"},
                    "files": {"type": "array", "items": {"type": "string"}, "description": "Specific files to commit (default: all changes)"},
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_push",
            "description": "Push committed changes to the remote repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "remote": {"type": "string", "description": "Remote name (default: origin)"},
                    "branch": {"type": "string", "description": "Branch name (default: current branch)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_save_state",
            "description": "Save the current agent state (code, memory, procedures) as a git snapshot.",
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "Label for this state snapshot"},
                },
                "required": ["label"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_rollback_agent",
            "description": "Rollback the agent to a previous version.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Commit hash, branch, or 'last' for previous commit"},
                },
                "required": ["target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_list_snapshots",
            "description": "List recent agent evolution snapshots (commits).",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of snapshots to show (default 20)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Check the git status of the agent repository.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff_evolution",
            "description": "Show changes between two agent versions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_commit": {"type": "string", "description": "Starting commit hash"},
                    "to_commit": {"type": "string", "description": "Ending commit (default: HEAD)"},
                },
                "required": ["from_commit"],
            },
        },
    },
]


GIT_TOOL_MAP = {
    "git_commit": git_commit,
    "git_push": git_push,
    "git_save_state": git_save_state,
    "git_rollback_agent": git_rollback_agent,
    "git_list_snapshots": git_list_snapshots,
    "git_status": git_status,
    "git_diff_evolution": git_diff_evolution,
}
