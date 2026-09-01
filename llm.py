"""
llm.py – Multi-provider LLM abstraction using AsyncOpenAI.

Each provider is backed by the same OpenAI-compatible client interface.
The agent picks the first available provider based on .env keys.
Supports runtime provider/model switching for the session.
"""

from __future__ import annotations

import os
import json
from typing import Any, AsyncIterator, Optional

from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Provider registry with available models
# ---------------------------------------------------------------------------

PROVIDERS: dict[str, dict[str, Any]] = {
    "groq": {
        "key_env": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "display_name": "Groq (Fastest)",
        "description": "Ultra-fast inference, free tier available",
        "models": [
            {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B", "description": "Best all-around (recommended)", "speed": "⚡⚡⚡", "quality": "⭐⭐⭐⭐"},
            {"id": "llama-3.1-8b-instant", "name": "Llama 3.1 8B Instant", "description": "Fastest, good for simple tasks", "speed": "⚡⚡⚡⚡", "quality": "⭐⭐⭐"},
            {"id": "llama-3.1-70b-versatile", "name": "Llama 3.1 70B", "description": "Previous gen, still excellent", "speed": "⚡⚡⚡", "quality": "⭐⭐⭐⭐"},
            {"id": "mixtral-8x7b-32768", "name": "Mixtral 8x7B", "description": "Good for long context (32K)", "speed": "⚡⚡⚡", "quality": "⭐⭐⭐⭐"},
            {"id": "gemma2-9b-it", "name": "Gemma 2 9B", "description": "Google's efficient model", "speed": "⚡⚡⚡⚡", "quality": "⭐⭐⭐"},
            {"id": "mistral-saba-24b", "name": "Mistral Saba 24B", "description": "Multilingual, strong reasoning", "speed": "⚡⚡⚡", "quality": "⭐⭐⭐⭐"},
        ],
    },
    "openrouter": {
        "key_env": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "meta-llama/llama-3.3-70b-instruct",
        "display_name": "OpenRouter (100+ Models)",
        "description": "Access to many providers, pay-per-use",
        "models": [
            {"id": "meta-llama/llama-3.3-70b-instruct", "name": "Llama 3.3 70B", "description": "Best free model", "speed": "⚡⚡⚡", "quality": "⭐⭐⭐⭐"},
            {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet", "description": "Excellent reasoning, paid", "speed": "⚡⚡", "quality": "⭐⭐⭐⭐⭐"},
            {"id": "openai/gpt-4o", "name": "GPT-4o", "description": "OpenAI flagship, paid", "speed": "⚡⚡", "quality": "⭐⭐⭐⭐⭐"},
            {"id": "google/gemini-2.0-flash-001", "name": "Gemini 2.0 Flash", "description": "Fast and capable", "speed": "⚡⚡⚡⚡", "quality": "⭐⭐⭐⭐"},
            {"id": "deepseek/deepseek-chat", "name": "DeepSeek V3", "description": "Strong coding, cheap", "speed": "⚡⚡⚡", "quality": "⭐⭐⭐⭐"},
            {"id": "mistralai/mistral-large-2411", "name": "Mistral Large", "description": "Strong multilingual", "speed": "⚡⚡", "quality": "⭐⭐⭐⭐"},
        ],
    },
    "gemini": {
        "key_env": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "default_model": "gemini-2.0-flash",
        "display_name": "Google Gemini (Free Tier)",
        "description": "Google's models, generous free tier",
        "models": [
            {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash", "description": "Fast, good all-around (recommended)", "speed": "⚡⚡⚡⚡", "quality": "⭐⭐⭐⭐"},
            {"id": "gemini-2.5-flash-preview-05-20", "name": "Gemini 2.5 Flash Preview", "description": "Latest thinking model", "speed": "⚡⚡⚡", "quality": "⭐⭐⭐⭐⭐"},
            {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro", "description": "Best quality, large context", "speed": "⚡⚡", "quality": "⭐⭐⭐⭐⭐"},
            {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash", "description": "Balanced speed/quality", "speed": "⚡⚡⚡⚡", "quality": "⭐⭐⭐⭐"},
        ],
    },
    "together": {
        "key_env": "TOGETHER_API_KEY",
        "base_url": "https://api.together.xyz/v1",
        "default_model": "meta-llama/Meta-Llama-3.3-70B-Instruct-Turbo",
        "display_name": "Together AI (Open Source)",
        "description": "Open-source models, competitive pricing",
        "models": [
            {"id": "meta-llama/Meta-Llama-3.3-70B-Instruct-Turbo", "name": "Llama 3.3 70B Turbo", "description": "Best open-source (recommended)", "speed": "⚡⚡⚡", "quality": "⭐⭐⭐⭐"},
            {"id": "meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo", "name": "Llama 3.1 405B Turbo", "description": "Largest open model", "speed": "⚡⚡", "quality": "⭐⭐⭐⭐⭐"},
            {"id": "deepseek-ai/DeepSeek-V3", "name": "DeepSeek V3", "description": "Strong coding model", "speed": "⚡⚡⚡", "quality": "⭐⭐⭐⭐"},
            {"id": "Qwen/Qwen2.5-72B-Instruct-Turbo", "name": "Qwen 2.5 72B Turbo", "description": "Excellent multilingual", "speed": "⚡⚡⚡", "quality": "⭐⭐⭐⭐"},
            {"id": "mistralai/Mixtral-8x22B-Instruct-v0.1", "name": "Mixtral 8x22B", "description": "Long context, good quality", "speed": "⚡⚡⚡", "quality": "⭐⭐⭐⭐"},
        ],
    },
}

# Custom provider is loaded dynamically from env vars
CUSTOM_PROVIDER_ENV = {
    "key_env": "CUSTOM_API_KEY",
    "base_url_env": "CUSTOM_BASE_URL",
    "model_env": "CUSTOM_MODEL",
    "display_name": "Custom Provider",
    "description": "Any OpenAI-compatible API (vLLM, Ollama, LM Studio, etc.)",
}

def _load_custom_provider() -> dict[str, Any] | None:
    """Load custom provider config from env vars if configured."""
    api_key = os.getenv(CUSTOM_PROVIDER_ENV["key_env"])
    base_url = os.getenv(CUSTOM_PROVIDER_ENV["base_url_env"])
    model = os.getenv(CUSTOM_PROVIDER_ENV["model_env"])
    if not api_key or not base_url or not model:
        return None
    return {
        "key_env": CUSTOM_PROVIDER_ENV["key_env"],
        "base_url": base_url,
        "default_model": model,
        "display_name": f"Custom ({base_url.split('//')[-1][:30]})",
        "description": CUSTOM_PROVIDER_ENV["description"],
        "models": [
            {"id": model, "name": model, "description": "Custom model", "speed": "–", "quality": "–"},
        ],
    }

DEFAULT_ORDER = ["groq", "openrouter", "gemini", "together"]

# ---------------------------------------------------------------------------
# Session-level provider/model override
# ---------------------------------------------------------------------------

_session_provider: str | None = None
_session_model: str | None = None


def set_session_provider(provider: str | None, model: str | None = None) -> dict[str, Any]:
    """Set the provider and optional model for the current session.

    Returns info dict about the selected provider/model.
    """
    global _session_provider, _session_model

    if provider is None:
        _session_provider = None
        _session_model = None
        return {"action": "reset", "message": "Session provider reset to auto-detect"}

    pname = provider.lower()
    # Handle custom provider
    if pname == "custom":
        custom_cfg = _load_custom_provider()
        if not custom_cfg:
            return {"error": "Custom provider not configured. Set CUSTOM_API_KEY, CUSTOM_BASE_URL, CUSTOM_MODEL in .env"}
        _session_provider = "custom"
        _session_model = model or custom_cfg["default_model"]
        return {
            "action": "set",
            "provider": "custom",
            "model": _session_model,
            "display_name": custom_cfg["display_name"],
            "message": f"Switched to {custom_cfg['display_name']} / {_session_model}",
        }
    if pname not in PROVIDERS:
        return {"error": f"Unknown provider: {pname}. Available: {', '.join(list(PROVIDERS.keys()) + ['custom'])}"}

    cfg = PROVIDERS[pname]
    if not os.getenv(cfg["key_env"]):
        return {"error": f"No API key set for {pname} ({cfg['key_env']}). Add it to .env"}

    # Validate model if specified
    if model:
        valid_ids = [m["id"] for m in cfg["models"]]
        if model not in valid_ids:
            # Try partial match
            matches = [m for m in valid_ids if model.lower() in m.lower()]
            if len(matches) == 1:
                model = matches[0]
            elif len(matches) > 1:
                return {"error": f"Multiple models match '{model}': {matches}. Be more specific."}
            else:
                return {"error": f"Model '{model}' not found for {pname}. Use /model list to see options."}

    _session_provider = pname
    _session_model = model  # None = use default

    actual_model = model or cfg["default_model"]
    return {
        "action": "set",
        "provider": pname,
        "model": actual_model,
        "display_name": cfg["display_name"],
        "message": f"Switched to {cfg['display_name']} / {actual_model}",
    }


def get_session_info() -> dict[str, Any]:
    """Return current session provider/model info."""
    if _session_provider == "custom":
        custom_cfg = _load_custom_provider()
        if custom_cfg:
            return {"provider": "custom", "model": _session_model or custom_cfg["default_model"], "display": custom_cfg["display_name"]}
    if _session_provider and _session_provider in PROVIDERS:
        cfg = PROVIDERS[_session_provider]
        model = _session_model or cfg["default_model"]
        return {"provider": _session_provider, "model": model, "display": cfg["display_name"]}
    return {"provider": None, "model": None, "display": "auto"}


def list_providers() -> list[dict[str, Any]]:
    """List all providers with availability status and models."""
    result = []
    for pname in DEFAULT_ORDER:
        cfg = PROVIDERS[pname]
        has_key = bool(os.getenv(cfg["key_env"]))
        result.append({
            "id": pname,
            "display_name": cfg["display_name"],
            "description": cfg["description"],
            "key_env": cfg["key_env"],
            "available": has_key,
            "default_model": cfg["default_model"],
            "models": cfg["models"],
            "session_active": _session_provider == pname,
        })
    # Add custom provider if configured
    custom_cfg = _load_custom_provider()
    if custom_cfg:
        result.append({
            "id": "custom",
            "display_name": custom_cfg["display_name"],
            "description": custom_cfg["description"],
            "key_env": CUSTOM_PROVIDER_ENV["key_env"],
            "available": True,
            "default_model": custom_cfg["default_model"],
            "models": custom_cfg["models"],
            "session_active": _session_provider == "custom",
        })
    return result


def get_models_for_provider(provider: str) -> list[dict[str, str]]:
    """Return available models for a provider."""
    cfg = PROVIDERS.get(provider.lower())
    if not cfg:
        return []
    return cfg["models"]


# ---------------------------------------------------------------------------
# Live model fetching from provider APIs
# ---------------------------------------------------------------------------

_model_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_MODEL_CACHE_TTL = 3600  # 1 hour


def _cache_hit(provider: str) -> list[dict[str, Any]] | None:
    """Return cached models if still fresh, else None."""
    import time
    if provider in _model_cache:
        ts, models = _model_cache[provider]
        if time.time() - ts < _MODEL_CACHE_TTL:
            return models
    return None


def _cache_set(provider: str, models: list[dict[str, Any]]) -> None:
    import time
    _model_cache[provider] = (time.time(), models)


async def fetch_models_from_provider(provider: str) -> list[dict[str, Any]]:
    """Fetch live model list from a provider's API.

    Returns list of dicts: {"id": ..., "name": ..., "description": ...}
    Falls back to hardcoded list on error.
    """
    import httpx
    import time

    cached = _cache_hit(provider)
    if cached is not None:
        return cached

    fallback = PROVIDERS.get(provider, {}).get("models", [])
    try:
        if provider == "openrouter":
            models = await _fetch_openrouter_models()
        elif provider == "groq":
            models = await _fetch_groq_models()
        elif provider == "together":
            models = await _fetch_together_models()
        elif provider == "gemini":
            models = await _fetch_gemini_models()
        elif provider == "custom":
            models = await _fetch_custom_models()
        else:
            models = fallback

        if models:
            _cache_set(provider, models)
            return models
        # Empty from API → use hardcoded fallback
        return fallback
    except Exception:
        # Fallback to hardcoded list
        return fallback


async def _fetch_openrouter_models() -> list[dict[str, Any]]:
    """Fetch models from OpenRouter API."""
    import httpx
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return []
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
        data = resp.json()

    models = []
    for m in data.get("data", []):
        mid = m.get("id", "")
        # Skip embedding, moderation, and tts models
        if any(skip in mid.lower() for skip in ["embed", "moderat", "tts", "whisper", "dall-e"]):
            continue
        # Prefer instruct/chat models
        pricing = m.get("pricing", {})
        prompt_price = float(pricing.get("prompt", "0") or "0")
        is_free = prompt_price == 0
        models.append({
            "id": mid,
            "name": m.get("name", mid),
            "description": f"{'🆓 Free' if is_free else f'${prompt_price*1e6:.1f}/1M tokens'} | ctx:{m.get('context_length', '?')}",
            "speed": "",
            "quality": "",
        })

    # Sort: free first, then by context length desc
    models.sort(key=lambda x: (not x["description"].startswith("🆓"), -int(x["description"].split("ctx:")[-1].split(")")[0].replace(",", "").replace("?", "0") if "ctx:" in x["description"] else 0)))
    return models


async def _fetch_groq_models() -> list[dict[str, Any]]:
    """Fetch models from Groq API."""
    import httpx
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return []
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
        data = resp.json()

    models = []
    for m in data.get("data", []):
        mid = m.get("id", "")
        created = m.get("created", 0)
        models.append({
            "id": mid,
            "name": mid,
            "description": f"Groq hosted | {m.get('owned_by', 'groq')}",
            "speed": "⚡",
            "quality": "",
        })
    # Sort newest first
    models.sort(key=lambda x: x["id"])
    return models


async def _fetch_together_models() -> list[dict[str, Any]]:
    """Fetch models from Together API."""
    import httpx
    api_key = os.getenv("TOGETHER_API_KEY")
    if not api_key:
        return []
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://api.together.xyz/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
        data = resp.json()

    models = []
    for m in data if isinstance(data, list) else data.get("data", []):
        mid = m.get("id", "")
        # Skip embedding and non-chat models
        if any(skip in mid.lower() for skip in ["embed", "image", "tts", "moderation"]):
            continue
        pricing = m.get("pricing", {})
        prompt_price = float(pricing.get("prompt", "0") or "0")
        ctx = m.get("context_length", "?")
        models.append({
            "id": mid,
            "name": m.get("display_name", mid.split("/")[-1]),
            "description": f"{'🆓 Free' if prompt_price == 0 else f'${prompt_price*1e6:.1f}/1M tokens'} | ctx:{ctx}",
            "speed": "",
            "quality": "",
        })
    models.sort(key=lambda x: (not x["description"].startswith("🆓"), x["id"]))
    return models


async def _fetch_gemini_models() -> list[dict[str, Any]]:
    """Fetch models from Google Gemini API."""
    import httpx
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return []
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
        )
        resp.raise_for_status()
        data = resp.json()

    models = []
    for m in data.get("models", []):
        name = m.get("name", "")
        mid = name.replace("models/", "")
        # Only include generateContent-capable models
        methods = m.get("supportedGenerationMethods", [])
        if "generateContent" not in methods:
            continue
        display = m.get("displayName", mid)
        desc = m.get("description", "")[:80]
        models.append({
            "id": mid,
            "name": display,
            "description": desc or f"Google {mid}",
            "speed": "",
            "quality": "",
        })
    return models


async def _fetch_custom_models() -> list[dict[str, Any]]:
    """Fetch models from custom provider's /v1/models endpoint."""
    import httpx
    base_url = os.getenv("CUSTOM_BASE_URL")
    api_key = os.getenv("CUSTOM_API_KEY", "none")
    if not base_url:
        return []
    url = base_url.rstrip("/") + "/models"
    headers = {}
    if api_key and api_key.lower() != "none":
        headers["Authorization"] = f"Bearer {api_key}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    models = []
    for m in data.get("data", []):
        mid = m.get("id", m.get("name", ""))
        models.append({
            "id": mid,
            "name": mid,
            "description": "Custom model",
            "speed": "",
            "quality": "",
        })
    return models


# ---------------------------------------------------------------------------
# Provider resolution & client creation
# ---------------------------------------------------------------------------


def _resolve_provider(name: str | None = None) -> tuple[str, dict[str, Any], str]:
    """Return (provider_name, config, model) for the chosen or first available provider.

    Resolution order:
      1. Explicit `name` argument
      2. Session-level override (set_session_provider)
      3. First available from .env keys
    """
    # 1. Explicit provider name
    if name:
        pname = name.lower()
        # Handle custom provider
        if pname == "custom":
            custom_cfg = _load_custom_provider()
            if custom_cfg:
                model = _session_model or custom_cfg["default_model"]
                return "custom", custom_cfg, model
            raise ValueError("Custom provider not configured. Set CUSTOM_API_KEY, CUSTOM_BASE_URL, CUSTOM_MODEL in .env")
        cfg = PROVIDERS.get(pname)
        if cfg and os.getenv(cfg["key_env"]):
            if _session_provider == pname and _session_model:
                return pname, cfg, _session_model
            return pname, cfg, cfg["default_model"]
        if cfg:
            raise ValueError(f"Provider '{name}' not configured or key missing ({cfg['key_env']})")
        available = list(PROVIDERS.keys()) + ['custom']
        raise ValueError(f"Unknown provider: '{name}'. Available: {', '.join(available)}")

    # 2. Session override
    if _session_provider == "custom":
        custom_cfg = _load_custom_provider()
        if custom_cfg:
            model = _session_model or custom_cfg["default_model"]
            return "custom", custom_cfg, model
    if _session_provider and _session_provider in PROVIDERS:
        cfg = PROVIDERS[_session_provider]
        if os.getenv(cfg["key_env"]):
            model = _session_model or cfg["default_model"]
            return _session_provider, cfg, model

    # 3. Auto-detect from env
    for pname in DEFAULT_ORDER:
        cfg = PROVIDERS[pname]
        if os.getenv(cfg["key_env"]):
            return pname, cfg, cfg["default_model"]

    # 4. Try custom provider as last resort
    custom_cfg = _load_custom_provider()
    if custom_cfg:
        return "custom", custom_cfg, custom_cfg["default_model"]

    raise RuntimeError(
        "No LLM provider configured. Set at least one of: "
        + ", ".join(c["key_env"] for c in PROVIDERS.values())
        + ", or CUSTOM_API_KEY+CUSTOM_BASE_URL+CUSTOM_MODEL"
    )


def get_client(provider: str | None = None, model: str | None = None) -> tuple[AsyncOpenAI, str, str]:
    """Create an AsyncOpenAI client for the chosen provider.

    Args:
        provider: Explicit provider name, or None for auto-detect.
        model: Override model, or None for default/session.

    Returns:
        (client, provider_name, model_name)
    """
    pname, cfg, resolved_model = _resolve_provider(provider)
    if model:
        resolved_model = model
    client = AsyncOpenAI(
        api_key=os.getenv(cfg["key_env"]),
        base_url=cfg["base_url"],
    )
    return client, pname, resolved_model


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
