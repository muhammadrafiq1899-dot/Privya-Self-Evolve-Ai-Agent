#!/usr/bin/env python3
"""
api/server.py – Unified API server for the AI agent.

Launch: python api/server.py (or python server.py from root)

Provides:
  - REST API for agent control
  - WebSocket for real-time updates
  - Static file serving for web dashboard
  - Background task management
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Always load .env from the project root, regardless of CWD
_project_root = Path(__file__).parent.parent
load_dotenv(_project_root / ".env")

# Import agent modules
from llm import chat, get_client
from memory import short_term, long_term, procedural, MemoryEntry
from tools import get_tools, execute_tool
from nl_cron import list_cron_jobs
from reflection import agent_reflect
from subagents import delegate_task
from events import event_listener, list_event_rules, list_recent_events
from git_integration import git_save_state, git_list_snapshots
from semantic import vector_store

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AI Agent API",
    description="Self-Evolving AI Agent - Unified API",
    version="2.0.0",
)

# Serve static files from web/
web_dir = Path(__file__).parent.parent / "web"
if web_dir.exists():
    app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

# Global state
start_time = time.time()
request_count = 0
activity_log: list[dict[str, Any]] = []
websocket_clients: list[WebSocket] = []

# Tool map for execution
from tools import _tool_map as base_tool_map
ALL_TOOL_MAP = dict(base_tool_map)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    reflection: bool = True
    max_iterations: int = 20

class ChatResponse(BaseModel):
    response: str
    tools_used: list[str] = []
    reflected: bool = False
    duration: float = 0.0

class EventRuleRequest(BaseModel):
    name: str
    event_type: str
    condition: str
    action: str
    cooldown: int = 300

class MemoryRequest(BaseModel):
    text: str
    tags: list[str] = []
    importance: float = 0.5

# ---------------------------------------------------------------------------
# WebSocket manager
# ---------------------------------------------------------------------------

async def broadcast(message: dict[str, Any]):
    """Send message to all connected WebSocket clients."""
    for client in websocket_clients[:]:
        try:
            await client.send_json(message)
        except Exception:
            websocket_clients.remove(client)

def log_activity(text: str):
    """Add to activity log."""
    entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "text": text,
        "timestamp": time.time(),
    }
    activity_log.insert(0, entry)
    if len(activity_log) > 100:
        activity_log.pop()

# ---------------------------------------------------------------------------
# Routes: Dashboard
# ---------------------------------------------------------------------------

@app.get("/")
async def serve_dashboard():
    """Serve the web dashboard."""
    index_path = web_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "AI Agent API running. Dashboard not found."}

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "uptime": f"{time.time() - start_time:.0f}s"}

# ---------------------------------------------------------------------------
# Routes: Chat
# ---------------------------------------------------------------------------

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """Send a message to the agent and get a response."""
    global request_count
    request_count += 1
    
    start = time.time()
    log_activity(f"User: {req.message[:50]}...")
    await broadcast({"type": "activity", "time": datetime.now().strftime("%H:%M:%S"), "text": f"New message: {req.message[:50]}..."})
    
    # Build messages
    messages = [
        {"role": "system", "content": "You are a helpful AI assistant with access to various tools. Be concise and helpful."},
        {"role": "user", "content": req.message},
    ]
    
    tools_used = []
    response_text = ""
    
    # Tool loop
    for _ in range(req.max_iterations):
        try:
            response = await chat(messages, tools=get_tools(), temperature=0.7)
        except Exception as e:
            log_activity(f"LLM error: {e}")
            return ChatResponse(
                response=f"⚠️ LLM Error: {e}",
                tools_used=tools_used,
                duration=time.time() - start,
            )
        
        messages.append(response)
        
        tool_calls = response.get("tool_calls")
        if not tool_calls:
            response_text = response.get("content", "")
            break
        
        for tc in tool_calls:
            func_name = tc["function"]["name"]
            tools_used.append(func_name)
            
            await broadcast({"type": "tool_call", "tool": func_name, "preview": tc["function"]["arguments"][:80]})
            log_activity(f"Tool: {func_name}")
            
            result = await execute_tool(func_name, tc["function"]["arguments"])
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(result, ensure_ascii=False, default=str)[:4000],
            })
    
    # Apply reflection
    reflected = False
    if req.reflection and response_text:
        try:
            reflected_result = await agent_reflect(
                user_query=req.message,
                initial_response=response_text,
                enabled=True,
                max_rounds=1,
            )
            if reflected_result["reflected"]:
                response_text = reflected_result["response"]
                reflected = True
        except Exception:
            pass
    
    # Save to memory
    if response_text and len(response_text) > 50:
        short_term.add({"role": "assistant", "content": response_text})
    
    duration = time.time() - start
    log_activity(f"Response sent ({duration:.1f}s, {len(tools_used)} tools)")
    
    await broadcast({"type": "chat_response", "content": response_text})
    
    return ChatResponse(
        response=response_text,
        tools_used=tools_used,
        reflected=reflected,
        duration=duration,
    )

# ---------------------------------------------------------------------------
# Routes: Stats
# ---------------------------------------------------------------------------

@app.get("/api/stats")
async def get_stats():
    """Get agent statistics."""
    try:
        _, provider, model = get_client()
        provider_str = f"{provider}/{model}"
    except Exception:
        provider_str = "not configured"
    
    return {
        "memories": len(long_term.recent(1000)),
        "procedures": len(procedural.all_procedures()),
        "tools_count": len(get_tools()),
        "requests": request_count,
        "provider": provider_str,
        "uptime": f"{int(time.time() - start_time) // 60}m {(int(time.time() - start_time) % 60)}s",
    }

# ---------------------------------------------------------------------------
# Routes: Activity
# ---------------------------------------------------------------------------

@app.get("/api/activity")
async def get_activity():
    """Get recent activity log."""
    return {"activities": activity_log[:20]}

# ---------------------------------------------------------------------------
# Routes: Memories
# ---------------------------------------------------------------------------

@app.get("/api/memories")
async def get_memories():
    """Get long-term memories."""
    memories = long_term.recent(20)
    return {
        "memories": [
            {"text": m.text[:200], "source": m.source, "importance": m.importance}
            for m in memories
        ]
    }

@app.post("/api/memories")
async def add_memory(req: MemoryRequest):
    """Add a new memory."""
    entry = MemoryEntry(text=req.text, tags=req.tags, importance=req.importance)
    long_term.add(entry)
    log_activity(f"Memory saved: {req.text[:50]}...")
    return {"status": "saved", "id": len(long_term.recent(1000))}

# ---------------------------------------------------------------------------
# Routes: Events
# ---------------------------------------------------------------------------

@app.get("/api/events")
async def get_events():
    """Get event rules."""
    from events import rule_store
    rules = rule_store.all_rules()
    return {
        "rules": [
            {"name": r.name, "event_type": r.event_type, "condition": r.condition, "action": r.action, "enabled": r.enabled}
            for r in rules
        ]
    }

@app.post("/api/events")
async def add_event(req: EventRuleRequest):
    """Add an event rule."""
    from events import add_event_rule
    result = await add_event_rule(req.name, req.event_type, req.condition, req.action, req.cooldown)
    log_activity(f"Event rule added: {req.name}")
    return result

@app.get("/api/events/recent")
async def get_recent_events():
    """Get recent system events."""
    result = await list_recent_events()
    return result

# ---------------------------------------------------------------------------
# Routes: Cron
# ---------------------------------------------------------------------------

@app.get("/api/cron")
async def get_cron():
    """Get cron jobs."""
    return {"jobs": list_cron_jobs()}

# ---------------------------------------------------------------------------
# Routes: Models
# ---------------------------------------------------------------------------

@app.get("/api/models")
async def get_models():
    """Get available models from all providers."""
    from llm import list_providers, fetch_models_from_provider
    providers = list_providers()
    available = [p for p in providers if p["available"]]
    result = []
    for p in available:
        try:
            live = await fetch_models_from_provider(p["id"])
        except Exception:
            live = p["models"]
        if not live:
            live = p["models"]
        result.append({
            "provider": p["id"],
            "display_name": p["display_name"],
            "models": live[:50],
        })
    return {"providers": result}

@app.get("/api/models/switch")
async def switch_model(provider: str, model: str):
    """Switch the active model for the session."""
    from llm import set_session_provider
    result = set_session_provider(provider, model)
    return result

# ---------------------------------------------------------------------------
# Routes: Git
# ---------------------------------------------------------------------------

@app.get("/api/git/snapshots")
async def get_git_snapshots():
    """Get git evolution snapshots."""
    result = await git_list_snapshots()
    return result

@app.post("/api/git/save")
async def save_git_state(label: str = "api-save"):
    """Save agent state to git."""
    result = await git_save_state(label)
    log_activity(f"Git state saved: {label}")
    return result

# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time communication."""
    await websocket.accept()
    websocket_clients.append(websocket)
    
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming WebSocket messages
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        websocket_clients.remove(websocket)

# ---------------------------------------------------------------------------
# Startup/shutdown events
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    log_activity("API server started")
    # Check provider status
    try:
        from llm import _resolve_provider
        pname, cfg, model = _resolve_provider()
        log_activity(f"LLM provider: {pname} / {model}")
    except Exception as e:
        log_activity(f"LLM provider error: {e}")
    await broadcast({"type": "activity", "time": datetime.now().strftime("%H:%M:%S"), "text": "Server started"})

@app.on_event("shutdown")
async def shutdown():
    log_activity("API server shutting down")

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    print(f"🚀 Starting AI Agent API server on {host}:{port}")
    print(f"📊 Dashboard: http://localhost:{port}")
    print(f"📡 API: http://localhost:{port}/api")
    print(f"🔌 WebSocket: ws://localhost:{port}/ws")
    
    uvicorn.run(app, host=host, port=port)
