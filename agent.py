#!/usr/bin/env python3
"""
agent.py – Self-evolving AI agent with Textual TUI.

Launch: python agent.py

Features:
  - Multi-provider LLM (Groq / OpenRouter / Gemini / Together / Custom)
  - Tool calling with sandboxed execution
  - Short-term, long-term, and procedural memory
  - Web search, file I/O, Python/shell execution
  - Natural language scheduling
  - Obsidian vault integration
  - Hardware access (Termux:API)
  - Vision & multimodal (image analysis)
  - Voice I/O (STT/TTS)
  - Semantic vector search (RAG)
  - Reflection & self-correction
  - Event-driven proactivity
  - Git self-versioning
  - Sub-agent delegation
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
    OptionList,
)
from textual.widgets.option_list import Option
from textual.reactive import reactive
from textual.events import Mount, Key
from rich.text import Text
from rich.panel import Panel
from rich.columns import Columns

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
# Version info
# ---------------------------------------------------------------------------

APP_VERSION = "1.0.0"
APP_BUILD = "2026.09.02"

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

# Count toolsets
TOOLSETS = sorted(set(
    name.split("_")[0] if "_" in name else name
    for name in ALL_TOOL_MAP.keys()
))

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
# Textual TUI Application – Purple Hermes Theme
# ---------------------------------------------------------------------------

class AgentTUI(App):
    """Self-evolving AI agent terminal interface – Purple Edition."""

    TITLE = "✦ PRIVYA – Self-Evolving AI Agent"
    SUB_TITLE = "Multi-feature AI with memory, vision, voice & more"

    CSS = """
    Screen {
        layout: vertical;
        background: #0d0014;
    }

    /* ── Top header strip ── */
    #top-bar {
        height: auto;
        dock: top;
        padding: 0 1;
        background: #1a0030;
        border-bottom: tall #9b30ff;
    }
    #top-bar Static {
        color: #e0b0ff;
    }

    /* ── Info strip (model, tools, provider) ── */
    #info-strip {
        height: auto;
        padding: 0 1;
        background: #0d0014;
    }
    #info-strip Static {
        color: #c080ff;
    }

    /* ── Chat log ── */
    #chat-log {
        height: 1fr;
        margin: 0 1;
        border: solid #6a0dad;
        background: #0d0014;
        padding: 0;
    }

    /* ── Input area ── */
    #input-area {
        height: auto;
        min-height: 3;
        padding: 0 1 0 1;
        background: #0d0014;
    }
    #input-bar {
        height: 3;
        background: #1a0030;
        border: tall #9b30ff;
    }
    #input-bar Input {
        background: #1a0030;
        color: #e0b0ff;
    }

    /* ── Prompt indicator ── */
    #prompt-line {
        height: 1;
        padding: 0 1;
        background: #0d0014;
    }
    #prompt-line Static {
        color: #9b30ff;
        text-style: bold;
    }

    /* ── Status bar ── */
    #status-bar {
        height: 1;
        dock: bottom;
        padding: 0 1;
        background: #1a0030;
        border-top: tall #6a0dad;
        color: #c080ff;
    }

    /* ── Model picker overlay ── */
    #model-picker-container {
        height: auto;
        max-height: 30;
        margin: 1 2;
        background: #0d0014;
        border: tall #9b30ff;
    }
    #model-picker-container Static {
        color: #e0b0ff;
        text-style: bold;
        padding: 0 1;
    }
    #model-picker {
        max-height: 25;
        background: #0d0014;
        border: hidden;
    }
    #model-picker > .option-list--option {
        color: #c080ff;
        padding: 0 1;
    }
    #model-picker > .option-list--option-highlighted {
        color: #ffffff;
        background: #3d0066;
    }
    #model-picker > .option-list--option-selected {
        color: #ff80ff;
        background: #2a004a;
    }

    /* ── Welcome banner ── */
    #welcome-banner {
        height: auto;
        margin: 0 1;
        padding: 0;
        background: #0d0014;
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
    current_model: reactive[str] = reactive("unknown")
    reflection_enabled: reactive[bool] = reactive(True)
    voice_mode: reactive[bool] = reactive(False)
    model_picker_visible: reactive[bool] = reactive(False)

    def compose(self) -> ComposeResult:
        """Compose the TUI layout."""
        # Top bar: agent name + version
        yield Static("", id="top-bar")

        # Info strip: model, tools, toolsets, provider
        yield Static("", id="info-strip")

        # Welcome banner
        yield Static("", id="welcome-banner")

        # Chat area with border
        yield RichLog(id="chat-log", markup=True, highlight=True, wrap=True)

        # Prompt indicator
        yield Static("  $ ", id="prompt-line")

        # Input bar
        yield Input(placeholder="", id="input-bar")

        # Status bar
        yield Static("", id="status-bar")

    def on_mount(self) -> None:
        """Initialize on app mount."""
        # Resolve current provider/model
        try:
            _, provider, model = get_client()
            self.current_provider = provider
            self.current_model = model
        except Exception:
            self.current_provider = "none"
            self.current_model = "none"

        self._update_top_bar()
        self._update_info_strip()
        self._update_welcome()
        self._update_status()

        # Focus input
        self.query_one("#input-bar", Input).focus()

    # -----------------------------------------------------------------------
    # Layout updates
    # -----------------------------------------------------------------------

    def _update_top_bar(self) -> None:
        """Update the top header bar with agent name, version, build."""
        bar = self.query_one("#top-bar", Static)
        t = Text()
        t.append("  ✦ ", style="bold #9b30ff")
        t.append("PRIVYA", style="bold #e0b0ff")
        t.append(" – AI Agent Framework", style="bold #c080ff")
        t.append(f"\n  Agent v{APP_VERSION}", style="dim #9b30ff")
        t.append(f" ({APP_BUILD})", style="dim #7b2fa0")
        bar.update(t)

    def _update_info_strip(self) -> None:
        """Update model/tools/provider info line."""
        strip = self.query_one("#info-strip", Static)
        t = Text()
        t.append("  ● ", style="bold #9b30ff")
        t.append(f"{self.current_model}", style="bold #e0b0ff")
        t.append("  ·  ", style="dim #6a0dad")
        t.append(f"{len(ALL_TOOLS)} tools", style="bold #c080ff")
        t.append("  ·  ", style="dim #6a0dad")
        t.append("toolsets: ", style="dim #9b30ff")
        t.append(", ".join(TOOLSETS), style="dim #7b2fa0")
        t.append("  ·  ", style="dim #6a0dad")
        t.append("provider: ", style="dim #9b30ff")
        t.append(f"{self.current_provider}", style="bold #e0b0ff")
        strip.update(t)

    def _update_welcome(self) -> None:
        """Update the welcome banner."""
        banner = self.query_one("#welcome-banner", Static)
        t = Text()
        t.append("\n  Welcome to Privya Agent! Type your message or /help for commands.\n", style="#c080ff")
        t.append("  Tip: /model opens the interactive model picker. Arrow keys to browse, Enter to select.\n", style="dim #7b2fa0")
        banner.update(t)

    def _update_status(self) -> None:
        """Update the bottom status bar."""
        status = self.query_one("#status-bar", Static)
        mem_count = len(long_term.recent(1000))
        proc_count = len(procedural.all_procedures())
        voice_icon = "🎤" if self.voice_mode else ""
        reflect_icon = "🔍" if self.reflection_enabled else ""
        t = Text()
        t.append("  $ ", style="bold #9b30ff")
        t.append(f"{self.current_model}", style="bold #e0b0ff")
        t.append("  ·  ", style="dim #6a0dad")
        t.append(f"mem:{mem_count}", style="#c080ff")
        t.append("  ", style="dim")
        t.append(f"proc:{proc_count}", style="#c080ff")
        t.append("  ·  ", style="dim #6a0dad")
        t.append(f"{voice_icon}{reflect_icon}", style="dim")
        t.append("  ·  ", style="dim #6a0dad")
        t.append(f"{datetime.now().strftime('%H:%M')}", style="dim #9b30ff")
        status.update(t)

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
        log.write(Text(f"  ✦ {user_text}", style="bold #e0b0ff"))

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
            help_text = Text()
            help_text.append("\n  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n", style="dim #6a0dad")
            help_text.append("  ✦ PRIVYA COMMANDS\n", style="bold #9b30ff")
            help_text.append("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n", style="dim #6a0dad")
            help_text.append("  /model          ", style="bold #e0b0ff")
            help_text.append("– Interactive model picker\n", style="#c080ff")
            help_text.append("  /model list     ", style="bold #e0b0ff")
            help_text.append("– Fetch live models from providers\n", style="#c080ff")
            help_text.append("  /model reset    ", style="bold #e0b0ff")
            help_text.append("– Reset to auto-detect\n", style="#c080ff")
            help_text.append("  /memory         ", style="bold #e0b0ff")
            help_text.append("– View long-term memories\n", style="#c080ff")
            help_text.append("  /procedures     ", style="bold #e0b0ff")
            help_text.append("– View learned procedures\n", style="#c080ff")
            help_text.append("  /cron           ", style="bold #e0b0ff")
            help_text.append("– View scheduled jobs\n", style="#c080ff")
            help_text.append("  /events         ", style="bold #e0b0ff")
            help_text.append("– View event rules\n", style="#c080ff")
            help_text.append("  /recent_events  ", style="bold #e0b0ff")
            help_text.append("– View recent system events\n", style="#c080ff")
            help_text.append("  /snapshots      ", style="bold #e0b0ff")
            help_text.append("– View git evolution snapshots\n", style="#c080ff")
            help_text.append("  /save           ", style="bold #e0b0ff")
            help_text.append("– Save agent state to git\n", style="#c080ff")
            help_text.append("  /voice          ", style="bold #e0b0ff")
            help_text.append("– Toggle voice mode\n", style="#c080ff")
            help_text.append("  /reflect        ", style="bold #e0b0ff")
            help_text.append("– Toggle reflection\n", style="#c080ff")
            help_text.append("  /clear          ", style="bold #e0b0ff")
            help_text.append("– Clear working memory\n", style="#c080ff")
            help_text.append("  /help           ", style="bold #e0b0ff")
            help_text.append("– This help\n", style="#c080ff")
            help_text.append("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n", style="dim #6a0dad")
            help_text.append("  Just type naturally to chat with the agent!\n", style="dim #7b2fa0")
            log.write(help_text)

        elif command == "/model":
            arg = parts[1].strip() if len(parts) > 1 else ""
            if arg and arg not in ("list", "reset", "status"):
                # Direct switch: /model groq mixtral-8x7b
                await self._switch_model(arg, log)
            elif arg == "list":
                await self._handle_model_list(log)
            elif arg == "reset":
                result = set_session_provider(None)
                log.write(Text(f"  🔄 {result['message']}", style="dim #c080ff"))
                self._refresh_provider()
            elif arg == "status":
                await self._handle_model_status(log)
            else:
                # Interactive picker
                await self._show_model_picker(log)

        elif command == "/memory":
            memories = long_term.recent(10)
            if not memories:
                log.write(Text("  No memories stored yet.", style="dim #7b2fa0"))
            else:
                log.write(Text("  ✦ Long-term Memories", style="bold #9b30ff"))
                for i, m in enumerate(memories, 1):
                    log.write(Text(f"    {i}. {m.text[:120]}", style="dim #c080ff"))

        elif command == "/procedures":
            procs = procedural.all_procedures()
            if not procs:
                log.write(Text("  No procedures learned yet.", style="dim #7b2fa0"))
            else:
                log.write(Text("  ✦ Learned Procedures", style="bold #9b30ff"))
                for p in procs:
                    log.write(Text(f"    • {p.name}: {p.description}", style="dim #c080ff"))

        elif command == "/cron":
            jobs = list_cron_jobs()
            if not jobs:
                log.write(Text("  No cron jobs scheduled.", style="dim #7b2fa0"))
            else:
                log.write(Text("  ✦ Scheduled Jobs", style="bold #9b30ff"))
                for j in jobs:
                    icon = "●" if j.get("enabled") else "○"
                    log.write(Text(f"    {icon} {j['name']}: {j['cron']} → {j['command']}", style="dim #c080ff"))

        elif command == "/events":
            result = await list_event_rules()
            log.write(Text(f"  ✦ Event Rules\n{result.get('result', 'None')}", style="dim #c080ff"))

        elif command == "/recent_events":
            result = await list_recent_events()
            log.write(Text(f"  ✦ Recent Events\n{result.get('result', 'None')}", style="dim #c080ff"))

        elif command == "/snapshots":
            result = await git_list_snapshots()
            log.write(Text(f"  ✦ Git Snapshots\n{result.get('result', 'None')}", style="dim #c080ff"))

        elif command == "/save":
            log.write(Text("  Saving agent state...", style="dim #9b30ff"))
            result = await git_save_state(f"manual-save-{datetime.now().strftime('%H%M')}")
            log.write(Text(f"  {result.get('result', result.get('error', 'Unknown'))}", style="dim #c080ff"))

        elif command == "/voice":
            self.voice_mode = not self.voice_mode
            status = "enabled" if self.voice_mode else "disabled"
            log.write(Text(f"  🎤 Voice mode {status}", style="dim #c080ff"))
            self._update_status()

        elif command == "/reflect":
            self.reflection_enabled = not self.reflection_enabled
            status = "enabled" if self.reflection_enabled else "disabled"
            log.write(Text(f"  🔍 Reflection {status}", style="dim #c080ff"))
            self._update_status()

        elif command == "/clear":
            short_term.clear()
            log.write(Text("  Working memory cleared.", style="dim #c080ff"))

        else:
            log.write(Text(f"  Unknown command: {command}", style="bold #ff4040"))

    # -----------------------------------------------------------------------
    # Interactive Model Picker (Hermes-style)
    # -----------------------------------------------------------------------

    async def _show_model_picker(self, log: RichLog) -> None:
        """Show the interactive model picker with arrow keys and enter selection."""
        providers = list_providers()
        available = [p for p in providers if p["available"]]

        if not available:
            log.write(Text("  ❌ No providers configured. Add an API key to .env", style="bold #ff4040"))
            return

        # Fetch live models from all available providers
        log.write(Text("  ⏳ Fetching live models from providers...", style="dim #9b30ff"))

        all_models: list[tuple[str, str, str]] = []  # (provider_id, model_id, display_name)

        for p in available:
            try:
                live_models = await fetch_models_from_provider(p["id"])
            except Exception:
                live_models = p["models"]

            if not live_models:
                live_models = p["models"]

            for m in live_models:
                display = m["id"]
                desc = m.get("description", "")
                provider_tag = f"[{p['id']}]"
                all_models.append((p["id"], m["id"], display, desc, provider_tag))

        if not all_models:
            log.write(Text("  ❌ No models found from any provider.", style="bold #ff4040"))
            return

        # Log the picker header
        log.write(Text(f"\n  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", style="dim #6a0dad"))
        log.write(Text(f"  ✦ Model Picker – {len(all_models)} available", style="bold #9b30ff"))
        log.write(Text(f"  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", style="dim #6a0dad"))
        log.write(Text(f"  Use ↑↓ arrow keys to browse, Enter to select, Esc to cancel", style="dim #7b2fa0"))
        log.write(Text("", style="dim"))

        # Build the OptionList for interactive selection
        options: list[Option | OptionListSeparator] = []

        current_provider = None
        for provider_id, model_id, display, desc, provider_tag in all_models:
            # Add header between providers
            if provider_id != current_provider:
                if current_provider is not None:
                    options.append(Option(
                        Text("", style="dim"),
                        id=f"sep_{provider_id}",
                        disabled=True,
                    ))
                options.append(Option(
                    Text(f"  ── {provider_tag} ──", style="bold #9b30ff"),
                    id=f"header_{provider_id}",
                    disabled=True,
                ))
                current_provider = provider_id

            # Build option text
            opt_text = Text()
            opt_text.append(f"    {display}", style="#e0b0ff")
            if desc:
                opt_text.append(f"  {desc}", style="dim #7b2fa0")
            options.append(Option(opt_text, id=model_id))

        # Create the option list widget
        option_list = OptionList(*options, id="model-picker")
        option_list.styles.max_height = 25

        yield option_list

        # Wait for selection
        self.model_picker_visible = True
        try:
            event = await self.wait_for_dismiss_or_select(option_list)
            if event is not None:
                selected_id = event.option_id
                # Find provider for this model
                for provider_id, model_id, display, desc, provider_tag in all_models:
                    if model_id == selected_id:
                        result = set_session_provider(provider_id, model_id)
                        if "error" in result:
                            log.write(Text(f"  ❌ {result['error']}", style="bold #ff4040"))
                        else:
                            log.write(Text(f"  ✅ {result['message']}", style="bold #e0b0ff"))
                            self._refresh_provider()
                        break
        except Exception:
            pass
        finally:
            self.model_picker_visible = False
            # Remove the option list
            try:
                option_list.remove()
            except Exception:
                pass

    async def wait_for_dismiss_or_select(self, option_list: OptionList) -> Any:
        """Wait for user to select an option or press Escape."""
        from textual import work

        result = None
        result_holder = {"value": None}

        async def wait_for_selection():
            async for event in option_list.events():
                if isinstance(event, OptionList.OptionSelected):
                    result_holder["value"] = event
                    return

        # Run selection watcher
        self.run_worker(wait_for_selection(), exclusive=True)

        # Wait for either selection or escape
        while result_holder["value"] is None:
            await asyncio.sleep(0.05)
            # Check if widget was removed
            if not option_list.is_mounted:
                return None

        return result_holder["value"]

    async def _handle_model_status(self, log: RichLog) -> None:
        """Show current model status."""
        info = get_session_info()
        providers = list_providers()

        log.write(Text("\n  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", style="dim #6a0dad"))
        log.write(Text("  ✦ Provider & Model Status", style="bold #9b30ff"))
        log.write(Text("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", style="dim #6a0dad"))

        if info["provider"]:
            log.write(Text(f"    Active: {info['display']} / {info['model']}", style="bold #e0b0ff"))
            log.write(Text(f"    (Use /model reset to go back to auto-detect)", style="dim #7b2fa0"))
        else:
            try:
                _, prov, model = get_client()
                log.write(Text(f"    Auto-detected: {prov}/{model}", style="bold #e0b0ff"))
            except Exception:
                log.write(Text("    No provider configured", style="bold #ff4040"))

        log.write(Text("", style="dim"))
        for p in providers:
            icon = "●" if p["available"] else "○"
            active = " ← ACTIVE" if p["session_active"] else ""
            color = "#e0b0ff" if p["available"] else "#7b2fa0"
            log.write(Text(f"    {icon} {p['id']:<12}", style=f"bold {color}"))
            log.write(Text(f"       {p['display_name']}{active}", style=color))
            if p["available"]:
                log.write(Text(f"       Default: {p['default_model']}", style="dim #7b2fa0"))
                log.write(Text(f"       Key: {p['key_env']}", style="dim #7b2fa0"))

        log.write(Text("\n  Usage:", style="bold #9b30ff"))
        log.write(Text("    /model                – Interactive model picker (arrow keys + enter)", style="dim #c080ff"))
        log.write(Text("    /model list           – Fetch all models from providers", style="dim #c080ff"))
        log.write(Text("    /model groq           – Switch provider (default model)", style="dim #c080ff"))
        log.write(Text("    /model groq mixtral   – Switch provider + model", style="dim #c080ff"))
        log.write(Text("    /model reset          – Reset to auto-detect", style="dim #c080ff"))
        log.write(Text("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n", style="dim #6a0dad"))

    async def _handle_model_list(self, log: RichLog) -> None:
        """List all providers and live-fetched models."""
        providers = list_providers()

        log.write(Text("\n  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", style="dim #6a0dad"))
        log.write(Text("  ✦ All Providers & Models (live)", style="bold #9b30ff"))
        log.write(Text("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", style="dim #6a0dad"))

        for p in providers:
            icon = "●" if p["available"] else "○"
            active = " ← ACTIVE" if p["session_active"] else ""
            log.write(Text(f"\n  {icon} {p['display_name']}{active}", style="bold #e0b0ff"))
            log.write(Text(f"    {p['description']}", style="dim #7b2fa0"))

            if p["available"]:
                log.write(Text(f"    ⏳ Fetching live models...", style="dim #9b30ff"))

                try:
                    live_models = await fetch_models_from_provider(p["id"])
                except Exception as e:
                    live_models = p["models"]
                    log.write(Text(f"    ⚠️ API error: {e}", style="dim #ff8040"))

                if not live_models:
                    live_models = p["models"]

                # Show first 50
                shown = live_models[:50]
                remaining = len(live_models) - 50

                for m in shown:
                    desc = m.get("description", "")
                    log.write(Text(f"    • {m['id']}", style="#c080ff"))
                    if desc:
                        log.write(Text(f"      {desc}", style="dim #7b2fa0"))

                if remaining > 0:
                    log.write(Text(f"    ... and {remaining} more models", style="dim #9b30ff"))
                log.write(Text(f"    ({len(live_models)} total)", style="dim #7b2fa0"))
            else:
                log.write(Text(f"    (Add {p['key_env']} to .env to enable)", style="dim #7b2fa0"))

        log.write(Text("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n", style="dim #6a0dad"))

    async def _switch_model(self, args: str, log: RichLog) -> None:
        """Switch model directly from /model <provider> [model]"""
        parts = args.split()
        provider = parts[0]
        model = parts[1] if len(parts) > 1 else None

        result = set_session_provider(provider, model)
        if "error" in result:
            log.write(Text(f"  ❌ {result['error']}", style="bold #ff4040"))
        else:
            log.write(Text(f"  ✅ {result['message']}", style="bold #e0b0ff"))
            self._refresh_provider()

    def _refresh_provider(self) -> None:
        """Refresh provider display after a switch."""
        try:
            info = get_session_info()
            if info["provider"]:
                self.current_provider = info["display"]
                self.current_model = info["model"]
            else:
                _, prov, model = get_client()
                self.current_provider = prov
                self.current_model = model
        except Exception:
            self.current_provider = "none"
            self.current_model = "none"
        self._update_info_strip()
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
                log.write(Text(f"  ⚠️ LLM error: {e}", style="bold #ff4040"))
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
                        log.write(Text("  🔍 Reflecting...", style="dim #9b30ff"))
                        reflected = await agent_reflect(
                            user_query=user_text,
                            initial_response=content,
                            enabled=True,
                            max_rounds=1,
                        )
                        if reflected["reflected"]:
                            content = reflected["response"]
                            details = reflected["details"]
                            log.write(Text(f"  ✅ Improved after {details['rounds']} round(s) ({details['verdict']})", style="dim #e0b0ff"))

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

                log.write(Text(f"  🔧 {func_name}({func_args[:80]}...)", style="dim #9b30ff"))

                result = await combined_execute_tool(func_name, func_args)

                # Show tool result briefly
                result_preview = result.get("result", result.get("error", ""))
                if isinstance(result_preview, dict):
                    result_preview = json.dumps(result_preview)[:200]
                if result_preview:
                    preview = str(result_preview)[:200] + "..." if len(str(result_preview)) > 200 else str(result_preview)
                    log.write(Text(f"  📎 {preview}", style="dim #7b2fa0"))

                # Add tool result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False, default=str)[:4000],
                })

        log.write(Text("  ⚠️ Max tool iterations reached.", style="bold #ff8040"))

    def _stream_to_log(self, text: str, log: RichLog) -> None:
        """Display agent response in log."""
        lines = text.split("\n")
        formatted = Text()
        formatted.append("  ✦ ", style="bold #9b30ff")
        for i, line in enumerate(lines):
            if i > 0:
                formatted.append("    ")
            formatted.append(line + "\n", style="#e0b0ff")
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
        log.write(Text(f"  🎤 Voice mode {status}", style="dim #c080ff"))
        self._update_status()

    async def action_save_state(self) -> None:
        """Save agent state to git."""
        log = self.query_one("#chat-log", RichLog)
        log.write(Text("  Saving agent state...", style="dim #9b30ff"))
        result = await git_save_state(f"quick-save-{datetime.now().strftime('%H%M')}")
        log.write(Text(f"  {result.get('result', result.get('error', 'Unknown'))}", style="dim #c080ff"))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = AgentTUI()
    app.run()
