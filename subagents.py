"""
subagents.py – Sub-Agent Delegation for parallel task execution.

The main router agent can spawn parallel "worker" agents for heavy tasks:
- Multiple research queries simultaneously
- Parallel code analysis
- Concurrent web searches
- Distributed memory consolidation

Each sub-agent runs in its own async context with isolated conversation history.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from llm import chat, get_client
from tools import get_tools, execute_tool
from memory import short_term, long_term, MemoryEntry


# ---------------------------------------------------------------------------
# Sub-Agent types
# ---------------------------------------------------------------------------

class SubAgentType:
    RESEARCH = "research"       # Web research and information gathering
    CODE = "code"               # Code analysis and generation
    ANALYSIS = "analysis"       # Data analysis and reasoning
    WRITING = "writing"         # Content generation
    SUMMARY = "summary"         # Summarization of large content
    CUSTOM = "custom"           # Custom task


# ---------------------------------------------------------------------------
# Sub-Agent definition
# ---------------------------------------------------------------------------

@dataclass
class SubAgent:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: str = SubAgentType.CUSTOM
    task: str = ""
    status: str = "pending"  # pending, running, completed, failed
    result: str = ""
    error: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0
    tools_used: list[str] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def duration(self) -> float:
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return 0.0


# ---------------------------------------------------------------------------
# Sub-Agent system prompts
# ---------------------------------------------------------------------------

SUB_AGENT_PROMPTS = {
    SubAgentType.RESEARCH: (
        "You are a research sub-agent. Your job is to gather comprehensive "
        "information on the given topic using web search and content fetching. "
        "Be thorough, cite sources, and provide actionable insights. "
        "Focus on finding accurate, up-to-date information."
    ),
    SubAgentType.CODE: (
        "You are a code sub-agent. Analyze, review, or generate code as requested. "
        "Be precise, follow best practices, and include error handling. "
        "Output clean, well-documented code."
    ),
    SubAgentType.ANALYSIS: (
        "You are an analysis sub-agent. Break down complex problems, identify patterns, "
        "and provide data-driven insights. Show your reasoning step by step."
    ),
    SubAgentType.WRITING: (
        "You are a writing sub-agent. Generate high-quality content based on the request. "
        "Focus on clarity, engagement, and accuracy. Match the requested tone and style."
    ),
    SubAgentType.SUMMARY: (
        "You are a summarization sub-agent. Condense the provided content into clear, "
        "accurate summaries. Preserve key points and maintain important details."
    ),
    SubAgentType.CUSTOM: (
        "You are a helpful sub-agent. Complete the assigned task accurately and efficiently. "
        "Use available tools when needed. Be concise in your output."
    ),
}


# ---------------------------------------------------------------------------
# Sub-Agent executor
# ---------------------------------------------------------------------------

class SubAgentRunner:
    """Runs a sub-agent with isolated context."""

    def __init__(self):
        self.active_agents: dict[str, SubAgent] = {}

    async def run(
        self,
        task: str,
        agent_type: str = SubAgentType.CUSTOM,
        context: str = "",
        max_iterations: int = 3,
        timeout: int = 120,
    ) -> SubAgent:
        """Execute a sub-agent task.

        Args:
            task: The task description
            agent_type: Type of sub-agent
            context: Additional context from parent
            max_iterations: Max tool-call iterations
            timeout: Max execution time in seconds

        Returns:
            SubAgent with results
        """
        agent = SubAgent(type=agent_type, task=task, status="running", started_at=time.time())
        self.active_agents[agent.id] = agent

        system_prompt = SUB_AGENT_PROMPTS.get(agent_type, SUB_AGENT_PROMPTS[SubAgentType.CUSTOM])

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Task: {task}\n\nContext: {context}" if context else f"Task: {task}"},
        ]

        try:
            result = await asyncio.wait_for(
                self._run_loop(agent, messages, max_iterations),
                timeout=timeout,
            )
            agent.result = result
            agent.status = "completed"
        except asyncio.TimeoutError:
            agent.status = "failed"
            agent.error = f"Timed out after {timeout}s"
        except Exception as e:
            agent.status = "failed"
            agent.error = str(e)
        finally:
            agent.completed_at = time.time()
            self.active_agents.pop(agent.id, None)

        return agent

    async def _run_loop(
        self,
        agent: SubAgent,
        messages: list[dict[str, Any]],
        max_iterations: int,
    ) -> str:
        """Run the sub-agent tool-calling loop."""
        for _ in range(max_iterations):
            response = await chat(messages, tools=get_tools(), temperature=0.5, max_tokens=2048)
            messages.append(response)

            tool_calls = response.get("tool_calls")
            if not tool_calls:
                return response.get("content", "")

            for tc in tool_calls:
                func_name = tc["function"]["name"]
                agent.tools_used.append(func_name)

                result = await execute_tool(func_name, tc["function"]["arguments"])
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False)[:4000],
                })

        return messages[-1].get("content", "(max iterations reached)")

    async def run_parallel(
        self,
        tasks: list[dict[str, Any]],
        timeout: int = 120,
    ) -> list[SubAgent]:
        """Run multiple sub-agents in parallel.

        Args:
            tasks: List of {"task": str, "type": str, "context": str}
            timeout: Max time for all agents

        Returns:
            List of completed SubAgent results
        """
        coros = []
        for t in tasks:
            coros.append(self.run(
                task=t["task"],
                agent_type=t.get("type", SubAgentType.CUSTOM),
                context=t.get("context", ""),
                timeout=timeout,
            ))

        return await asyncio.gather(*coros)


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

runner = SubAgentRunner()


async def research_parallel(
    queries: list[str],
    context: str = "",
    timeout: int = 120,
) -> dict[str, Any]:
    """Run parallel research on multiple queries.

    Spawns one sub-agent per query, runs them simultaneously,
    then synthesizes the results.
    """
    tasks = [
        {"task": q, "type": SubAgentType.RESEARCH, "context": context}
        for q in queries
    ]

    agents = await runner.run_parallel(tasks, timeout=timeout)

    # Collect results
    results = []
    for agent in agents:
        results.append({
            "query": agent.task,
            "status": agent.status,
            "result": agent.result if agent.status == "completed" else agent.error,
            "duration": f"{agent.duration:.1f}s",
            "tools_used": agent.tools_used,
        })

    # Synthesize if all succeeded
    successful = [a for a in agents if a.status == "completed"]
    synthesis = ""

    if len(successful) > 1:
        combined = "\n\n".join(
            f"## Research: {a.task}\n{a.result}" for a in successful
        )
        synthesis_resp = await chat([
            {"role": "system", "content": "Synthesize these research findings into a comprehensive, well-organized response. Identify key themes and provide actionable insights."},
            {"role": "user", "content": combined},
        ], temperature=0.3, max_tokens=2000)
        synthesis = synthesis_resp.get("content", "")
    elif successful:
        synthesis = successful[0].result

    return {
        "synthesis": synthesis,
        "individual_results": results,
        "agents_succeeded": len(successful),
        "agents_failed": len(agents) - len(successful),
    }


async def code_review_parallel(
    code_files: dict[str, str],
    context: str = "",
    timeout: int = 60,
) -> dict[str, Any]:
    """Review multiple code files in parallel.

    Args:
        code_files: {filename: code_content}
        context: What the code should do
    """
    tasks = [
        {
            "task": f"Review this code for bugs, security issues, and improvements:\n\nFile: {filename}\n```{filename.split('.')[-1]}\n{code}\n```",
            "type": SubAgentType.CODE,
            "context": context,
        }
        for filename, code in code_files.items()
    ]

    agents = await runner.run_parallel(tasks, timeout=timeout)

    results = {}
    for agent in agents:
        filename = agent.task.split("File: ")[1].split("\n")[0] if "File: " in agent.task else "unknown"
        results[filename] = {
            "status": agent.status,
            "review": agent.result if agent.status == "completed" else agent.error,
        }

    return {"reviews": results}


async def delegate_task(
    task: str,
    agent_type: str = SubAgentType.CUSTOM,
    context: str = "",
    timeout: int = 120,
) -> dict[str, Any]:
    """Delegate a single task to a sub-agent.

    The sub-agent runs with its own context and returns a result.
    """
    agent = await runner.run(
        task=task,
        agent_type=agent_type,
        context=context,
        timeout=timeout,
    )

    # Save notable results to memory
    if agent.status == "completed" and len(agent.result) > 100:
        long_term.add(MemoryEntry(
            text=f"Sub-agent ({agent.type}) completed: {agent.task[:100]}. Result: {agent.result[:300]}",
            source="sub_agent",
            importance=0.4,
        ))

    return {
        "result": agent.result,
        "status": agent.status,
        "error": agent.error,
        "duration": f"{agent.duration:.1f}s",
        "tools_used": agent.tools_used,
    }


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

SUBAGENT_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "research_parallel",
            "description": "Research multiple topics simultaneously using parallel sub-agents. Returns synthesized findings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "queries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Research queries to investigate in parallel",
                    },
                    "context": {"type": "string", "description": "Additional context for the research"},
                },
                "required": ["queries"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_task",
            "description": "Delegate a complex task to a specialized sub-agent worker.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Task description"},
                    "agent_type": {"type": "string", "enum": ["research", "code", "analysis", "writing", "summary", "custom"], "description": "Type of sub-agent"},
                    "context": {"type": "string", "description": "Additional context"},
                },
                "required": ["task"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "code_review_parallel",
            "description": "Review multiple code files simultaneously for bugs and improvements.",
            "parameters": {
                "type": "object",
                "properties": {
                    "files": {
                        "type": "object",
                        "description": "Object mapping filenames to code content",
                    },
                    "context": {"type": "string", "description": "What the code should do"},
                },
                "required": ["files"],
            },
        },
    },
]


SUBAGENT_TOOL_MAP = {
    "research_parallel": research_parallel,
    "delegate_task": delegate_task,
    "code_review_parallel": code_review_parallel,
}
