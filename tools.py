"""
tools.py – Tool registry, implementations, and OpenAI function-calling schemas.

The agent calls these tools during conversation via OpenAI's function-calling
format. Each tool returns a dict with "result" (str) and optional "error".
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Awaitable, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

from security import run_python_sandboxed, run_shell_sandboxed, check_file_access
from memory import long_term, MemoryEntry

# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = []
_tool_map: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {}


def _register(name: str, description: str, parameters: dict[str, Any]):
    """Decorator to register a tool."""
    def decorator(fn):
        TOOL_SCHEMAS.append({
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        })
        _tool_map[name] = fn
        return fn
    return decorator


def get_tools() -> list[dict[str, Any]]:
    return TOOL_SCHEMAS


async def execute_tool(name: str, arguments: str | dict) -> dict[str, Any]:
    """Execute a tool by name with JSON arguments."""
    fn = _tool_map.get(name)
    if not fn:
        return {"result": "", "error": f"Unknown tool: {name}"}
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
    except json.JSONDecodeError:
        return {"result": "", "error": f"Invalid JSON arguments: {arguments}"}
    try:
        return await fn(**args)
    except TypeError as e:
        return {"result": "", "error": f"Tool argument error: {e}"}
    except Exception as e:
        return {"result": "", "error": f"Tool execution error: {e}"}


# ---------------------------------------------------------------------------
# Web search (DuckDuckGo – free, no API key)
# ---------------------------------------------------------------------------

@_register(
    "web_search",
    "Search the web using DuckDuckGo. Returns titles, URLs, and snippets.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "description": "Max results (default 5)"},
        },
        "required": ["query"],
    },
)
async def web_search(query: str, max_results: int = 5) -> dict[str, Any]:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return {"result": "", "error": "duckduckgo-search not installed. Run: pip install duckduckgo-search"}

    try:
        results = DDGS().text(query, max_results=max_results)
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. **{r['title']}**\n   {r['href']}\n   {r['body']}\n")
        return {"result": "\n".join(lines) if lines else "No results found."}
    except Exception as e:
        return {"result": "", "error": f"Search error: {e}"}


# ---------------------------------------------------------------------------
# Web fetch (trafilatura for clean text extraction)
# ---------------------------------------------------------------------------

@_register(
    "web_fetch",
    "Fetch a URL and extract clean text content.",
    {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
        },
        "required": ["url"],
    },
)
async def web_fetch(url: str) -> dict[str, Any]:
    try:
        import trafilatura
    except ImportError:
        return {"result": "", "error": "trafilatura not installed. Run: pip install trafilatura"}

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; AI-Agent/1.0)"})
            resp.raise_for_status()
        text = trafilatura.extract(resp.text, include_links=False, include_tables=False)
        if text:
            return {"result": text[:6000]}
        return {"result": resp.text[:3000]}
    except Exception as e:
        return {"result": "", "error": f"Fetch error: {e}"}


# ---------------------------------------------------------------------------
# Python execution (sandboxed)
# ---------------------------------------------------------------------------

@_register(
    "run_python",
    "Execute Python code in a sandboxed subprocess. Useful for calculations, data processing, and testing ideas.",
    {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python code to execute"},
        },
        "required": ["code"],
    },
)
async def run_python(code: str) -> dict[str, Any]:
    result = run_python_sandboxed(code, timeout=15)
    output_parts = []
    if result["stdout"]:
        output_parts.append(f"Output:\n{result['stdout']}")
    if result["stderr"]:
        output_parts.append(f"Stderr:\n{result['stderr']}")
    if result["error"]:
        output_parts.append(f"Error: {result['error']}")
    text = "\n".join(output_parts) if output_parts else "(no output)"
    return {"result": text, "error": result["error"]}


# ---------------------------------------------------------------------------
# Shell command (sandboxed)
# ---------------------------------------------------------------------------

@_register(
    "run_shell",
    "Run a shell command (ls, cat, find, date, etc). Sandbox-restricted.",
    {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to run"},
        },
        "required": ["command"],
    },
)
async def run_shell(command: str) -> dict[str, Any]:
    result = run_shell_sandboxed(command, timeout=10)
    output_parts = []
    if result["stdout"]:
        output_parts.append(result["stdout"])
    if result["stderr"]:
        output_parts.append(f"stderr: {result['stderr']}")
    if result["error"]:
        output_parts.append(f"Error: {result['error']}")
    return {"result": "\n".join(output_parts) or "(no output)", "error": result["error"]}


# ---------------------------------------------------------------------------
# Memory operations
# ---------------------------------------------------------------------------

@_register(
    "save_memory",
    "Save an important fact, insight, or observation to long-term memory.",
    {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Content to remember"},
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags for categorization",
            },
            "importance": {
                "type": "number",
                "description": "Importance 0.0-1.0 (default 0.5)",
            },
        },
        "required": ["text"],
    },
)
async def save_memory(text: str, tags: list[str] | None = None, importance: float = 0.5) -> dict[str, Any]:
    entry = MemoryEntry(text=text, tags=tags or [], importance=importance)
    long_term.add(entry)
    return {"result": f"Saved to long-term memory: '{text[:80]}...'"}


@_register(
    "recall_memory",
    "Search long-term memory for relevant past information.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to search for"},
        },
        "required": ["query"],
    },
)
async def recall_memory(query: str) -> dict[str, Any]:
    results = long_term.search(query, limit=5)
    if not results:
        return {"result": "No matching memories found."}
    lines = []
    for i, e in enumerate(results, 1):
        tags = f" [{', '.join(e.tags)}]" if e.tags else ""
        lines.append(f"{i}. ({e.source}{tags}) {e.text[:200]}")
    return {"result": "\n".join(lines)}


# ---------------------------------------------------------------------------
# Obsidian vault integration (optional)
# ---------------------------------------------------------------------------

@_register(
    "obsidian_write",
    "Write a note to your Obsidian vault via the Local REST API.",
    {
        "type": "object",
        "properties": {
            "filename": {"type": "string", "description": "Note filename (without .md)"},
            "content": {"type": "string", "description": "Markdown content to write"},
            "folder": {"type": "string", "description": "Subfolder in vault (default: root)"},
        },
        "required": ["filename", "content"],
    },
)
async def obsidian_write(filename: str, content: str, folder: str = "") -> dict[str, Any]:
    api_key = os.getenv("OBSIDIAN_API_KEY")
    base_url = os.getenv("OBSIDIAN_URL", "http://127.0.0.1:27123")
    vault = os.getenv("OBSIDIAN_VAULT", "~/ai-agent/vault")

    if not api_key:
        return {"result": "", "error": "OBSIDIAN_API_KEY not set. Configure it in .env"}

    path = f"{folder}/{filename}.md" if folder else f"{filename}.md"
    path = path.strip("/")
    url = f"{base_url}/vault/{path}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.put(
                url,
                content=content,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "text/markdown",
                },
            )
            if resp.status_code in (200, 201, 204):
                return {"result": f"Note saved to Obsidian: {path}"}
            return {"result": "", "error": f"Obsidian API error: {resp.status_code} {resp.text[:200]}"}
    except Exception as e:
        return {"result": "", "error": f"Obsidian connection error: {e}"}


@_register(
    "obsidian_read",
    "Read a note from your Obsidian vault via the Local REST API.",
    {
        "type": "object",
        "properties": {
            "filename": {"type": "string", "description": "Note filename (without .md)"},
            "folder": {"type": "string", "description": "Subfolder in vault"},
        },
        "required": ["filename"],
    },
)
async def obsidian_read(filename: str, folder: str = "") -> dict[str, Any]:
    api_key = os.getenv("OBSIDIAN_API_KEY")
    base_url = os.getenv("OBSIDIAN_URL", "http://127.0.0.1:27123")

    if not api_key:
        return {"result": "", "error": "OBSIDIAN_API_KEY not set."}

    path = f"{folder}/{filename}.md" if folder else f"{filename}.md"
    path = path.strip("/")
    url = f"{base_url}/vault/{path}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
            if resp.status_code == 200:
                return {"result": resp.text}
            return {"result": "", "error": f"Not found or error: {resp.status_code}"}
    except Exception as e:
        return {"result": "", "error": f"Obsidian error: {e}"}


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------

@_register(
    "read_file",
    "Read a local file's contents.",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to read"},
        },
        "required": ["path"],
    },
)
async def read_file(path: str) -> dict[str, Any]:
    err = check_file_access(path, "read")
    if err:
        return {"result": "", "error": err}
    try:
        resolved = Path(path).expanduser().resolve()
        content = resolved.read_text(encoding="utf-8")
        return {"result": content[:8000]}
    except Exception as e:
        return {"result": "", "error": f"Read error: {e}"}


@_register(
    "write_file",
    "Write content to a local file.",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to write"},
            "content": {"type": "string", "description": "Content to write"},
        },
        "required": ["path", "content"],
    },
)
async def write_file(path: str, content: str) -> dict[str, Any]:
    err = check_file_access(path, "write")
    if err:
        return {"result": "", "error": err}
    try:
        resolved = Path(path).expanduser().resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return {"result": f"File written: {resolved}"}
    except Exception as e:
        return {"result": "", "error": f"Write error: {e}"}
