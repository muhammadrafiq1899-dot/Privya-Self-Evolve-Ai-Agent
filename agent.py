#!/usr/bin/env python3
"""
agent.py – Self-evolving AI agent with prompt_toolkit TUI.

Launch: python agent.py

TUI powered by prompt_toolkit for full Termux/Android support:
  - Arrow keys scroll output
  - Autocomplete for slash commands
  - Model picker with arrow keys + enter
  - Works perfectly on Termux Android

Features:
  - Multi-provider LLM (Groq / OpenRouter / Gemini / Together / Custom)
  - Tool calling with sandboxed execution
  - Short-term, long-term, and procedural memory
  - Vision, voice, semantic search, reflection, events, git, sub-agents
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Any

from prompt_toolkit import PromptSession, Application
from prompt_toolkit.layout import Layout, HSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML, FormattedText
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit import print_formatted_text
from prompt_toolkit.output import ColorDepth

from llm import chat_stream, chat, get_client, set_session_provider, get_session_info, list_providers, get_models_for_provider, fetch_models_from_provider
from memory import short_term, long_term, procedural, MemoryEntry, Procedure
from tools import get_tools, execute_tool
from nl_cron import nl_to_cron, add_cron_job, list_cron_jobs

# Feature modules
from reflection import agent_reflect
from subagents import delegate_task, research_parallel
from events import event_listener, monitor_manager, add_event_rule, list_event_rules, list_recent_events
from git_integration import git_auto_commit, git_save_state, git_list_snapshots, git_status as git_status_cmd
from semantic import vector_store, add_to_knowledge

# Conditionally import Termux modules
try:
    from termux_hardware import HARDWARE_TOOL_SCHEMAS, HARDWARE_TOOL_MAP
    HAS_TERMUX = True
except ImportError:
    HAS_TERMUX = False

try:
    from vision import VISION_TOOL_SCHEMAS, VISION_TOOL_MAP
    HAS_VISION = True
except ImportError:
    HAS_VISION = False

try:
    from voice import VOICE_TOOL_SCHEMAS, VOICE_TOOL_MAP
    HAS_VOICE = True
except ImportError:
    HAS_VOICE = False

# ---------------------------------------------------------------------------
# Version info
# ---------------------------------------------------------------------------

APP_VERSION = "1.0.0"
APP_BUILD = "2026.09.02"

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a self-evolving AI assistant running in a terminal on Android (Termux).

You have access to tools that let you search the web, read/write files, execute Python code, 
manage your memory, and interact with an Obsidian vault.

Core behaviors:
- Always think step by step before acting.
- Use tools when needed rather than guessing.
- Save important facts and insights to memory automatically.
- When you notice a repeated workflow, suggest creating a procedure for it.
- Be concise but thorough in your responses.
- You can remember things across sessions via long-term memory.
- For complex questions, consider delegating to sub-agents for parallel research.
- Before giving important answers, reflect on your response for accuracy.
- Auto-commit significant changes to git for version control.

You are autonomous and self-improving. Learn from each interaction.
"""

# ---------------------------------------------------------------------------
# Slash commands registry
# ---------------------------------------------------------------------------

COMMANDS: list[tuple[str, str]] = [
    ("/model",          "Switch model (session-scope)"),
    ("/model list",     "Fetch live models from providers"),
    ("/model reset",    "Reset to auto-detect from .env"),
    ("/memory",         "Review long-term memories"),
    ("/procedures",     "View learned procedures"),
    ("/cron",           "View scheduled cron jobs"),
    ("/events",         "View event rules"),
    ("/recent_events",  "View recent system events"),
    ("/snapshots",      "View git evolution snapshots"),
    ("/save",           "Save agent state to git"),
    ("/voice",          "Toggle voice mode (STT/TTS)"),
    ("/reflect",        "Toggle self-reflection"),
    ("/clear",          "Clear working memory"),
    ("/help",           "Show all commands"),
]

# ---------------------------------------------------------------------------
# Tool setup (same as before)
# ---------------------------------------------------------------------------

ALL_TOOLS = list(get_tools())
ALL_TOOL_MAP: dict[str, Any] = {}

from tools import _tool_map as base_tool_map
ALL_TOOL_MAP.update(base_tool_map)

if HAS_TERMUX:
    ALL_TOOLS.extend(HARDWARE_TOOL_SCHEMAS)
    ALL_TOOL_MAP.update(HARDWARE_TOOL_MAP)
if HAS_VISION:
    ALL_TOOLS.extend(VISION_TOOL_SCHEMAS)
    ALL_TOOL_MAP.update(VISION_TOOL_MAP)
if HAS_VOICE:
    ALL_TOOLS.extend(VOICE_TOOL_SCHEMAS)
    ALL_TOOL_MAP.update(VOICE_TOOL_MAP)

from reflection import REFLECTION_TOOL_SCHEMAS, REFLECTION_TOOL_MAP
from subagents import SUBAGENT_TOOL_SCHEMAS, SUBAGENT_TOOL_MAP
from events import EVENT_TOOL_SCHEMAS, EVENT_TOOL_MAP
from git_integration import GIT_TOOL_SCHEMAS, GIT_TOOL_MAP
from semantic import SEMANTIC_TOOL_SCHEMAS, SEMANTIC_TOOL_MAP

ALL_TOOLS.extend(REFLECTION_TOOL_SCHEMAS + SUBAGENT_TOOL_SCHEMAS + EVENT_TOOL_SCHEMAS + GIT_TOOL_SCHEMAS + SEMANTIC_TOOL_SCHEMAS)
ALL_TOOL_MAP.update(REFLECTION_TOOL_MAP)
ALL_TOOL_MAP.update(SUBAGENT_TOOL_MAP)
ALL_TOOL_MAP.update(EVENT_TOOL_MAP)
ALL_TOOL_MAP.update(GIT_TOOL_MAP)
ALL_TOOL_MAP.update(SEMANTIC_TOOL_MAP)

TOOLSETS = sorted(set(
    name.split("_")[0] if "_" in name else name
    for name in ALL_TOOL_MAP.keys()
))


async def combined_execute_tool(name: str, arguments: str | dict) -> dict[str, Any]:
    """Execute a tool by name using the combined tool map."""
    fn = ALL_TOOL_MAP.get(name)
    if not fn:
        return {"result": "", "error": f"Unknown tool: {name}"}
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
    except json.JSONDecodeError:
        return {"result": "", "error": f"Invalid JSON arguments: {arguments}"}
    try:
        if asyncio.iscoroutinefunction(fn):
            return await fn(**args)
        else:
            return fn(**args)
    except TypeError as e:
        return {"result": "", "error": f"Tool argument error: {e}"}
    except Exception as e:
        return {"result": "", "error": f"Tool execution error: {e}"}


def get_all_tools() -> list[dict[str, Any]]:
    return ALL_TOOLS


# ---------------------------------------------------------------------------
# Slash command completer
# ---------------------------------------------------------------------------

class SlashCompleter(Completer):
    """Autocomplete for slash commands."""

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/"):
            return

        word = text.lower()
        for cmd, desc in COMMANDS:
            if cmd.startswith(word):
                yield Completion(
                    cmd,
                    start_position=-len(text),
                    display_meta=desc,
                )


# ---------------------------------------------------------------------------
# Purple theme style
# ---------------------------------------------------------------------------

STYLE = Style.from_dict({
    "prompt": "ansimagenta bold",
    "command": "ansibrightmagenta",
    "output": "ansimagenta",
    "system": "ansibrightblack",
    "error": "ansired bold",
    "success": "ansigreen",
    "thinking": "ansimagenta",
    "tool": "ansibrightblack",
    "header": "ansibrightmagenta bold",
    "model": "ansibrightmagenta",
    "provider": "ansimagenta",
    "autocomplete": "ansimagenta",
    "autocomplete.description": "ansibrightblack",
    "autocomplete.selected": "ansibrightmagenta bold",
})


# ---------------------------------------------------------------------------
# TUI Application
# ---------------------------------------------------------------------------

class PrivyaTUI:
    """Self-evolving AI agent TUI using prompt_toolkit."""

    def __init__(self):
        self.current_provider = "unknown"
        self.current_model = "unknown"
        self.reflection_enabled = True
        self.voice_mode = False
        self.context_tokens_used = 0
        self.context_window = 131072
        self.last_user_msg = ""
        self.last_response_time = 0.0
        self.output_lines: list[str] = []

        # Try to resolve provider
        try:
            _, provider, model = get_client()
            self.current_provider = provider
            self.current_model = model
            self.context_window = self._detect_context_window(model)
        except Exception:
            self.current_provider = "none"
            self.current_model = "none"

    def _detect_context_window(self, model: str) -> int:
        windows = {
            "llama-3.3-70b": 131072, "llama-3.1-8b": 131072,
            "llama-3.1-70b": 131072, "mixtral": 32768,
            "gemma2": 8192, "claude": 200000, "gpt-4o": 128000,
            "gemini": 1048576, "deepseek": 65536, "mistral": 32768,
            "default": 131072,
        }
        model_lower = model.lower()
        for key, size in windows.items():
            if key in model_lower:
                return size
        return windows["default"]

    def _setup_keybindings(self):
        pass  # Handled by prompt_toolkit's built-in scrolling

    def _write(self, text: str, style: str = "") -> None:
        """Write to output (printed to terminal)."""
        self.output_lines.append(text)
        # Use prompt_toolkit's print to terminal
        from prompt_toolkit import print_formatted_text
        from prompt_toolkit.formatted_text import FormattedText
        print_formatted_text(FormattedText([('', text)]), style=STYLE)

    def _write_rich(self, *parts: tuple[str, str]) -> None:
        """Write styled text to output."""
        text = "".join(p[0] for p in parts)
        self._write(text)

    def _clear_output(self) -> None:
        """Clear output."""
        self.output_lines.clear()
        import os as _os
        _os.system('cls' if _os.name == 'nt' else 'clear')

    def _get_prompt(self) -> HTML:
        """Get the input prompt."""
        model_short = self.current_model
        if len(model_short) > 25:
            model_short = model_short[:22] + "..."
        pct = ""
        if self.context_tokens_used > 0 and self.context_window > 0:
            p = min(100, int(self.context_tokens_used / self.context_window * 100))
            pct = f" {p}%"
        return HTML(
            f'<style name="prompt">  $ </style>'
            f'<style name="model">{model_short}</style>'
            f'<style name="provider">{pct} > </style>'
        )

    def _estimate_tokens(self, messages: list[dict]) -> int:
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if content:
                total += len(content) // 4
        return total

    # -------------------------------------------------------------------
    # Command handlers
    # -------------------------------------------------------------------

    async def handle_command(self, cmd: str) -> None:
        """Handle slash commands."""
        parts = cmd.split(maxsplit=1)
        command = parts[0].lower()

        if command == "/help":
            await self._handle_help()
        elif command == "/model":
            arg = parts[1].strip() if len(parts) > 1 else ""
            if arg and arg not in ("list", "reset", "status"):
                await self._switch_model(arg)
            elif arg == "list":
                await self._handle_model_list()
            elif arg == "reset":
                result = set_session_provider(None)
                self._write(f"  🔄 {result['message']}")
                self._refresh_provider()
            elif arg == "status":
                await self._handle_model_status()
            else:
                await self._show_model_picker()
        elif command == "/memory":
            memories = long_term.recent(10)
            if not memories:
                self._write("  No memories stored yet.")
            else:
                self._write("  ✦ Long-term Memories:")
                for i, m in enumerate(memories, 1):
                    self._write(f"    {i}. {m.text[:120]}")
        elif command == "/procedures":
            procs = procedural.all_procedures()
            if not procs:
                self._write("  No procedures learned yet.")
            else:
                self._write("  ✦ Learned Procedures:")
                for p in procs:
                    self._write(f"    • {p.name}: {p.description}")
        elif command == "/cron":
            jobs = list_cron_jobs()
            if not jobs:
                self._write("  No cron jobs scheduled.")
            else:
                self._write("  ✦ Scheduled Jobs:")
                for j in jobs:
                    icon = "●" if j.get("enabled") else "○"
                    self._write(f"    {icon} {j['name']}: {j['cron']} → {j['command']}")
        elif command == "/events":
            result = await list_event_rules()
            self._write(f"  ✦ Event Rules:\n{result.get('result', 'None')}")
        elif command == "/recent_events":
            result = await list_recent_events()
            self._write(f"  ✦ Recent Events:\n{result.get('result', 'None')}")
        elif command == "/snapshots":
            result = await git_list_snapshots()
            self._write(f"  ✦ Git Snapshots:\n{result.get('result', 'None')}")
        elif command == "/save":
            self._write("  Saving agent state...")
            result = await git_save_state(f"manual-save-{datetime.now().strftime('%H%M')}")
            self._write(f"  {result.get('result', result.get('error', 'Unknown'))}")
        elif command == "/voice":
            self.voice_mode = not self.voice_mode
            status = "enabled" if self.voice_mode else "disabled"
            self._write(f"  🎤 Voice mode {status}")
        elif command == "/reflect":
            self.reflection_enabled = not self.reflection_enabled
            status = "enabled" if self.reflection_enabled else "disabled"
            self._write(f"  🔍 Reflection {status}")
        elif command == "/clear":
            short_term.clear()
            self.context_tokens_used = 0
            self._clear_output()
            self._write("  Working memory cleared.")
        else:
            self._write(f"  Unknown command: {command}. Type /help for available commands.")

    async def _handle_help(self) -> None:
        self._write("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self._write("  ✦ PRIVYA COMMANDS")
        self._write("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        for cmd, desc in COMMANDS:
            self._write(f"  {cmd:<18} – {desc}")
        self._write("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self._write("  Just type naturally to chat with the agent!")
        self._write("  Type / to see autocomplete suggestions.")

    async def _handle_model_status(self) -> None:
        info = get_session_info()
        providers = list_providers()

        self._write("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self._write("  ✦ Provider & Model Status")
        self._write("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        if info["provider"]:
            self._write(f"    Active: {info['display']} / {info['model']}")
        else:
            try:
                _, prov, model = get_client()
                self._write(f"    Auto-detected: {prov}/{model}")
            except Exception:
                self._write("    No provider configured")

        self._write(f"    Context window: {self.context_window:,} tokens")
        self._write(f"    Used: {self.context_tokens_used:,} ({min(100, int(self.context_tokens_used/max(1,self.context_window)*100))}%)")

        self._write("")
        for p in providers:
            icon = "●" if p["available"] else "○"
            active = " ← ACTIVE" if p["session_active"] else ""
            self._write(f"    {icon} {p['id']:<12}{p['display_name']}{active}")

        self._write("")
        self._write("  Usage:")
        self._write("    /model                – Interactive picker (arrow keys + enter)")
        self._write("    /model groq           – Switch to Groq")
        self._write("    /model groq mixtral   – Switch provider + model")
        self._write("    /model reset          – Reset to auto-detect")
        self._write("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    async def _handle_model_list(self) -> None:
        providers = list_providers()
        self._write("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self._write("  ✦ All Providers & Models (live)")
        self._write("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        for p in providers:
            icon = "●" if p["available"] else "○"
            active = " ← ACTIVE" if p["session_active"] else ""
            self._write(f"\n  {icon} {p['display_name']}{active}")
            if p["available"]:
                self._write("    ⏳ Fetching live models...")
                try:
                    live_models = await fetch_models_from_provider(p["id"])
                except Exception as e:
                    live_models = p["models"]
                    self._write(f"    ⚠️ API error: {e}")
                if not live_models:
                    live_models = p["models"]
                shown = live_models[:50]
                remaining = len(live_models) - 50
                for m in shown:
                    desc = m.get("description", "")
                    self._write(f"    • {m['id']}")
                    if desc:
                        self._write(f"      {desc}")
                if remaining > 0:
                    self._write(f"    ... and {remaining} more")
                self._write(f"    ({len(live_models)} total)")
            else:
                self._write(f"    (Add {p['key_env']} to .env to enable)")
        self._write("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    async def _switch_model(self, args: str) -> None:
        parts = args.split()
        provider = parts[0]
        model = parts[1] if len(parts) > 1 else None
        result = set_session_provider(provider, model)
        if "error" in result:
            self._write(f"  ❌ {result['error']}")
        else:
            self._write(f"  ✅ {result['message']}")
            self._refresh_provider()

    def _refresh_provider(self) -> None:
        try:
            info = get_session_info()
            if info["provider"]:
                self.current_provider = info["display"]
                self.current_model = info["model"]
            else:
                _, prov, model = get_client()
                self.current_provider = prov
                self.current_model = model
            self.context_window = self._detect_context_window(self.current_model)
        except Exception:
            self.current_provider = "none"
            self.current_model = "none"

    async def _show_model_picker(self) -> None:
        """Interactive model picker with arrow key navigation."""
        providers = list_providers()
        available = [p for p in providers if p["available"]]

        if not available:
            self._write("  ❌ No providers configured. Add an API key to .env")
            return

        self._write("  ⏳ Fetching live models from providers...")

        all_models: list[tuple[str, str, str, str, str]] = []
        for p in available:
            try:
                live_models = await fetch_models_from_provider(p["id"])
            except Exception:
                live_models = p["models"]
            if not live_models:
                live_models = p["models"]
            for m in live_models:
                all_models.append((p["id"], m["id"], m["id"], m.get("description", ""), f"[{p['id']}]"))

        if not all_models:
            self._write("  ❌ No models found.")
            return

        # Show numbered list for selection
        self._write("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self._write(f"  ✦ Model Picker – {len(all_models)} available")
        self._write("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self._write("  Type a number to select, or 'c' to cancel:")
        self._write("")

        current_provider = None
        idx = 1
        model_index: dict[int, tuple[str, str]] = {}
        for provider_id, model_id, display, desc, provider_tag in all_models:
            if provider_id != current_provider:
                self._write(f"  ── {provider_tag} ──")
                current_provider = provider_id
            desc_str = f"  {desc}" if desc else ""
            self._write(f"    {idx:>3}) {display}{desc_str}")
            model_index[idx] = (provider_id, model_id)
            idx += 1

        self._write("")

        # Get selection from user
        try:
            session = PromptSession(style=STYLE)
            choice = await session.prompt_async("  Select model #: ")
            choice = choice.strip()
            if choice.lower() == "c" or choice == "":
                self._write("  Cancelled.")
                return
            num = int(choice)
            if num in model_index:
                provider_id, model_id = model_index[num]
                result = set_session_provider(provider_id, model_id)
                if "error" in result:
                    self._write(f"  ❌ {result['error']}")
                else:
                    self._write(f"  ✅ {result['message']}")
                    self._refresh_provider()
            else:
                self._write(f"  ❌ Invalid choice: {num}")
        except (ValueError, EOFError, KeyboardInterrupt):
            self._write("  Cancelled.")

    # -------------------------------------------------------------------
    # Agent loop
    # -------------------------------------------------------------------

    async def agent_loop(self, user_text: str) -> None:
        """Run the agent with tool calling loop."""
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *short_term.snapshot(),
        ]

        self.context_tokens_used = self._estimate_tokens(messages)
        start_time = asyncio.get_event_loop().time()

        for iteration in range(5):
            self._write("  🧠 thinking...")

            try:
                response = await chat(messages, tools=get_all_tools(), temperature=0.7)
            except Exception as e:
                self._write(f"  ⚠️ LLM error: {e}")
                return

            elapsed = asyncio.get_event_loop().time() - start_time
            self.last_response_time = elapsed

            messages.append(response)
            self.context_tokens_used = self._estimate_tokens(messages)

            tool_calls = response.get("tool_calls")
            if not tool_calls:
                content = response.get("content", "")
                if content:
                    # Thinking/reasoning block
                    thinking = response.get("thinking", "") or response.get("reasoning_content", "")
                    if thinking:
                        self._write("  ┌─ Reasoning " + "─" * 40)
                        for line in thinking.strip().split("\n"):
                            self._write(f"  │ {line}")
                        self._write("  └" + "─" * 53)

                    # Reflection
                    if self.reflection_enabled:
                        self._write("  🔍 Reflecting...")
                        reflected = await agent_reflect(
                            user_query=user_text,
                            initial_response=content,
                            enabled=True,
                            max_rounds=1,
                        )
                        if reflected["reflected"]:
                            content = reflected["response"]
                            details = reflected["details"]
                            self._write(f"  ✅ Improved after {details['rounds']} round(s) ({details['verdict']})")

                    short_term.add({"role": "assistant", "content": content})

                    if len(content) > 100:
                        asyncio.create_task(self._auto_save(content))

                    # Display response in box
                    self._write("  ┌─ ✦ Privya " + "─" * 43)
                    for line in content.split("\n"):
                        self._write(f"  │ {line}")
                    self._write("  └" + "─" * 53)

                return

            # Execute tools
            for tc in tool_calls:
                func_name = tc["function"]["name"]
                func_args = tc["function"]["arguments"]
                self._write(f"  🔧 {func_name}({func_args[:80]}...)")
                result = await combined_execute_tool(func_name, func_args)
                result_preview = result.get("result", result.get("error", ""))
                if isinstance(result_preview, dict):
                    result_preview = json.dumps(result_preview)[:200]
                if result_preview:
                    preview = str(result_preview)[:200]
                    self._write(f"  📎 {preview}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False, default=str)[:4000],
                })
                self.context_tokens_used = self._estimate_tokens(messages)

        self._write("  ⚠️ Max tool iterations reached.")

    async def _auto_save(self, content: str) -> None:
        if any(kw in content.lower() for kw in ["important", "remember", "note:", "key insight", "conclusion"]):
            long_term.add(MemoryEntry(text=content[:500], source="auto_save", importance=0.6))
        try:
            await add_to_knowledge(content[:1000], source="conversation")
        except Exception:
            pass

    # -------------------------------------------------------------------
    # Main run loop
    # -------------------------------------------------------------------

    async def run(self) -> None:
        """Main TUI run loop."""
        # Show welcome
        self._write("  ✦ PRIVYA – AI Agent Framework")
        self._write(f"  Agent v{APP_VERSION} ({APP_BUILD})")
        self._write("")
        self._write(f"  ● {self.current_model} · {len(ALL_TOOLS)} tools · provider: {self.current_provider}")
        self._write("")
        self._write("  Welcome to Privya Agent! Type your message or /help for commands.")
        self._write("  Type / to see autocomplete suggestions.")
        self._write("  ↑↓ scroll output  ·  /model opens interactive model picker.")
        self._write("")

        session = PromptSession(
            completer=SlashCompleter(),
            complete_while_typing=True,
            style=STYLE,
        )

        while True:
            try:
                model_short = self.current_model
                if len(model_short) > 25:
                    model_short = model_short[:22] + "..."
                pct = ""
                if self.context_tokens_used > 0 and self.context_window > 0:
                    p = min(100, int(self.context_tokens_used / self.context_window * 100))
                    pct = f" {p}%"
                prompt_text = f"  $ {model_short}{pct} > "

                user_text = await session.prompt_async(prompt_text)
                user_text = user_text.strip()

                if not user_text:
                    continue

                self.last_user_msg = user_text
                self._write(f"  ✦ {user_text}")

                if user_text.startswith("/"):
                    await self.handle_command(user_text)
                else:
                    short_term.add({"role": "user", "content": user_text})
                    await self.agent_loop(user_text)

            except (KeyboardInterrupt, EOFError):
                self._write("\n  Goodbye! ✦")
                break


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tui = PrivyaTUI()
    asyncio.run(tui.run())
