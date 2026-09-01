#!/usr/bin/env python3
"""
telegram_bot.py – Telegram interface for the self-evolving AI agent.

Launch: python telegram_bot.py

Requires TELEGRAM_BOT_TOKEN in .env.

Features:
  - All agent features (tools, memory, vision, voice, etc.)
  - Photo analysis via Telegram image uploads
  - Voice messages via Telegram audio transcription
  - Inline keyboard for quick actions
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any
from datetime import datetime

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

load_dotenv()

from llm import chat, get_client
from memory import short_term, long_term, procedural, MemoryEntry
from tools import get_tools, execute_tool
from nl_cron import nl_to_cron, add_cron_job, list_cron_jobs

# Feature modules
from reflection import agent_reflect
from subagents import delegate_task, research_parallel
from events import event_listener, list_event_rules, list_recent_events
from git_integration import git_save_state, git_list_snapshots
from semantic import add_to_knowledge

# Conditionally import Termux modules
try:
    from termux_hardware import HARDWARE_TOOL_SCHEMAS, HARDWARE_TOOL_MAP
    HAS_TERMUX = True
except ImportError:
    HAS_TERMUX = False

try:
    from vision import VISION_TOOL_SCHEMAS, VISION_TOOL_MAP, analyze_image
    HAS_VISION = True
except ImportError:
    HAS_VISION = False

try:
    from voice import VOICE_TOOL_SCHEMAS, VOICE_TOOL_MAP, stt_groq
    HAS_VOICE = True
except ImportError:
    HAS_VOICE = False

# ---------------------------------------------------------------------------
# Combine all tool schemas and maps
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


async def combined_execute_tool(name: str, arguments: str | dict) -> dict[str, Any]:
    """Execute a tool by name."""
    fn = ALL_TOOL_MAP.get(name)
    if not fn:
        return {"result": "", "error": f"Unknown tool: {name}"}
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
    except json.JSONDecodeError:
        return {"result": "", "error": f"Invalid JSON arguments"}
    try:
        if asyncio.iscoroutinefunction(fn):
            return await fn(**args)
        else:
            return fn(**args)
    except TypeError as e:
        return {"result": "", "error": f"Tool argument error: {e}"}
    except Exception as e:
        return {"result": "", "error": f"Tool execution error: {e}"}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("telegram_bot")

SYSTEM_PROMPT = """You are a self-evolving AI assistant accessible via Telegram.

You have access to tools: web search, file operations, Python execution, memory management, 
Obsidian vault integration, and more.

Behaviors:
- Be concise and helpful (Telegram messages should be readable).
- Use tools when needed. Prefer web_search for current information.
- Save important user preferences and facts to memory.
- You remember things across sessions.
- Format responses with simple markdown for Telegram.
- For complex questions, consider using sub-agents for parallel research.
- Before important answers, reflect on accuracy.
- Auto-commit significant changes for version control.
"""

# Per-user conversation storage
_user_conversations: dict[int, list[dict[str, Any]]] = {}
_user_settings: dict[int, dict[str, Any]] = {}

MAX_HISTORY = 30


def _get_history(user_id: int) -> list[dict[str, Any]]:
    if user_id not in _user_conversations:
        _user_conversations[user_id] = []
    return _user_conversations[user_id]


def _get_settings(user_id: int) -> dict[str, Any]:
    if user_id not in _user_settings:
        _user_settings[user_id] = {"reflection": True, "voice": False}
    return _user_settings[user_id]


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    keyboard = [
        [
            InlineKeyboardButton("🧠 Memory", callback_data="show_memory"),
            InlineKeyboardButton("⚙️ Procedures", callback_data="show_procedures"),
        ],
        [
            InlineKeyboardButton("⚡ Events", callback_data="show_events"),
            InlineKeyboardButton("📦 Snapshots", callback_data="show_snapshots"),
        ],
        [
            InlineKeyboardButton("🔍 Toggle Reflection", callback_data="toggle_reflect"),
            InlineKeyboardButton("🎤 Toggle Voice", callback_data="toggle_voice"),
        ],
        [
            InlineKeyboardButton("💾 Save State", callback_data="save_state"),
            InlineKeyboardButton("⏰ Cron Jobs", callback_data="show_cron"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🤖 *Self-Evolving AI Agent*\n\n"
        "I'm your personal AI assistant with memory, vision, voice, and more.\n\n"
        "Commands:\n"
        "/memory – View long-term memories\n"
        "/procedures – View learned procedures\n"
        "/cron – View scheduled jobs\n"
        "/events – View event rules\n"
        "/snapshots – View git snapshots\n"
        "/save – Save agent state\n"
        "/reflect – Toggle reflection\n"
        "/voice – Toggle voice mode\n"
        "/clear – Clear conversation\n"
        "/help – Show this message\n\n"
        "💡 Send me a photo to analyze it!\n"
        "🎤 Send a voice message to transcribe it!\n\n"
        "Use the buttons below for quick actions:",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    memories = long_term.recent(10)
    if not memories:
        await update.message.reply_text("🧠 No memories stored yet.")
        return
    lines = ["🧠 *Long-term Memories:*\n"]
    for i, m in enumerate(memories, 1):
        lines.append(f"{i}. {m.text[:150]}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_procedures(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    procs = procedural.all_procedures()
    if not procs:
        await update.message.reply_text("⚙️ No procedures learned yet.")
        return
    lines = ["⚙️ *Learned Procedures:*\n"]
    for p in procs:
        lines.append(f"• *{p.name}*: {p.description}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_cron(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    jobs = list_cron_jobs()
    if not jobs:
        await update.message.reply_text("⏰ No jobs scheduled.")
        return
    lines = ["⏰ *Scheduled Jobs:*\n"]
    for j in jobs:
        status = "✅" if j.get("enabled") else "❌"
        lines.append(f"{status} *{j['name']}*: `{j['cron']}`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_events(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    result = await list_event_rules()
    await update.message.reply_text(f"⚡ *Event Rules:*\n{result.get('result', 'None')}", parse_mode="Markdown")


async def cmd_snapshots(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    result = await git_list_snapshots()
    await update.message.reply_text(f"📦 *Git Snapshots:*\n{result.get('result', 'None')}", parse_mode="Markdown")


async def cmd_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("💾 Saving agent state...")
    result = await git_save_state(f"telegram-save-{datetime.now().strftime('%H%M')}")
    await update.message.reply_text(f"✅ {result.get('result', result.get('error', 'Unknown'))}")


async def cmd_reflect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    settings = _get_settings(user_id)
    settings["reflection"] = not settings["reflection"]
    status = "enabled" if settings["reflection"] else "disabled"
    await update.message.reply_text(f"🔍 Reflection {status}")


async def cmd_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    settings = _get_settings(user_id)
    settings["voice"] = not settings["voice"]
    status = "enabled" if settings["voice"] else "disabled"
    await update.message.reply_text(f"🎤 Voice mode {status}")


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    _user_conversations.pop(user_id, None)
    await update.message.reply_text("🔄 Conversation cleared.")


# ---------------------------------------------------------------------------
# Callback query handler (inline buttons)
# ---------------------------------------------------------------------------

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard button presses."""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "show_memory":
        memories = long_term.recent(5)
        if not memories:
            text = "🧠 No memories stored yet."
        else:
            lines = ["🧠 *Memories:*\n"]
            for i, m in enumerate(memories, 1):
                lines.append(f"{i}. {m.text[:120]}")
            text = "\n".join(lines)
        await query.edit_message_text(text, parse_mode="Markdown")

    elif data == "show_procedures":
        procs = procedural.all_procedures()
        if not procs:
            text = "⚙️ No procedures yet."
        else:
            lines = ["⚙️ *Procedures:*\n"]
            for p in procs:
                lines.append(f"• *{p.name}*")
            text = "\n".join(lines)
        await query.edit_message_text(text, parse_mode="Markdown")

    elif data == "show_events":
        result = await list_event_rules()
        await query.edit_message_text(f"⚡ {result.get('result', 'None')}", parse_mode="Markdown")

    elif data == "show_snapshots":
        result = await git_list_snapshots()
        await query.edit_message_text(f"📦 {result.get('result', 'None')}", parse_mode="Markdown")

    elif data == "show_cron":
        jobs = list_cron_jobs()
        if not jobs:
            text = "⏰ No jobs."
        else:
            lines = ["⏰ *Jobs:*\n"]
            for j in jobs:
                lines.append(f"• {j['name']}: `{j['cron']}`")
            text = "\n".join(lines)
        await query.edit_message_text(text, parse_mode="Markdown")

    elif data == "toggle_reflect":
        user_id = update.effective_user.id
        settings = _get_settings(user_id)
        settings["reflection"] = not settings["reflection"]
        status = "ON" if settings["reflection"] else "OFF"
        await query.edit_message_text(f"🔍 Reflection: {status}")

    elif data == "toggle_voice":
        user_id = update.effective_user.id
        settings = _get_settings(user_id)
        settings["voice"] = not settings["voice"]
        status = "ON" if settings["voice"] else "OFF"
        await query.edit_message_text(f"🎤 Voice: {status}")

    elif data == "save_state":
        await query.edit_message_text("💾 Saving...")
        result = await git_save_state(f"button-save-{datetime.now().strftime('%H%M')}")
        await query.edit_message_text(f"✅ {result.get('result', result.get('error', 'Failed'))}")


# ---------------------------------------------------------------------------
# Photo handler (vision)
# ---------------------------------------------------------------------------

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle uploaded photos for vision analysis."""
    if not HAS_VISION:
        await update.message.reply_text("⚠️ Vision module not available.")
        return

    photo = update.message.photo[-1]  # Highest resolution
    caption = update.message.caption or "Describe this image in detail."

    await update.message.chat.send_action("typing")
    await update.message.reply_text("👁️ Analyzing image...")

    # Download photo
    file = await context.bot.get_file(photo.file_id)
    import tempfile
    from pathlib import Path
    temp_dir = Path(tempfile.gettempdir())
    photo_path = str(temp_dir / f"tg_photo_{photo.file_id}.jpg")
    await file.download_to_drive(photo_path)

    # Analyze
    result = await analyze_image(photo_path, prompt=caption)

    if result.get("error"):
        await update.message.reply_text(f"⚠️ Error: {result['error']}")
    else:
        text = result["result"]
        if len(text) > 4000:
            text = text[:3997] + "..."
        await update.message.reply_text(text, parse_mode="Markdown")

    # Clean up
    try:
        os.unlink(photo_path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Voice message handler
# ---------------------------------------------------------------------------

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle voice messages for transcription."""
    voice = update.message.voice
    if not voice:
        return

    await update.message.chat.send_action("typing")
    await update.message.reply_text("🎤 Transcribing voice message...")

    # Download voice file
    file = await context.bot.get_file(voice.file_id)
    import tempfile
    from pathlib import Path
    temp_dir = Path(tempfile.gettempdir())
    voice_path = str(temp_dir / f"tg_voice_{voice.file_id}.ogg")
    await file.download_to_drive(voice_path)

    # Transcribe
    if HAS_VOICE:
        result = await stt_groq(audio_path=voice_path)
    else:
        await update.message.reply_text("⚠️ Voice module not available.")
        try:
            os.unlink(voice_path)
        except OSError:
            pass
        return

    try:
        os.unlink(voice_path)
    except OSError:
        pass

    if result.get("error"):
        await update.message.reply_text(f"⚠️ Transcription error: {result['error']}")
        return

    text = result.get("text", "")
    if not text:
        await update.message.reply_text("No speech detected.")
        return

    # Process transcribed text as regular message
    await update.message.reply_text(f"🎤 *Transcribed:* {text}", parse_mode="Markdown")

    # Create a synthetic text update to process
    user_id = update.effective_user.id
    history = _get_history(user_id)
    history.append({"role": "user", "content": text})

    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]

    # Run agent loop
    for _ in range(5):
        try:
            response = await chat(messages, tools=ALL_TOOLS, temperature=0.7)
        except Exception as e:
            await update.message.reply_text(f"⚠️ Error: {e}")
            return

        messages.append(response)

        tool_calls = response.get("tool_calls")
        if not tool_calls:
            content = response.get("content", "")
            if content:
                history.append({"role": "assistant", "content": content})
                if len(content) > 4000:
                    content = content[:3997] + "..."
                await update.message.reply_text(content, parse_mode="Markdown")
            return

        for tc in tool_calls:
            result = await combined_execute_tool(tc["function"]["name"], tc["function"]["arguments"])
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(result, ensure_ascii=False, default=str)[:4000],
            })

    await update.message.reply_text("⚠️ Max iterations reached.")


# ---------------------------------------------------------------------------
# Main message handler with tool loop
# ---------------------------------------------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle user text messages with tool-calling loop."""
    user_id = update.effective_user.id
    user_text = update.message.text
    if not user_text:
        return

    await update.message.chat.send_action("typing")

    history = _get_history(user_id)
    history.append({"role": "user", "content": user_text})

    if len(history) > MAX_HISTORY * 2:
        history[:] = history[-MAX_HISTORY:]

    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]

    for _ in range(5):
        try:
            response = await chat(messages, tools=ALL_TOOLS, temperature=0.7)
        except Exception as e:
            logger.error(f"LLM error: {e}")
            await update.message.reply_text(f"⚠️ LLM error: {e}")
            return

        messages.append(response)

        tool_calls = response.get("tool_calls")
        if not tool_calls:
            content = response.get("content", "")
            if content:
                # Apply reflection if enabled
                settings = _get_settings(user_id)
                if settings.get("reflection", True):
                    reflected = await agent_reflect(
                        user_query=user_text,
                        initial_response=content,
                        enabled=True,
                        max_rounds=1,
                    )
                    if reflected["reflected"]:
                        content = reflected["response"]

                history.append({"role": "assistant", "content": content})
                if len(content) > 4000:
                    content = content[:3997] + "..."
                await update.message.reply_text(content, parse_mode="Markdown")
            return

        for tc in tool_calls:
            result = await combined_execute_tool(tc["function"]["name"], tc["function"]["arguments"])
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(result, ensure_ascii=False, default=str)[:4000],
            })

    await update.message.reply_text("⚠️ Max iterations reached.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN not set in .env")
        sys.exit(1)

    try:
        _, provider, model = get_client()
        print(f"✅ LLM provider: {provider}/{model}")
    except Exception as e:
        print(f"❌ {e}")
        sys.exit(1)

    # Feature status
    features = []
    if HAS_TERMUX:
        features.append("📱 Termux")
    if HAS_VISION:
        features.append("👁️ Vision")
    if HAS_VOICE:
        features.append("🎤 Voice")
    features.extend(["🧠 RAG", "🔍 Reflection", "⚡ Events", "📦 Git", "🔀 Sub-agents"])
    print(f"Features: {', '.join(features)}")

    print("🤖 Starting Telegram bot...")

    app = Application.builder().token(token).build()

    # Register handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("memory", cmd_memory))
    app.add_handler(CommandHandler("procedures", cmd_procedures))
    app.add_handler(CommandHandler("cron", cmd_cron))
    app.add_handler(CommandHandler("events", cmd_events))
    app.add_handler(CommandHandler("snapshots", cmd_snapshots))
    app.add_handler(CommandHandler("save", cmd_save))
    app.add_handler(CommandHandler("reflect", cmd_reflect))
    app.add_handler(CommandHandler("voice", cmd_voice))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Bot running! Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
