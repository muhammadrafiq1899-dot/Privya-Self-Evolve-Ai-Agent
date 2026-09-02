#!/usr/bin/env python3
"""
agent.py – Self-evolving AI agent with Rich + prompt_toolkit TUI.

Launch: python agent.py

Beautiful terminal UI with:
  - Rich panels, tables, colored output
  - prompt_toolkit for input with autocomplete
  - Scrollable output (terminal scrollback)
  - Works perfectly on Termux Android
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich import box
from rich.tree import Tree

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML

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
# Constants
# ---------------------------------------------------------------------------

APP_VERSION = "1.0.0"
APP_BUILD = "2026.09.02"
console = Console()

SYSTEM_PROMPT = """You are a self-evolving AI assistant running in a terminal on Android (Termux).
You have access to tools that let you search the web, read/write files, execute Python code, 
manage your memory, and interact with an Obsidian vault.
Core behaviors:
- Always think step by step before acting.
- Use tools when needed rather than guessing.
- Save important facts and insights to memory automatically.
- Be concise but thorough in your responses.
- You can remember things across sessions via long-term memory.
You are autonomous and self-improving. Learn from each interaction."""

COMMANDS = [
    ("/model", "Switch model"), ("/model list", "Live models"),
    ("/model reset", "Auto-detect"), ("/memory", "Memories"),
    ("/procedures", "Procedures"), ("/cron", "Cron jobs"),
    ("/events", "Event rules"), ("/recent_events", "Recent events"),
    ("/snapshots", "Git snapshots"), ("/save", "Save state"),
    ("/voice", "Voice mode"), ("/reflect", "Reflection"),
    ("/clear", "Clear screen"), ("/help", "All commands"),
]

# ---------------------------------------------------------------------------
# Tool setup
# ---------------------------------------------------------------------------

ALL_TOOLS = list(get_tools())
ALL_TOOL_MAP: dict[str, Any] = {}
from tools import _tool_map as base_tool_map
ALL_TOOL_MAP.update(base_tool_map)
if HAS_TERMUX:
    ALL_TOOLS.extend(HARDWARE_TOOL_SCHEMAS); ALL_TOOL_MAP.update(HARDWARE_TOOL_MAP)
if HAS_VISION:
    ALL_TOOLS.extend(VISION_TOOL_SCHEMAS); ALL_TOOL_MAP.update(VISION_TOOL_MAP)
if HAS_VOICE:
    ALL_TOOLS.extend(VOICE_TOOL_SCHEMAS); ALL_TOOL_MAP.update(VOICE_TOOL_MAP)
from reflection import REFLECTION_TOOL_SCHEMAS, REFLECTION_TOOL_MAP
from subagents import SUBAGENT_TOOL_SCHEMAS, SUBAGENT_TOOL_MAP
from events import EVENT_TOOL_SCHEMAS, EVENT_TOOL_MAP
from git_integration import GIT_TOOL_SCHEMAS, GIT_TOOL_MAP
from semantic import SEMANTIC_TOOL_SCHEMAS, SEMANTIC_TOOL_MAP
ALL_TOOLS.extend(REFLECTION_TOOL_SCHEMAS + SUBAGENT_TOOL_SCHEMAS + EVENT_TOOL_SCHEMAS + GIT_TOOL_SCHEMAS + SEMANTIC_TOOL_SCHEMAS)
ALL_TOOL_MAP.update(REFLECTION_TOOL_MAP); ALL_TOOL_MAP.update(SUBAGENT_TOOL_MAP)
ALL_TOOL_MAP.update(EVENT_TOOL_MAP); ALL_TOOL_MAP.update(GIT_TOOL_MAP); ALL_TOOL_MAP.update(SEMANTIC_TOOL_MAP)
TOOLSETS = sorted(set(name.split("_")[0] if "_" in name else name for name in ALL_TOOL_MAP.keys()))

async def combined_execute_tool(name: str, arguments: str | dict) -> dict[str, Any]:
    fn = ALL_TOOL_MAP.get(name)
    if not fn: return {"result": "", "error": f"Unknown tool: {name}"}
    try: args = json.loads(arguments) if isinstance(arguments, str) else arguments
    except json.JSONDecodeError: return {"result": "", "error": f"Invalid JSON: {arguments}"}
    try:
        if asyncio.iscoroutinefunction(fn): return await fn(**args)
        else: return fn(**args)
    except TypeError as e: return {"result": "", "error": f"Arg error: {e}"}
    except Exception as e: return {"result": "", "error": f"Error: {e}"}

def get_all_tools(): return ALL_TOOLS

# ---------------------------------------------------------------------------
# Slash command completer
# ---------------------------------------------------------------------------

class SlashCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/"): return
        for cmd, desc in COMMANDS:
            if cmd.startswith(text.lower()):
                yield Completion(cmd, start_position=-len(text), display_meta=desc)

# ---------------------------------------------------------------------------
# Rich TUI
# ---------------------------------------------------------------------------

class PrivyaTUI:
    def __init__(self):
        self.current_provider = "unknown"
        self.current_model = "unknown"
        self.reflection_enabled = True
        self.voice_mode = False
        self.context_tokens_used = 0
        self.context_window = 131072
        self.last_user_msg = ""
        self.last_response_time = 0.0
        self.session_count = 0

        try:
            _, provider, model = get_client()
            self.current_provider = provider
            self.current_model = model
            self.context_window = self._detect_context_window(model)
        except Exception:
            self.current_provider = "none"
            self.current_model = "none"

    def _detect_context_window(self, model: str) -> int:
        windows = {"llama": 131072, "mixtral": 32768, "gemma": 8192, "claude": 200000,
                    "gpt-4o": 128000, "gemini": 1048576, "deepseek": 65536, "mistral": 32768, "default": 131072}
        ml = model.lower()
        for k, v in windows.items():
            if k in ml: return v
        return windows["default"]

    def _estimate_tokens(self, messages: list[dict]) -> int:
        return sum(len(m.get("content", "")) // 4 for m in messages)

    def _get_prompt(self) -> HTML:
        m = self.current_model
        if len(m) > 25: m = m[:22] + "..."
        pct = ""
        if self.context_tokens_used > 0 and self.context_window > 0:
            p = min(100, int(self.context_tokens_used / self.context_window * 100))
            pct = f" {p}%"
        return HTML(f'<style name="model">{m}{pct}</style> <style name="prompt">>&#8288;</style> ')

    # -------------------------------------------------------------------
    # Rich output helpers
    # -------------------------------------------------------------------

    def _show_banner(self):
        """Show the startup banner."""
        banner = Table(show_header=False, box=None, padding=(0, 1))
        banner.add_column("key", style="bold green")
        banner.add_column("val", style="bright_white")
        banner.add_row("✦", Text("PRIVYA – AI Agent Framework", style="bold bright_white"))
        banner.add_row("", Text(f"v{APP_VERSION} ({APP_BUILD})", style="dim white"))
        console.print(Panel(banner, border_style="bright_green", box=box.ROUNDED))

        info = Table(show_header=False, box=None, padding=(0, 1))
        info.add_column("key", style="dim green")
        info.add_column("val", style="bright_white")
        info.add_row("● Model", Text(self.current_model, style="bold bright_white"))
        info.add_row("● Tools", Text(f"{len(ALL_TOOLS)} ({', '.join(TOOLSETS[:8])}...)", style="green"))
        info.add_row("● Provider", Text(self.current_provider, style="bright_white"))
        console.print(info)
        console.print()

        tip = Text()
        tip.append("  ✦ ", style="bold bright_green")
        tip.append("Welcome! ", style="bright_white")
        tip.append("Type a message or ", style="dim white")
        tip.append("/help", style="bold bright_green")
        tip.append(" for commands. ", style="dim white")
        tip.append("/model", style="bold bright_green")
        tip.append(" to pick a model.", style="dim white")
        console.print(tip)
        console.print()

    def _show_help(self):
        table = Table(title="✦ Commands", box=box.ROUNDED, border_style="bright_green", title_style="bold bright_white")
        table.add_column("Command", style="bold bright_green", no_wrap=True)
        table.add_column("Description", style="bright_white")
        for cmd, desc in COMMANDS:
            table.add_row(cmd, desc)
        console.print(table)

    def _show_model_status(self):
        info = get_session_info()
        providers = list_providers()

        table = Table(title="✦ Provider Status", box=box.ROUNDED, border_style="bright_green", title_style="bold bright_white")
        table.add_column("Provider", style="bold bright_green")
        table.add_column("Status", style="bright_white")
        table.add_column("Model", style="bright_white")

        for p in providers:
            icon = "●" if p["available"] else "○"
            active = " ← ACTIVE" if p["session_active"] else ""
            status = f"{icon} {'Available' if p['available'] else 'No key'}{active}"
            model = p["default_model"] if p["available"] else f"(add {p['key_env']})"
            table.add_row(p["display_name"], status, model)

        console.print(table)
        pct = min(100, int(self.context_tokens_used / max(1, self.context_window) * 100))
        console.print(f"  Context: {self.context_tokens_used:,} / {self.context_window:,} tokens ({pct}%)", style="dim white")
        console.print()

    async def _show_model_picker(self):
        """Interactive model picker with numbered selection."""
        providers = list_providers()
        available = [p for p in providers if p["available"]]

        if not available:
            console.print(Panel("No providers configured. Add an API key to .env", border_style="red", box=box.ROUNDED))
            return

        console.print("[dim green]  ⏳ Fetching live models...[/]")

        all_models: list[tuple[str, str, str, str]] = []
        for p in available:
            try:
                live_models = await fetch_models_from_provider(p["id"])
            except Exception:
                live_models = p["models"]
            if not live_models:
                live_models = p["models"]
            for m in live_models:
                all_models.append((p["id"], m["id"], m.get("description", ""), p["display_name"]))

        if not all_models:
            console.print("[red]  No models found.[/]")
            return

        # Show as a Rich Table with numbers
        table = Table(
            title=f"✦ Model Picker – {len(all_models)} available",
            box=box.ROUNDED, border_style="bright_green",
            title_style="bold bright_white",
            show_lines=False,
        )
        table.add_column("#", style="bold bright_green", width=4, justify="right")
        table.add_column("Model", style="bright_white")
        table.add_column("Description", style="dim white")

        current_provider = None
        idx = 1
        model_map: dict[int, tuple[str, str]] = {}
        for provider_id, model_id, desc, prov_name in all_models:
            if provider_id != current_provider:
                table.add_row("", f"[bold bright_green]── {prov_name} ──[/]", "")
                current_provider = provider_id
            table.add_row(str(idx), model_id, desc[:50] if desc else "")
            model_map[idx] = (provider_id, model_id)
            idx += 1

        console.print(table)
        console.print()

        # Get selection
        session = PromptSession(style=Style.from_dict({"model": "ansigreen bold", "prompt": "ansiwhite bold"}))
        try:
            choice = await session.prompt_async("  Select model # (or 'c' to cancel): ")
            choice = choice.strip()
            if choice.lower() in ("c", ""):
                console.print("[dim green]  Cancelled.[/]")
                return
            num = int(choice)
            if num in model_map:
                provider_id, model_id = model_map[num]
                result = set_session_provider(provider_id, model_id)
                if "error" in result:
                    console.print(f"[red]  ❌ {result['error']}[/]")
                else:
                    console.print(f"[bright_green]  ✅ {result['message']}[/]")
                    self._refresh_provider()
            else:
                console.print(f"[red]  Invalid choice: {num}[/]")
        except (ValueError, EOFError, KeyboardInterrupt):
            console.print("[dim green]  Cancelled.[/]")

    async def _show_model_list(self):
        providers = list_providers()
        for p in providers:
            icon = "●" if p["available"] else "○"
            active = " ← ACTIVE" if p["session_active"] else ""
            console.print(f"\n[bold bright_green]  {icon} {p['display_name']}{active}[/]")
            if p["available"]:
                console.print("[dim green]    ⏳ Fetching live models...[/]")
                try:
                    live_models = await fetch_models_from_provider(p["id"])
                except Exception as e:
                    live_models = p["models"]
                    console.print(f"[yellow]    ⚠️ {e}[/]")
                if not live_models:
                    live_models = p["models"]
                table = Table(box=None, show_header=False, padding=(0, 1))
                table.add_column("model", style="bright_white")
                table.add_column("desc", style="dim white")
                for m in live_models[:40]:
                    table.add_row(f"  • {m['id']}", m.get("description", "")[:60])
                console.print(table)
                if len(live_models) > 40:
                    console.print(f"[dim green]    ... and {len(live_models) - 40} more ({len(live_models)} total)[/]")
            else:
                console.print(f"[dim green]    (Add {p['key_env']} to .env)[/]")

    def _refresh_provider(self):
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

    # -------------------------------------------------------------------
    # Agent loop
    # -------------------------------------------------------------------

    async def agent_loop(self, user_text: str):
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *short_term.snapshot()]
        self.context_tokens_used = self._estimate_tokens(messages)
        start_time = asyncio.get_event_loop().time()

        console.print("[bright_green]  🧠 thinking...[/]")

        for iteration in range(20):
            try:
                response = await chat(messages, tools=get_all_tools(), temperature=0.7)
            except Exception as e:
                console.print(f"[red]  ⚠️ LLM error: {e}[/]")
                return

            elapsed = asyncio.get_event_loop().time() - start_time
            self.last_response_time = elapsed
            messages.append(response)
            self.context_tokens_used = self._estimate_tokens(messages)

            tool_calls = response.get("tool_calls")
            if not tool_calls:
                content = response.get("content", "")
                if content:
                    # Thinking block
                    thinking = response.get("thinking", "") or response.get("reasoning_content", "")
                    if thinking:
                        console.print(Panel(thinking.strip(), title="🔍 Reasoning", border_style="dim green", box=box.ROUNDED))

                    # Reflection
                    if self.reflection_enabled:
                        console.print("[bright_green]  🔍 Reflecting...[/]")
                        try:
                            reflected = await agent_reflect(user_query=user_text, initial_response=content, enabled=True, max_rounds=1)
                            if reflected["reflected"]:
                                content = reflected["response"]
                                details = reflected["details"]
                                console.print(f"[dim green]  ✅ Improved ({details['verdict']})[/]")
                        except Exception as e:
                            console.print(f"[yellow]  ⚠️ Reflection failed: {e}[/]")

                    short_term.add({"role": "assistant", "content": content})
                    if len(content) > 100:
                        asyncio.create_task(self._auto_save(content))

                    # Display response in a panel
                    console.print(Panel(content, title="✦ Privya", border_style="bright_green", box=box.ROUNDED))
                else:
                    console.print("[yellow]  ⚠️ Empty response from LLM[/]")
                return

            # Execute tools
            for tc in tool_calls:
                func_name = tc["function"]["name"]
                func_args = tc["function"]["arguments"]
                console.print(f"[bright_green]  🔧 {func_name}[/]")
                result = await combined_execute_tool(func_name, func_args)
                preview = result.get("result", result.get("error", ""))
                if isinstance(preview, dict): preview = json.dumps(preview)[:150]
                if preview:
                    console.print(f"[dim green]  📎 {str(preview)[:150]}[/]")
                messages.append({"role": "tool", "tool_call_id": tc["id"],
                                "content": json.dumps(result, ensure_ascii=False, default=str)[:4000]})
                self.context_tokens_used = self._estimate_tokens(messages)

        console.print("[yellow]  ⚠️ Max iterations reached (20). The task may need to be split into smaller steps.[/]")

    async def _auto_save(self, content: str):
        if any(kw in content.lower() for kw in ["important", "remember", "note:", "key insight"]):
            long_term.add(MemoryEntry(text=content[:500], source="auto_save", importance=0.6))
        try:
            await add_to_knowledge(content[:1000], source="conversation")
        except Exception:
            pass

    # -------------------------------------------------------------------
    # Command handler
    # -------------------------------------------------------------------

    async def handle_command(self, cmd: str):
        parts = cmd.split(maxsplit=1)
        command = parts[0].lower()

        if command == "/help":
            self._show_help()
        elif command == "/model":
            arg = parts[1].strip() if len(parts) > 1 else ""
            if arg and arg not in ("list", "reset", "status"):
                await self._switch_model(arg)
            elif arg == "list":
                await self._show_model_list()
            elif arg == "reset":
                result = set_session_provider(None)
                console.print(f"[green]  🔄 {result['message']}[/]")
                self._refresh_provider()
            elif arg == "status":
                self._show_model_status()
            else:
                await self._show_model_picker()
        elif command == "/memory":
            memories = long_term.recent(10)
            if not memories:
                console.print("[dim green]  No memories yet.[/]")
            else:
                table = Table(title="🧠 Memories", box=box.ROUNDED, border_style="bright_green")
                table.add_column("#", style="bold bright_green", width=3)
                table.add_column("Content", style="bright_white")
                for i, m in enumerate(memories, 1):
                    table.add_row(str(i), m.text[:120])
                console.print(table)
        elif command == "/procedures":
            procs = procedural.all_procedures()
            if not procs:
                console.print("[dim green]  No procedures yet.[/]")
            else:
                for p in procs:
                    console.print(f"[bright_green]  • {p.name}:[/] {p.description}")
        elif command == "/cron":
            jobs = list_cron_jobs()
            if not jobs:
                console.print("[dim green]  No cron jobs.[/]")
            else:
                for j in jobs:
                    icon = "●" if j.get("enabled") else "○"
                    console.print(f"[bright_green]  {icon} {j['name']}:[/] {j['cron']} → {j['command']}")
        elif command == "/events":
            result = await list_event_rules()
            console.print(f"[bright_green]  ⚡ Events:[/]\n{result.get('result', 'None')}")
        elif command == "/recent_events":
            result = await list_recent_events()
            console.print(f"[bright_green]  📊 Recent:[/]\n{result.get('result', 'None')}")
        elif command == "/snapshots":
            result = await git_list_snapshots()
            console.print(f"[bright_green]  📦 Snapshots:[/]\n{result.get('result', 'None')}")
        elif command == "/save":
            console.print("[dim green]  Saving...[/]")
            result = await git_save_state(f"save-{datetime.now().strftime('%H%M')}")
            console.print(f"[bright_green]  ✅ {result.get('result', result.get('error', 'Done'))}[/]")
        elif command == "/voice":
            self.voice_mode = not self.voice_mode
            console.print(f"[bright_green]  🎤 Voice {'enabled' if self.voice_mode else 'disabled'}[/]")
        elif command == "/reflect":
            self.reflection_enabled = not self.reflection_enabled
            console.print(f"[bright_green]  🔍 Reflection {'enabled' if self.reflection_enabled else 'disabled'}[/]")
        elif command == "/clear":
            os.system('cls' if os.name == 'nt' else 'clear')
            short_term.clear()
            self.context_tokens_used = 0
            self._show_banner()
        else:
            console.print(f"[red]  Unknown: {command}. Type /help[/]")

    async def _switch_model(self, args: str):
        parts = args.split()
        provider = parts[0]
        model = parts[1] if len(parts) > 1 else None
        result = set_session_provider(provider, model)
        if "error" in result:
            console.print(f"[red]  ❌ {result['error']}[/]")
        else:
            console.print(f"[bright_green]  ✅ {result['message']}[/]")
            self._refresh_provider()

    # -------------------------------------------------------------------
    # Main loop
    # -------------------------------------------------------------------

    async def run(self):
        self._show_banner()
        session = PromptSession(
            completer=SlashCompleter(),
            complete_while_typing=True,
            style=Style.from_dict({"model": "ansigreen bold", "prompt": "ansiwhite bold"}),
        )

        while True:
            try:
                prompt = self._get_prompt()
                user_text = await session.prompt_async(prompt)
                user_text = user_text.strip()
                if not user_text:
                    continue

                self.last_user_msg = user_text
                console.print(f"[bright_green]  ✦[/] {user_text}")

                if user_text.startswith("/"):
                    await self.handle_command(user_text)
                else:
                    short_term.add({"role": "user", "content": user_text})
                    await self.agent_loop(user_text)

            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim green]  Goodbye! ✦[/]")
                break


if __name__ == "__main__":
    tui = PrivyaTUI()
    asyncio.run(tui.run())
