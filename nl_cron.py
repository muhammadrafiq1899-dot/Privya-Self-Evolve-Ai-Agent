"""
nl_cron.py – Natural language to cron expression converter.

Uses the LLM to translate human-readable schedule descriptions into
standard 5-field cron expressions, with validation.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from llm import chat

# ---------------------------------------------------------------------------
# Cron validation
# ---------------------------------------------------------------------------

CRON_FIELDS = re.compile(
    r"^"
    r"([\*\-\/\d\,]+)\s+"   # minute (0-59)
    r"([\*\-\/\d\,]+)\s+"   # hour (0-23)
    r"([\*\-\/\d\,]+)\s+"   # day of month (1-31)
    r"([\*\-\/\d\,]+)\s+"   # month (1-12)
    r"([\*\-\/\d\,]+)"      # day of week (0-7)
    r"$"
)

VALID_MONTHS = set(range(1, 13))
VALID_HOURS = set(range(0, 24))
VALID_MINUTES = set(range(0, 60))


def validate_cron(expr: str) -> tuple[bool, str]:
    """Validate a cron expression. Returns (is_valid, message)."""
    expr = expr.strip()
    if not CRON_FIELDS.match(expr):
        return False, f"Invalid cron format: '{expr}'. Expected 5 space-separated fields."

    parts = expr.split()
    if len(parts) != 5:
        return False, f"Cron must have 5 fields, got {len(parts)}."

    # Basic range validation for fixed values
    field_names = ["minute", "hour", "day", "month", "weekday"]
    maxima = [59, 23, 31, 12, 7]

    for i, (part, name, maximum) in enumerate(zip(parts, field_names, maxima)):
        if part == "*":
            continue
        if "/" in part or "-" in part or "," in part:
            continue  # complex expressions – trust LLM
        try:
            val = int(part)
            if val < 0 or val > maximum:
                return False, f"{name} value {val} out of range (0-{maximum})."
        except ValueError:
            return False, f"Invalid {name} value: '{part}'."

    return True, "Valid cron expression."


# ---------------------------------------------------------------------------
# Natural language → cron via LLM
# ---------------------------------------------------------------------------

CONVERSION_SYSTEM = """You are a cron expression generator. Convert natural language time descriptions into standard 5-field cron expressions (minute hour day-of-month month day-of-week).

Rules:
- Use standard cron notation (*/5 for every 5, etc.)
- If the user says "every day at 3pm", produce: 0 15 * * *
- If the user says "every Monday at 9am", produce: 0 9 * * 1
- If the user says "every 30 minutes", produce: */30 * * * *
- If the user says "hourly", produce: 0 * * * *
- Only output the 5-field cron expression, nothing else.
- Be precise and conservative. If ambiguous, prefer common interpretations.
"""


async def nl_to_cron(description: str) -> dict[str, str]:
    """Convert natural language schedule to cron expression.

    Returns:
        {"cron": str, "description": str, "validated": bool, "message": str}
    """
    messages = [
        {"role": "system", "content": CONVERSION_SYSTEM},
        {"role": "user", "content": description},
    ]

    try:
        response = await chat(messages, temperature=0.1, max_tokens=100)
        cron_expr = response["content"].strip().strip('"').strip("'")

        # Clean up any explanatory text the LLM might add
        lines = cron_expr.split("\n")
        cron_expr = lines[0].strip()

        valid, msg = validate_cron(cron_expr)
        return {
            "cron": cron_expr,
            "description": description,
            "validated": valid,
            "message": msg,
        }
    except Exception as e:
        return {
            "cron": "",
            "description": description,
            "validated": False,
            "message": f"Conversion error: {e}",
        }


# ---------------------------------------------------------------------------
# Local cron store (for simple scheduling without system crontab)
# ---------------------------------------------------------------------------

import json
from pathlib import Path

CRON_STORE = Path.home() / ".ai-agent" / "cron_jobs.json"


def _load_cron_jobs() -> list[dict]:
    if CRON_STORE.exists():
        try:
            return json.loads(CRON_STORE.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_cron_jobs(jobs: list[dict]) -> None:
    CRON_STORE.parent.mkdir(parents=True, exist_ok=True)
    CRON_STORE.write_text(json.dumps(jobs, indent=2, ensure_ascii=False), "utf-8")


def add_cron_job(name: str, cron_expr: str, command: str) -> dict:
    """Add a scheduled job to the local store."""
    valid, msg = validate_cron(cron_expr)
    if not valid:
        return {"error": msg}

    job = {
        "name": name,
        "cron": cron_expr,
        "command": command,
        "enabled": True,
        "created": datetime.now().isoformat(),
    }
    jobs = _load_cron_jobs()
    jobs.append(job)
    _save_cron_jobs(jobs)
    return {"result": f"Cron job '{name}' added: {cron_expr} → {command}"}


def remove_cron_job(name: str) -> dict:
    """Remove a scheduled job by name."""
    jobs = _load_cron_jobs()
    new_jobs = [j for j in jobs if j["name"] != name]
    if len(new_jobs) == len(jobs):
        return {"error": f"No job named '{name}' found."}
    _save_cron_jobs(new_jobs)
    return {"result": f"Cron job '{name}' removed."}


def list_cron_jobs() -> list[dict]:
    return _load_cron_jobs()
