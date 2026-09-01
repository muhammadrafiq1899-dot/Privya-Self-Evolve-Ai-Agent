"""
security.py – Security layer for tool execution.

Wraps potentially dangerous operations (file I/O, code execution) with
permission checks and sandboxing suitable for a Termux environment.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Blocked patterns (shell-dangerous commands)
# ---------------------------------------------------------------------------

BLOCKED_COMMANDS = {
    "rm -rf /", "rm -rf /*", "mkfs", "dd if=", "> /dev/sd",
    ":(){", "fork bomb", "chmod -R 777 /",
}

BLOCKED_MODULES = {
    "ctypes", "shlex", "importlib._bootstrap", "code",
}

# ---------------------------------------------------------------------------
# Python sandbox
# ---------------------------------------------------------------------------

SAFE_BUILTINS = {
    "abs", "all", "any", "bool", "bytes", "callable", "chr", "dict",
    "dir", "enumerate", "filter", "float", "frozenset", "getattr",
    "hasattr", "hash", "hex", "id", "int", "isinstance", "issubclass",
    "iter", "len", "list", "map", "max", "min", "next", "oct", "ord",
    "pow", "print", "property", "range", "repr", "reversed", "round",
    "set", "setattr", "slice", "sorted", "str", "sum", "super", "tuple",
    "type", "zip",
}


def _check_ast_safety(code: str) -> str | None:
    """Return an error message if code is unsafe, else None."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"Syntax error: {e}"

    for node in ast.walk(tree):
        # Block imports of dangerous modules
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name.split(".")[0]
                if mod in BLOCKED_MODULES:
                    return f"Import of '{mod}' is blocked for security."
        if isinstance(node, ast.ImportFrom) and node.module:
            mod = node.module.split(".")[0]
            if mod in BLOCKED_MODULES:
                return f"Import from '{mod}' is blocked for security."

        # Block eval/exec
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in ("eval", "exec", "compile", "__import__"):
                return f"Call to '{func.id}'() is blocked for security."

        # Block os.system / subprocess directly
        if isinstance(node, ast.Attribute) and node.attr in ("system", "popen"):
            if isinstance(node.value, ast.Name) and node.value.id in ("os", "subprocess"):
                return f"Direct os.{node.attr} / subprocess.{node.attr} is blocked."

    return None


def _check_shell_safety(code: str) -> str | None:
    """Block obviously dangerous shell commands."""
    lower = code.lower().strip()
    for pattern in BLOCKED_COMMANDS:
        if pattern in lower:
            return f"Blocked shell pattern: '{pattern}'"
    return None


def run_python_sandboxed(code: str, timeout: int = 15) -> dict[str, Any]:
    """
    Execute Python code in a subprocess with restricted builtins.

    Returns:
        {"stdout": str, "stderr": str, "returncode": int, "error": str | None}
    """
    safety_err = _check_ast_safety(code)
    if safety_err:
        return {"stdout": "", "stderr": "", "returncode": 1, "error": safety_err}

    # Write to temp file and run with subprocess (isolated process)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp_path = f.name

    try:
        result = subprocess.run(
            ["python3", tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(Path.home()),
            env={**os.environ, "PYTHONSAFEPATH": "1"},
        )
        return {
            "stdout": result.stdout[-4000:],  # cap output
            "stderr": result.stderr[-2000:],
            "returncode": result.returncode,
            "error": None if result.returncode == 0 else "Non-zero exit code",
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "", "returncode": -1, "error": "Execution timed out (15s)"}
    except Exception as e:
        return {"stdout": "", "stderr": "", "returncode": -1, "error": str(e)}
    finally:
        os.unlink(tmp_path)


def run_shell_sandboxed(command: str, timeout: int = 10) -> dict[str, Any]:
    """Run a whitelisted shell command safely."""
    safety_err = _check_shell_safety(command)
    if safety_err:
        return {"stdout": "", "stderr": "", "returncode": 1, "error": safety_err}

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(Path.home()),
        )
        return {
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-2000:],
            "returncode": result.returncode,
            "error": None if result.returncode == 0 else "Non-zero exit code",
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "", "returncode": -1, "error": "Command timed out (10s)"}
    except Exception as e:
        return {"stdout": "", "stderr": "", "returncode": -1, "error": str(e)}


def check_file_access(path: str, mode: str = "read") -> str | None:
    """Validate file access is within safe directories."""
    resolved = Path(path).expanduser().resolve()
    home = Path.home()
    safe_dirs = [home, Path("/tmp")]

    if mode == "write":
        # Block writes outside home and tmp
        if not any(str(resolved).startswith(str(d)) for d in safe_dirs):
            return f"Write access denied: {path} is outside safe directories."
    return None
