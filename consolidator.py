#!/usr/bin/env python3
"""
consolidator.py – Memory consolidation and procedure learning.

Run manually or via cron to:
1. Analyze recent conversations for patterns
2. Generate learned procedures from successful tool trajectories
3. Clean up and merge similar memories
4. Update the procedures index

Usage:
    python consolidator.py              # Run full consolidation
    python consolidator.py --scan       # Scan recent sessions only
    python consolidator.py --procedures # Learn procedures from trajectories
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from llm import chat
from memory import (
    long_term,
    procedural,
    MemoryEntry,
    Procedure,
    LONG_TERM_PATH,
    DATA_DIR,
)

# ---------------------------------------------------------------------------
# Session analysis
# ---------------------------------------------------------------------------

SESSION_DIR = DATA_DIR / "sessions"


def _load_recent_sessions(n: int = 5) -> list[list[dict[str, Any]]]:
    """Load the N most recent session files."""
    if not SESSION_DIR.exists():
        return []
    files = sorted(SESSION_DIR.glob("*.jsonl"), reverse=True)[:n]
    sessions = []
    for f in files:
        messages = []
        for line in f.read_text("utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    messages.append(json.loads(line))
                except (json.JSONDecodeError, TypeError):
                    continue
        if messages:
            sessions.append(messages)
    return sessions


# ---------------------------------------------------------------------------
# Consolidation tasks
# ---------------------------------------------------------------------------

async def consolidate_memories() -> dict[str, Any]:
    """Analyze long-term memories and consolidate similar ones."""
    all_memories = long_term.recent(100)
    if len(all_memories) < 5:
        return {"status": "skipped", "reason": "Not enough memories to consolidate (need 5+)"}

    # Prepare summary for LLM
    memory_text = "\n".join(
        f"- [{m.source}] {m.text[:200]}" for m in all_memories
    )

    prompt = f"""You are a memory consolidation system. Analyze these memories and:
1. Identify which memories are redundant or very similar
2. Create consolidated summaries for groups of related memories
3. Assign importance scores (0.0-1.0) based on frequency and relevance

Memories to analyze:
{memory_text}

Return a JSON array of consolidated memories with fields:
- "text": The consolidated memory text
- "importance": Score 0.0-1.0
- "tags": List of relevant tags
- "replaces": List of original memory texts that this replaces (first 50 chars each)
"""

    messages = [
        {"role": "system", "content": "You are a precise data analysis system. Return only valid JSON."},
        {"role": "user", "content": prompt},
    ]

    try:
        response = await chat(messages, temperature=0.2, max_tokens=2000)
        content = response["content"].strip()

        # Parse JSON response
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        consolidated = json.loads(content)

        added = 0
        for item in consolidated:
            if isinstance(item, dict) and "text" in item:
                long_term.add(MemoryEntry(
                    text=item["text"],
                    tags=item.get("tags", []),
                    importance=item.get("importance", 0.5),
                    source="consolidation",
                ))
                added += 1

        return {"status": "completed", "consolidated": added}
    except (json.JSONDecodeError, KeyError) as e:
        return {"status": "error", "error": f"Failed to parse consolidation: {e}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def learn_procedures() -> dict[str, Any]:
    """Analyze tool trajectories to discover repeatable procedures."""
    sessions = _load_recent_sessions(10)
    if not sessions:
        return {"status": "skipped", "reason": "No sessions found"}

    # Extract tool-call trajectories
    trajectories = []
    for session in sessions:
        tools_used = []
        for msg in session:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    tools_used.append({
                        "tool": tc["function"]["name"],
                        "args": tc["function"].get("arguments", "")[:100],
                    })
            if msg.get("role") == "tool" and msg.get("content"):
                try:
                    result = json.loads(msg["content"])
                    tools_used[-1]["success"] = result.get("error") is None if tools_used else False
                except (json.JSONDecodeError, KeyError):
                    pass
        if len(tools_used) >= 2:
            trajectories.append(tools_used)

    if not trajectories:
        return {"status": "skipped", "reason": "No tool trajectories found"}

    # Format for LLM analysis
    traj_text = "\n".join(
        f"Trajectory {i+1}: " + " → ".join(
            f"{t['tool']}({'success' if t.get('success') else 'fail'})"
            for t in traj
        )
        for i, traj in enumerate(trajectories[:10])
    )

    prompt = f"""You are a procedure-learning system. Analyze these tool-call trajectories 
and identify repeatable multi-step procedures.

Trajectories:
{traj_text}

For each discovered procedure, return a JSON array with objects containing:
- "name": Short procedure name (lowercase, underscored)
- "description": What the procedure does
- "steps": Array of step descriptions
- "tool_pattern": The tool sequence (e.g. "web_search → web_fetch → save_memory")

Focus on patterns that appear multiple times or represent useful workflows.
Only return valid JSON."""

    messages = [
        {"role": "system", "content": "You are a precise pattern recognition system. Return only valid JSON."},
        {"role": "user", "content": prompt},
    ]

    try:
        response = await chat(messages, temperature=0.2, max_tokens=1500)
        content = response["content"].strip()

        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        discovered = json.loads(content)
        added = 0

        for item in discovered:
            if isinstance(item, dict) and "name" in item:
                # Check if procedure already exists
                existing = procedural.get(item["name"])
                if existing:
                    existing.success_count += 1
                    continue

                procedural.add(Procedure(
                    name=item["name"],
                    description=item.get("description", ""),
                    steps=item.get("steps", []),
                    tool_pattern=item.get("tool_pattern", ""),
                ))
                added += 1

        return {"status": "completed", "procedures_learned": added}
    except (json.JSONDecodeError, KeyError) as e:
        return {"status": "error", "error": f"Failed to parse procedures: {e}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run_consolidation(scan_only: bool = False, procedures_only: bool = False) -> None:
    """Run the full consolidation pipeline."""
    print(f"🔄 Memory Consolidation — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if not scan_only and not procedures_only:
        # Full consolidation
        print("\n📊 Consolidating memories...")
        result = await consolidate_memories()
        print(f"   Status: {result['status']}")
        if result.get("consolidated"):
            print(f"   Consolidated: {result['consolidated']} new entries")

        print("\n🧠 Learning procedures from trajectories...")
        result = await learn_procedures()
        print(f"   Status: {result['status']}")
        if result.get("procedures_learned"):
            print(f"   Learned: {result['procedures_learned']} new procedures")

    elif scan_only:
        print("\n📊 Scanning memories...")
        result = await consolidate_memories()
        print(f"   Status: {result}")

    elif procedures_only:
        print("\n🧠 Learning procedures...")
        result = await learn_procedures()
        print(f"   Status: {result}")

    print("\n" + "=" * 60)

    # Print summary
    mem_count = len(long_term.recent(1000))
    proc_count = len(procedural.all_procedures())
    print(f"📈 Current state: {mem_count} memories, {proc_count} procedures")
    print("✅ Consolidation complete.")


def main() -> None:
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print(__doc__)
        sys.exit(0)

    scan_only = "--scan" in args
    procedures_only = "--procedures" in args

    asyncio.run(run_consolidation(scan_only=scan_only, procedures_only=procedures_only))


if __name__ == "__main__":
    main()
