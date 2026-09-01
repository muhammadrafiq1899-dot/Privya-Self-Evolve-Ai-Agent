#!/usr/bin/env python3
"""
agent.py – Self-evolving AI agent with Textual TUI.

Launch: python agent.py

Features:
  - Multi-provider LLM (Groq / OpenRouter / Gemini / Together)
  - Tool calling with sandboxed execution
  - Short-term, long-term, and procedural memory
  - Web search, file I/O, Python/shell execution
  - Natural language scheduling
  - Obsidian vault integration
  - ✨ NEW: Hardware access (Termux:API)
  - ✨ NEW: Vision & multimodal (image analysis)
  - ✨ NEW: Voice I/O (STT/TTS)
  - ✨ NEW: Semantic vector search (RAG)
  - ✨ NEW: Reflection & self-correction
  - ✨ NEW: Event-driven proactivity
  - ✨ NEW: Git self-versioning
  - ✨ NEW: Sub-agent delegation
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from typing import Any, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal, ScrollableContainer
from textual.widgets import (
    Header,
    Footer,
    Static,
    Input,
    RichLog,
    Label,
)
from textual.reactive import reactive
from rich.text import Text

from llm import chat_stream, chat, get_client, set_session_provider, get_session_info, list_providers, get_models_for_provider
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
# Combine all tool schemas and maps
# ---------------------------------------------------------------------------

ALL_TOOLS = list(get_tools())
ALL_TOOL_MAP: dict[str, Any] = {}

# Import base tool map
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

# Add feature tool schemas
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

# Override execute_tool to use our combined map
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
# Textual TUI Application
# ---------------------------------------------------------------------------

class AgentTUI(App):
    """Self-evolving AI agent terminal interface."""

    TITLE = "🤖 Self-Evolving AI Agent"
    SUB_TITLE = "Multi-feature AI with memory, vision, voice & more"

    CSS = """
    Screen {
        layout: vertical;
    }
    #chat-log {
        height: 1fr;
        margin: 0 1;
        border: solid $primary;
        padding: 1;
    }
    #input-bar {
        height: auto;
        min-height: 3;
        padding: 1;
    }
    #input-bar Input {
        width: 1fr;
    }
    #status-bar {
        height: 1;
        dock: bottom;
        padding: 0 1;
        background: $accent-darken-2;
        color: $text;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("ctrl+l", "clear_log", "Clear", show=True),
        Binding("ctrl+m", "show_memory", "Memory", show=True),
        Binding("ctrl+h", "show_help", "Help", show=True),
        Binding("ctrl+v", "voice_input", "Voice", show=True),
        Binding("ctrl+s", "save_state", "Save", show=True),
    ]

    current_provider: reactive[str] = reactive("unknown")
    reflection_enabled: reactive[bool] = reactive(True)
    voice_mode: reactive[bool] = reactive(False)

    def compose(self) -> ComposeResult:
        """Compose the TUI layout."""
        yield Header()
        yield Vertical(
            RichLog(id="chat-log", markup=True, highlight=True, wrap=True),
            Horizontal(
                Input(placeholder="Type your message...", id="user-input"),
                id="input-bar",
            ),
        )
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize on app mount."""
        try:
            _, provider, model = get_client()
            self.current_provider = f"{provider}/{model}"
        except Exception:
            self.current_provider = "no provider configured"

        self._update_status()
        log = self.query_one("#chat-log", RichLog)
        welcome = Text()
        welcome.append("🤖 Self-Evolving AI Agent\n", style="bold cyan")
        welcome.append(f"Provider: {self.current_provider}\n", style="dim")

        # Feature status
        features = []
        if HAS_TERMUX:
            features.append("📱 Termux:API")
        if HAS_VISION:
            features.append("👁️ Vision")
        if HAS_VOICE:
            features.append("🎤 Voice")
        features.append("🧠 RAG")
        features.append("🔍 Reflection")
        features.append("⚡ Events")
        features.append("📦 Git")
        features.append("🔀 Sub-agents")
        welcome.append(f"Features: {' | '.join(features)}\n", style="dim")

        welcome.append("\nType your message below. Commands:\n", style="dim")
        welcome.append("  /model        – Switch provider & model\n")
        welcome.append("  /memory       – Show long-term memories\n")
        welcome.append("  /procedures   – Show learned procedures\n")
        welcome.append("  /cron         – Show scheduled jobs\n")
        welcome.append("  /events       – Show event rules\n")
        welcome.append("  /snapshots    – Show git snapshots\n")
        welcome.append("  /voice        – Toggle voice mode\n")
        welcome.append("  /reflect      – Toggle reflection\n")
        welcome.append("  /save         – Save agent state\n")
        welcome.append("  /help         – Show all commands\n")
        log.write(welcome)

    def _update_status(self) -> None:
        mem_count = len(long_term.recent(1000))
        proc_count = len(procedural.all_procedures())
        status = self.query_one("#status-bar", Static)
        voice_icon = "🎤" if self.voice_mode else ""
        reflect_icon = "🔍" if self.reflection_enabled else ""
        status.update(
            f" {self.current_provider} | "
            f"Mem:{mem_count} Proc:{proc_count} | "
            f"{voice_icon}{reflect_icon} | "
            f"{datetime.now().strftime('%H:%M')}"
        )

    # -----------------------------------------------------------------------
    # Input handling
    # -----------------------------------------------------------------------

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user message submission."""
        user_text = event.value.strip()
        if not user_text:
            return

        event.input.value = ""
        log = self.query_one("#chat-log", RichLog)

        # Show user message
        log.write(Text(f"🧑 You: {user_text}", style="bold green"))

        # Handle slash commands
        if user_text.startswith("/"):
            await self._handle_command(user_text, log)
            return

        # Add to conversation
        short_term.add({"role": "user", "content": user_text})

        # Run agent loop
        await self._agent_loop(user_text, log)

    async def _handle_command(self, cmd: str, log: RichLog) -> None:
        """Handle slash commands."""
        parts = cmd.split(maxsplit=1)
        command = parts[0].lower()

        if command == "/help":
            help_text = Text("📋 Available Commands:\n", style="bold yellow")
            help_text.append("  /model          – Switch provider & model\n")
            help_text.append("  /memory         – View long-term memories\n")
            help_text.append("  /procedures     – View learned procedures\n")
            help_text.append("  /cron           – View scheduled jobs\n")
            help_text.append("  /events         – View event rules\n")
            help_text.append("  /recent_events  – View recent system events\n")
            help_text.append("  /snapshots      – View git evolution snapshots\n")
            help_text.append("  /save           – Save agent state to git\n")
            help_text.append("  /voice          – Toggle voice mode\n")
            help_text.append("  /reflect        – Toggle reflection\n")
            help_text.append("  /clear          – Clear working memory\n")
            help_text.append("  /help           – This help\n")
            help_text.append("\n💡 Just type naturally to chat with the agent!\n", style="dim")
            log.write(help_text)

        elif command == "/model":
            await self._handle_model_command(parts[1] if len(parts) > 1 else "", log)

        elif command == "/memory":
            memories = long_term.recent(10)
            if not memories:
                log.write(Text("  No memories stored yet.", style="dim"))
            else:
                log.write(Text("🧠 Long-term Memories:", style="bold cyan"))
                for i, m in enumerate(memories, 1):
                    log.write(Text(f"  {i}. {m.text[:120]}", style="dim"))

        elif command == "/procedures":
            procs = procedural.all_procedures()
            if not procs:
                log.write(Text("  No procedures learned yet.", style="dim"))
            else:
                log.write(Text("⚙️ Learned Procedures:", style="bold cyan"))
                for p in procs:
                    log.write(Text(f"  • {p.name}: {p.description}", style="dim"))

        elif command == "/cron":
            jobs = list_cron_jobs()
            if not jobs:
                log.write(Text("  No cron jobs scheduled.", style="dim"))
            else:
                log.write(Text("⏰ Scheduled Jobs:", style="bold cyan"))
                for j in jobs:
                    status = "✅" if j.get("enabled") else "❌"
                    log.write(Text(f"  {status} {j['name']}: {j['cron']} → {j['command']}", style="dim"))

        elif command == "/events":
            result = await list_event_rules()
            log.write(Text(f"⚡ Event Rules:\n{result.get('result', 'None')}", style="dim"))

        elif command == "/recent_events":
            result = await list_recent_events()
            log.write(Text(f"📊 Recent Events:\n{result.get('result', 'None')}", style="dim"))

        elif command == "/snapshots":
            result = await git_list_snapshots()
            log.write(Text(f"📦 Git Snapshots:\n{result.get('result', 'None')}", style="dim"))

        elif command == "/save":
            log.write(Text("  Saving agent state...", style="dim yellow"))
            result = await git_save_state(f"manual-save-{datetime.now().strftime('%H%M')}")
            log.write(Text(f"  {result.get('result', result.get('error', 'Unknown'))}", style="dim"))

        elif command == "/voice":
            self.voice_mode = not self.voice_mode
            status = "enabled" if self.voice_mode else "disabled"
            log.write(Text(f"  🎤 Voice mode {status}", style="dim"))

        elif command == "/reflect":
            self.reflection_enabled = not self.reflection_enabled
            status = "enabled" if self.reflection_enabled else "disabled"
            log.write(Text(f"  🔍 Reflection {status}", style="dim"))

        elif command == "/clear":
            short_term.clear()
            log.write(Text("  Working memory cleared.", style="dim"))

        else:
            log.write(Text(f"  Unknown command: {command}", style="red"))

    async def _handle_model_command(self, args: str, log: RichLog) -> None:
        """Handle /model command for provider/model switching.

        Usage:
          /model              – Show current provider and available providers
          /model list         – List all providers with models
          /model groq         – Switch to Groq (default model)
          /model groq mixtral – Switch to Groq with specific model
          /model reset        – Reset to auto-detect from .env
        """
        parts = args.strip().split()

        if not parts or parts[0] == "status":
            # Show current status
            info = get_session_info()
            providers = list_providers()

            status_text = Text("🤖 Provider & Model Status\n", style="bold cyan")

            if info["provider"]:
                status_text.append(f"  Active: {info['display']} / {info['model']}\n", style="bold green")
                status_text.append("  (Use /model reset to go back to auto-detect)\n", style="dim")
            else:
                try:
                    _, prov, model = get_client()
                    status_text.append(f"  Auto-detected: {prov}/{model}\n", style="bold green")
                except Exception:
                    status_text.append("  No provider configured\n", style="yellow")

            status_text.append("\nAvailable Providers:\n", style="bold yellow")
            for p in providers:
                icon = "✅" if p["available"] else "❌"
                active = " ← ACTIVE" if p["session_active"] else ""
                status_text.append(f"  {icon} {p['id']:<12} {p['display_name']}{active}\n", style="dim")
                if p["available"]:
                    status_text.append(f"     Default: {p['default_model']}\n", style="dim")
                    status_text.append(f"     Key: {p['key_env']}\n", style="dim")

            status_text.append("\nUsage:\n", style="bold yellow")
            status_text.append("  /model list              – Show all providers & models\n", style="dim")
            status_text.append("  /model groq              – Switch provider (default model)\n", style="dim")
            status_text.append("  /model groq mixtral-8x7b – Switch provider + model\n", style="dim")
            status_text.append("  /model reset             – Reset to auto-detect\n", style="dim")
            log.write(status_text)

        elif parts[0] == "list":
            # Detailed model listing
            providers = list_providers()
            list_text = Text("📋 All Providers & Models\n", style="bold cyan")

            for p in providers:
                icon = "✅" if p["available"] else "❌"
                active = " ← ACTIVE" if p["session_active"] else ""
                list_text.append(f"\n{icon} {p['display_name']}{active}\n", style="bold")
                list_text.append(f"   {p['description']}\n", style="dim")

                if p["available"]:
                    for m in p["models"]:
                        list_text.append(f"   • {m['id']}\n", style="dim")
                        list_text.append(f"     {m['name']} – {m['description']}  {m['speed']} {m['quality']}\n", style="dim")
                else:
                    list_text.append(f"   (Add {p['key_env']} to .env to enable)\n", style="dim")

            log.write(list_text)

        elif parts[0] == "reset":
            result = set_session_provider(None)
            log.write(Text(f"  🔄 {result['message']}", style="dim"))
            self._update_provider_display()

        else:
            # Switch provider (and optional model)
            provider = parts[0]
            model = parts[1] if len(parts) > 1 else None

            result = set_session_provider(provider, model)

            if "error" in result:
                log.write(Text(f"  ❌ {result['error']}", style="red"))
            else:
                log.write(Text(f"  ✅ {result['message']}", style="bold green"))
                self._update_provider_display()

    def _update_provider_display(self) -> None:
        """Update the provider display after a switch."""
        try:
            info = get_session_info()
            if info["provider"]:
                self.current_provider = f"{info['display']} / {info['model']}"
            else:
                _, prov, model = get_client()
                self.current_provider = f"{prov}/{model}"
        except Exception:
            self.current_provider = "no provider"
        self._update_status()

    # -----------------------------------------------------------------------
    # Core agent loop (tool calling + features)
    # -----------------------------------------------------------------------

    async def _agent_loop(self, user_text: str, log: RichLog, max_iterations: int = 5) -> None:
        """Run the agent with tool calling loop and all features."""
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *short_term.snapshot(),
        ]

        for iteration in range(max_iterations):
            try:
                # Get LLM response (may include tool calls)
                response = await chat(messages, tools=get_all_tools(), temperature=0.7)
            except Exception as e:
                log.write(Text(f"  ⚠️ LLM error: {e}", style="red"))
                return

            # Add assistant response to messages
            messages.append(response)

            # Check for tool calls
            tool_calls = response.get("tool_calls")
            if not tool_calls:
                # No tools – we're done
                content = response.get("content", "")
                if content:
                    # Apply reflection if enabled
                    if self.reflection_enabled:
                        log.write(Text("  🔍 Reflecting...", style="dim yellow"))
                        reflected = await agent_reflect(
                            user_query=user_text,
                            initial_response=content,
                            enabled=True,
                            max_rounds=1,
                        )
                        if reflected["reflected"]:
                            content = reflected["response"]
                            details = reflected["details"]
                            log.write(Text(f"  ✅ Improved after {details['rounds']} round(s) ({details['verdict']})", style="dim green"))

                    # Add to working memory
                    short_term.add({"role": "assistant", "content": content})

                    # Auto-save important content to semantic KB
                    if len(content) > 100:
                        asyncio.create_task(self._auto_save(content))

                    self._stream_to_log(content, log)

                    # Voice output if enabled
                    if self.voice_mode:
                        asyncio.create_task(self._speak(content))

                return

            # Execute tool calls
            for tc in tool_calls:
                func_name = tc["function"]["name"]
                func_args = tc["function"]["arguments"]

                log.write(Text(f"  🔧 {func_name}({func_args[:80]}...)", style="dim yellow"))

                result = await combined_execute_tool(func_name, func_args)

                # Show tool result briefly
                result_preview = result.get("result", result.get("error", ""))
                if isinstance(result_preview, dict):
                    result_preview = json.dumps(result_preview)[:200]
                if result_preview:
                    preview = str(result_preview)[:200] + "..." if len(str(result_preview)) > 200 else str(result_preview)
                    log.write(Text(f"  📎 {preview}", style="dim"))

                # Add tool result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False, default=str)[:4000],
                })

        log.write(Text("  ⚠️ Max tool iterations reached.", style="yellow"))

    def _stream_to_log(self, text: str, log: RichLog) -> None:
        """Display agent response in log."""
        lines = text.split("\n")
        formatted = Text("🤖 Agent: ", style="bold cyan")
        for line in lines:
            formatted.append(line + "\n")
        log.write(formatted)

    async def _auto_save(self, content: str) -> None:
        """Auto-save notable content to long-term memory and semantic KB."""
        # Save to long-term memory
        if any(kw in content.lower() for kw in ["important", "remember", "note:", "key insight", "conclusion"]):
            long_term.add(MemoryEntry(text=content[:500], source="auto_save", importance=0.6))

        # Save to semantic knowledge base
        try:
            await add_to_knowledge(content[:1000], source="conversation")
        except Exception:
            pass

    async def _speak(self, text: str) -> None:
        """Speak text using TTS."""
        try:
            from voice import tts_edge
            await tts_edge(text[:500])
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------------

    def action_clear_log(self) -> None:
        log = self.query_one("#chat-log", RichLog)
        log.clear()

    def action_show_memory(self) -> None:
        self.run_command("/memory")

    def action_show_help(self) -> None:
        self.run_command("/help")

    async def action_voice_input(self) -> None:
        """Toggle voice mode."""
        self.voice_mode = not self.voice_mode
        log = self.query_one("#chat-log", RichLog)
        status = "enabled" if self.voice_mode else "disabled"
        log.write(Text(f"  🎤 Voice mode {status}", style="dim"))

    async def action_save_state(self) -> None:
        """Save agent state to git."""
        log = self.query_one("#chat-log", RichLog)
        log.write(Text("  Saving agent state...", style="dim yellow"))
        result = await git_save_state(f"quick-save-{datetime.now().strftime('%H%M')}")
        log.write(Text(f"  {result.get('result', result.get('error', 'Unknown'))}", style="dim"))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = AgentTUI()
    app.run()
