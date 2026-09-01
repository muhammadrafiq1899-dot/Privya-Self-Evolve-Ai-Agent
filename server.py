#!/usr/bin/env python3
"""
server.py – Unified entry point for all agent services.

Launch: python server.py

Runs:
  1. Web API server (FastAPI + WebSocket)
  2. Telegram bot (if configured)
  3. Event listeners (battery, SMS monitors)
  4. Memory consolidation (periodic)

All services run as async tasks in a single process.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PORT = int(os.getenv("PORT", 8000))
HOST = os.getenv("HOST", "0.0.0.0")
ENABLE_TELEGRAM = bool(os.getenv("TELEGRAM_BOT_TOKEN"))
ENABLE_EVENTS = True
CONSOLIDATION_INTERVAL = 3600  # 1 hour

# ---------------------------------------------------------------------------
# Service runners
# ---------------------------------------------------------------------------

async def run_api_server():
    """Start the FastAPI web server."""
    import uvicorn
    from api.server import app
    
    config = uvicorn.Config(
        app,
        host=HOST,
        port=PORT,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)
    await server.serve()


async def run_telegram_bot():
    """Start the Telegram bot as a background task."""
    if not ENABLE_TELEGRAM:
        print("⏭️  Telegram bot disabled (no TELEGRAM_BOT_TOKEN)")
        return
    
    try:
        from telegram_bot import main as tg_main
        print("🤖 Starting Telegram bot...")
        # Run in thread to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, tg_main)
    except Exception as e:
        print(f"⚠️ Telegram bot error: {e}")


async def run_event_listeners():
    """Start background event monitors."""
    if not ENABLE_EVENTS:
        return
    
    try:
        from termux_hardware import battery_status
        # Check if Termux:API is available
        result = await battery_status()
        if "error" in result:
            print("⏭️  Termux:API not available, event listeners disabled")
            return
    except Exception:
        print("⏭️  Termux:API not available, event listeners disabled")
        return
    
    try:
        from events import monitor_manager
        print("⚡ Starting event listeners...")
        await monitor_manager.start(["battery", "sms", "idle"])
    except Exception as e:
        print(f"⚠️ Event listener error: {e}")


async def run_periodic_consolidation():
    """Periodically consolidate memories."""
    while True:
        await asyncio.sleep(CONSOLIDATION_INTERVAL)
        try:
            from consolidator import run_consolidation
            print("🔄 Running periodic memory consolidation...")
            await run_consolidation(scan_only=True)
        except Exception as e:
            print(f"⚠️ Consolidation error: {e}")


async def run_websocket_broadcaster():
    """Broadcast periodic status updates via WebSocket."""
    from api.server import broadcast, websocket_clients
    
    while True:
        await asyncio.sleep(10)
        if websocket_clients:
            try:
                from api.server import get_stats
                stats = await get_stats()
                await broadcast({"type": "stats", **stats})
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    """Run all services together."""
    print("=" * 60)
    print("🤖 Self-Evolving AI Agent - Unified System")
    print("=" * 60)
    print()
    
    # Check LLM provider
    try:
        from llm import get_client
        _, provider, model = get_client()
        print(f"✅ LLM Provider: {provider}/{model}")
    except Exception as e:
        print(f"❌ {e}")
        print("   Add at least one API key to .env")
        sys.exit(1)
    
    # Feature status
    features = []
    try:
        from termux_hardware import HARDWARE_TOOL_SCHEMAS
        features.append("📱 Termux:API")
    except ImportError:
        pass
    try:
        from vision import VISION_TOOL_SCHEMAS
        features.append("👁️ Vision")
    except ImportError:
        pass
    try:
        from voice import VOICE_TOOL_SCHEMAS
        features.append("🎤 Voice")
    except ImportError:
        pass
    features.extend(["🧠 RAG", "🔍 Reflection", "⚡ Events", "📦 Git", "🔀 Sub-agents"])
    print(f"✅ Features: {', '.join(features)}")
    
    # Tool count
    from tools import get_tools
    print(f"✅ Tools: {len(get_tools())} base + extensions")
    
    print()
    print(f"🌐 Dashboard: http://localhost:{PORT}")
    print(f"📡 API: http://localhost:{PORT}/api")
    print(f"🔌 WebSocket: ws://localhost:{PORT}/ws")
    
    if ENABLE_TELEGRAM:
        print(f"🤖 Telegram: enabled")
    else:
        print(f"⏭️  Telegram: disabled (add TELEGRAM_BOT_TOKEN to .env)")
    
    print()
    print("Starting services...")
    print("-" * 60)
    
    # Create task group for all services
    tasks = [
        asyncio.create_task(run_api_server(), name="api-server"),
        asyncio.create_task(run_event_listeners(), name="event-listeners"),
        asyncio.create_task(run_periodic_consolidation(), name="consolidation"),
        asyncio.create_task(run_websocket_broadcaster(), name="ws-broadcaster"),
    ]
    
    if ENABLE_TELEGRAM:
        tasks.append(asyncio.create_task(run_telegram_bot(), name="telegram-bot"))
    
    # Handle shutdown
    loop = asyncio.get_event_loop()
    
    def shutdown_handler():
        print("\n🛑 Shutting down all services...")
        for task in tasks:
            task.cancel()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_handler)
    
    # Run all tasks
    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except asyncio.CancelledError:
        print("✅ All services stopped.")
    except KeyboardInterrupt:
        print("\n🛑 Interrupted.")
    finally:
        # Cleanup
        for task in tasks:
            if not task.done():
                task.cancel()
        print("✅ Shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
