"""
llm.py – Multi-provider LLM abstraction using AsyncOpenAI.

Each provider is backed by the same OpenAI-compatible client interface.
The agent picks the first available provider based on .env keys.
"""

from __future__ import annotations

import os
import json
from typing import Any, AsyncIterator, Optional

from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

PROVIDERS: dict[str, dict[str, str]] = {
    "groq": {
        "key_env": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
    },
    "openrouter": {
        "key_env": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "meta-llama/llama-3.3-70b-instruct",
    },
    "gemini": {
        "key_env": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.0-flash",
    },
    "together": {
        "key_env": "TOGETHER_API_KEY",
        "base_url": "https://api.together.xyz/v1",
        "model": "meta-llama/Meta-Llama-3.3-70B-Instruct-Turbo",
    },
}

DEFAULT_ORDER = ["groq", "openrouter", "gemini", "together"]


def _resolve_provider(name: str | None = None) -> tuple[str, dict[str, str]]:
    """Return (provider_name, config) for the chosen or first available provider."""
    if name:
        cfg = PROVIDERS.get(name.lower())
        if cfg and os.getenv(cfg["key_env"]):
            return name.lower(), cfg
        raise ValueError(f"Provider '{name}' not configured or key missing ({cfg['key_env']})")

    for pname in DEFAULT_ORDER:
        cfg = PROVIDERS[pname]
        if os.getenv(cfg["key_env"]):
            return pname, cfg

    raise RuntimeError(
        "No LLM provider configured. Set at least one of: "
        + ", ".join(c["key_env"] for c in PROVIDERS.values())
    )


def get_client(provider: str | None = None) -> tuple[AsyncOpenAI, str, str]:
    """Create an AsyncOpenAI client for the chosen provider.

    Returns:
        (client, provider_name, model_name)
    """
    pname, cfg = _resolve_provider(provider)
    client = AsyncOpenAI(
        api_key=os.getenv(cfg["key_env"]),
        base_url=cfg["base_url"],
    )
    return client, pname, cfg["model"]


# ---------------------------------------------------------------------------
# Streaming chat completion
# ---------------------------------------------------------------------------

async def chat_stream(
    messages: list[dict[str, Any]],
    *,
    provider: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> AsyncIterator[str]:
    """Yield text chunks from a streaming chat completion."""
    client, pname, model = get_client(provider)
    kwargs: dict[str, Any] = dict(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    stream = await client.chat.completions.create(**kwargs)
    async for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield delta.content


# ---------------------------------------------------------------------------
# Non-streaming chat (used by consolidator & tools)
# ---------------------------------------------------------------------------

async def chat(
    messages: list[dict[str, Any]],
    *,
    provider: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Single non-streaming completion; returns the assistant message dict."""
    client, pname, model = get_client(provider)
    kwargs: dict[str, Any] = dict(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    resp = await client.chat.completions.create(**kwargs)
    choice = resp.choices[0]
    msg = choice.message

    result: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        result["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]
    return result
