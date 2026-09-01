"""
reflection.py – Reflection & self-correction loop.

Instead of returning the first answer, the agent:
1. Generates an initial response
2. Critiques its own work (hidden from user)
3. Corrects errors and improves quality
4. Returns the refined response

This dramatically reduces hallucinations in code generation and complex reasoning.
"""

from __future__ import annotations

from typing import Any, Optional

from llm import chat


# ---------------------------------------------------------------------------
# Reflection system prompts
# ---------------------------------------------------------------------------

CRITIC_SYSTEM = """You are a meticulous critic and fact-checker. Your job is to review 
an AI-generated response and identify:

1. **Factual errors**: Wrong claims, incorrect numbers, wrong dates
2. **Logical flaws**: Invalid reasoning, contradictions, missing steps
3. **Code issues**: Syntax errors, logic bugs, security vulnerabilities, wrong APIs
4. **Missing information**: Important details that were omitted
5. **Hallucinations**: Made-up facts, fake references, invented APIs/libraries

Be specific. Quote the problematic text and explain what's wrong.
If the response is good, say "APPROVED" and note minor improvements if any.

Respond in this format:
VERDICT: [APPROVED | NEEDS_FIX | MAJOR_ISSUES]
ISSUES:
- [issue 1]
- [issue 2]
...
SUGGESTIONS:
- [improvement 1]
...
"""

REVISION_SYSTEM = """You are a revision expert. Given an original AI response and a critic's 
feedback, produce an improved version that:

1. Fixes all identified issues
2. Incorporates the suggestions
3. Maintains the original intent and structure
4. Is clear, accurate, and complete

Output ONLY the revised response. No meta-commentary."""

CODE_REVIEW_SYSTEM = """You are a senior code reviewer. Review the generated code for:
1. Syntax errors
2. Logic bugs
3. Security vulnerabilities (injection, XSS, etc.)
4. Performance issues
5. API misuse or wrong library calls
6. Missing error handling
7. Style and best practices

Be specific about line numbers and exact fixes needed.
If code is correct, say "CODE_APPROVED" and note minor improvements."""


# ---------------------------------------------------------------------------
# Reflection pipeline
# ---------------------------------------------------------------------------

async def reflect_and_improve(
    response: str,
    context: str = "",
    task_type: str = "general",
    max_rounds: int = 2,
) -> dict[str, Any]:
    """Run reflection loop on a response.

    Args:
        response: Initial AI response to critique
        context: Original user query for context
        task_type: "general", "code", "math", "research"
        max_rounds: Max critique-revise cycles (1-3)

    Returns:
        {
            "final_response": str,
            "was_improved": bool,
            "critiques": list[str],
            "rounds": int,
        }
    """
    current = response
    critiques = []

    # Choose critic prompt based on task type
    if task_type == "code":
        critic_prompt = CODE_REVIEW_SYSTEM
    else:
        critic_prompt = CRITIC_SYSTEM

    for round_num in range(max_rounds):
        # Step 1: Critique
        critique_messages = [
            {"role": "system", "content": critic_prompt},
            {"role": "user", "content": f"Original query: {context}\n\nResponse to critique:\n{current}"},
        ]

        try:
            critique_resp = await chat(critique_messages, temperature=0.2, max_tokens=1500)
            critique = critique_resp.get("content", "")
        except Exception as e:
            critiques.append(f"Round {round_num + 1} critique error: {e}")
            break

        critiques.append(critique)

        # Step 2: Check verdict
        verdict = _extract_verdict(critique)

        if verdict == "APPROVED" or verdict == "CODE_APPROVED":
            return {
                "final_response": current,
                "was_improved": round_num > 0,
                "critiques": critiques,
                "rounds": round_num + 1,
                "verdict": verdict,
            }

        # Step 3: Revise
        revise_messages = [
            {"role": "system", "content": REVISION_SYSTEM},
            {"role": "user", "content": (
                f"Original query: {context}\n\n"
                f"Original response:\n{current}\n\n"
                f"Critic feedback:\n{critique}\n\n"
                f"Please produce the revised response:"
            )},
        ]

        try:
            revise_resp = await chat(revise_messages, temperature=0.3, max_tokens=4096)
            current = revise_resp.get("content", current)
        except Exception as e:
            critiques.append(f"Round {round_num + 1} revision error: {e}")
            break

    return {
        "final_response": current,
        "was_improved": len(critiques) > 0,
        "critiques": critiques,
        "rounds": len(critiques),
        "verdict": "REVISED",
    }


# ---------------------------------------------------------------------------
# Quick reflection for code
# ---------------------------------------------------------------------------

async def review_code(
    code: str,
    language: str = "python",
    context: str = "",
) -> dict[str, Any]:
    """Quick code review with reflection.

    Returns:
        {"approved": bool, "issues": list[str], "suggestions": list[str], "review": str}
    """
    messages = [
        {"role": "system", "content": CODE_REVIEW_SYSTEM},
        {"role": "user", "content": (
            f"Language: {language}\n"
            f"Context: {context}\n\n"
            f"Code to review:\n```\n{code}\n```"
        )},
    ]

    try:
        resp = await chat(messages, temperature=0.2, max_tokens=2000)
        review = resp.get("content", "")
        approved = "CODE_APPROVED" in review or "APPROVED" in review

        issues = []
        suggestions = []
        current_section = None

        for line in review.split("\n"):
            line = line.strip()
            if "ISSUE" in line.upper():
                current_section = "issues"
            elif "SUGGESTION" in line.upper():
                current_section = "suggestions"
            elif line.startswith("- ") or line.startswith("* "):
                item = line[2:].strip()
                if current_section == "issues":
                    issues.append(item)
                elif current_section == "suggestions":
                    suggestions.append(item)

        return {
            "approved": approved,
            "issues": issues,
            "suggestions": suggestions,
            "review": review,
        }
    except Exception as e:
        return {
            "approved": False,
            "issues": [f"Review error: {e}"],
            "suggestions": [],
            "review": "",
        }


# ---------------------------------------------------------------------------
# Math verification
# ---------------------------------------------------------------------------

async def verify_math(
    question: str,
    answer: str,
) -> dict[str, Any]:
    """Verify a mathematical answer by solving independently.

    Returns:
        {"verified": bool, "correct_answer": str, "explanation": str}
    """
    messages = [
        {"role": "system", "content": (
            "You are a math verification expert. Solve the problem independently "
            "and compare with the given answer. Show your work step by step."
        )},
        {"role": "user", "content": (
            f"Problem: {question}\n"
            f"Given answer: {answer}\n\n"
            f"Solve this problem independently and verify if the given answer is correct."
        )},
    ]

    try:
        resp = await chat(messages, temperature=0.1, max_tokens=2000)
        explanation = resp.get("content", "")

        verified = any(phrase in explanation.lower() for phrase in [
            "correct", "verified", "matches", "right answer", "same answer"
        ])

        return {
            "verified": verified,
            "explanation": explanation,
        }
    except Exception as e:
        return {"verified": False, "explanation": f"Verification error: {e}"}


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _extract_verdict(critique: str) -> str:
    """Extract verdict from critique text."""
    critique_upper = critique.upper()
    if "CODE_APPROVED" in critique_upper:
        return "CODE_APPROVED"
    if "APPROVED" in critique_upper:
        return "APPROVED"
    if "MAJOR_ISSUES" in critique_upper:
        return "MAJOR_ISSUES"
    if "NEEDS_FIX" in critique_upper:
        return "NEEDS_FIX"
    return "NEEDS_FIX"  # Default to requiring revision


# ---------------------------------------------------------------------------
# Integration with agent loop
# ---------------------------------------------------------------------------

async def agent_reflect(
    user_query: str,
    initial_response: str,
    task_type: str = "general",
    enabled: bool = True,
    max_rounds: int = 2,
) -> dict[str, Any]:
    """Main entry point for agent reflection.

    Call this after generating an initial response to self-correct.

    Args:
        user_query: Original user question
        initial_response: First draft of the response
        task_type: "general", "code", "math", "research"
        enabled: Whether reflection is active
        max_rounds: Max correction rounds

    Returns:
        {"response": str, "reflected": bool, "details": dict}
    """
    if not enabled:
        return {"response": initial_response, "reflected": False, "details": {}}

    result = await reflect_and_improve(
        response=initial_response,
        context=user_query,
        task_type=task_type,
        max_rounds=max_rounds,
    )

    return {
        "response": result["final_response"],
        "reflected": result["was_improved"],
        "details": {
            "rounds": result["rounds"],
            "verdict": result.get("verdict", "UNKNOWN"),
            "critiques_count": len(result["critiques"]),
        },
    }


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

REFLECTION_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "reflect_on_response",
            "description": "Critique and improve an AI response for accuracy and quality.",
            "parameters": {
                "type": "object",
                "properties": {
                    "response": {"type": "string", "description": "Response to critique and improve"},
                    "context": {"type": "string", "description": "Original user query for context"},
                    "task_type": {"type": "string", "enum": ["general", "code", "math", "research"], "description": "Type of task"},
                },
                "required": ["response", "context"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "review_code",
            "description": "Review code for bugs, security issues, and improvements.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Code to review"},
                    "language": {"type": "string", "description": "Programming language"},
                    "context": {"type": "string", "description": "What the code should do"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_math",
            "description": "Verify a mathematical answer by solving the problem independently.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The math problem"},
                    "answer": {"type": "string", "description": "The answer to verify"},
                },
                "required": ["question", "answer"],
            },
        },
    },
]


REFLECTION_TOOL_MAP = {
    "reflect_on_response": lambda response, context, task_type="general": reflect_and_improve(response, context, task_type),
    "review_code": review_code,
    "verify_math": verify_math,
}
