"""
events.py – Event-driven proactivity system.

Instead of waiting for user input or cron jobs, the agent can:
1. Monitor system events (battery, SMS, location changes)
2. React to conditions (battery < 15%, received 2FA code)
3. Execute automated responses (turn on battery saver, extract code)

Runs as background listeners that trigger agent actions.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Awaitable, Optional

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(os.getenv("AGENT_DATA_DIR", Path.home() / ".ai-agent"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
EVENT_LOG = DATA_DIR / "events.jsonl"
RULES_FILE = DATA_DIR / "event_rules.json"

# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

class EventType:
    BATTERY = "battery"
    SMS_RECEIVED = "sms_received"
    LOCATION_CHANGE = "location_change"
    TIME = "time"
    IDLE = "idle"
    APP_FOREGROUND = "app_foreground"
    CHARGING = "charging"
    CUSTOM = "custom"


@dataclass
class Event:
    type: str
    data: dict[str, Any]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EventRule:
    name: str
    event_type: str
    condition: str  # Natural language condition
    action: str  # Natural language action or tool call
    enabled: bool = True
    cooldown: int = 300  # Seconds between triggers
    last_triggered: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EventRule":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Event rules store
# ---------------------------------------------------------------------------

class EventRuleStore:
    """Persistent storage for event rules."""

    def __init__(self, path: Path = RULES_FILE):
        self.path = path
        self._rules: list[EventRule] | None = None

    def _load(self) -> list[EventRule]:
        if self._rules is not None:
            return self._rules
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text("utf-8"))
                self._rules = [EventRule.from_dict(r) for r in data]
            except (json.JSONDecodeError, OSError):
                self._rules = []
        else:
            self._rules = []
        return self._rules

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([r.to_dict() for r in self._rules], indent=2, ensure_ascii=False),
            "utf-8",
        )

    def add(self, rule: EventRule) -> None:
        self._load()
        self._rules.append(rule)
        self._save()

    def remove(self, name: str) -> bool:
        self._load()
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.name != name]
        if len(self._rules) < before:
            self._save()
            return True
        return False

    def get_enabled(self) -> list[EventRule]:
        return [r for r in self._load() if r.enabled]

    def all_rules(self) -> list[EventRule]:
        return self._load()

    def mark_triggered(self, name: str) -> None:
        self._load()
        for r in self._rules:
            if r.name == name:
                r.last_triggered = time.time()
                break
        self._save()


# ---------------------------------------------------------------------------
# Event listeners
# ---------------------------------------------------------------------------

class EventListener:
    """Background event listener that monitors conditions and triggers actions."""

    def __init__(self):
        self.rules = EventRuleStore()
        self._running = False
        self._handlers: dict[str, list[Callable]] = {}
        self._event_log: list[Event] = []

    def on(self, event_type: str, handler: Callable[..., Awaitable]) -> None:
        """Register a handler for an event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    async def emit(self, event: Event) -> None:
        """Emit an event to all registered handlers."""
        self._event_log.append(event)
        if len(self._event_log) > 1000:
            self._event_log = self._event_log[-500:]

        # Log event
        self._log_event(event)

        # Check rules
        for rule in self.rules.get_enabled():
            if rule.event_type == event.type or rule.event_type == "any":
                if self._check_condition(rule, event):
                    if self._check_cooldown(rule):
                        await self._execute_action(rule, event)

        # Call registered handlers
        for handler in self._handlers.get(event.type, []):
            try:
                await handler(event)
            except Exception as e:
                print(f"Event handler error: {e}")

    def _check_condition(self, rule: EventRule, event: Event) -> bool:
        """Check if an event meets a rule's condition."""
        cond = rule.condition.lower()
        data = event.data

        # Battery conditions
        if "battery" in cond and event.type == EventType.BATTERY:
            level = data.get("level", 100)
            if "below" in cond or "<" in cond:
                threshold = self._extract_number(cond)
                return level < threshold if threshold else level < 20
            if "above" in cond or ">" in cond:
                threshold = self._extract_number(cond)
                return level > threshold if threshold else level > 80

        # SMS conditions
        if "sms" in cond or "message" in cond:
            if event.type == EventType.SMS_RECEIVED:
                if "2fa" in cond or "code" in cond or "verification" in cond:
                    msg = data.get("message", "")
                    return bool(re.search(r'\b\d{4,8}\b', msg))
                if "contains" in cond:
                    keyword = cond.split("contains")[-1].strip()
                    return keyword in data.get("message", "").lower()

        # Time conditions
        if event.type == EventType.TIME:
            return True  # Time events always match

        # Charging
        if "charging" in cond:
            return data.get("charging", False)

        # Default: match if condition is empty or "any"
        return not cond or cond == "any"

    def _check_cooldown(self, rule: EventRule) -> bool:
        """Check if enough time has passed since last trigger."""
        elapsed = time.time() - rule.last_triggered
        return elapsed >= rule.cooldown

    def _extract_number(self, text: str) -> float | None:
        """Extract a number from text."""
        import re
        match = re.search(r'(\d+)', text)
        return float(match.group(1)) if match else None

    async def _execute_action(self, rule: EventRule, event: Event) -> None:
        """Execute a rule's action."""
        from llm import chat

        # Mark as triggered
        self.rules.mark_triggered(rule.name)

        # Build action prompt
        prompt = (
            f"Event occurred: {rule.event_type}\n"
            f"Event data: {json.dumps(event.data, indent=2)}\n"
            f"Rule: {rule.name}\n"
            f"Condition: {rule.condition}\n"
            f"Action to take: {rule.action}\n\n"
            f"Execute the described action using the available tools. Be concise."
        )

        messages = [
            {"role": "system", "content": "You are an automated agent responding to system events. Execute the described action."},
            {"role": "user", "content": prompt},
        ]

        try:
            from tools import get_tools, execute_tool
            response = await chat(messages, tools=get_tools(), temperature=0.3, max_tokens=1000)

            # Execute any tool calls
            tool_calls = response.get("tool_calls", [])
            for tc in tool_calls:
                result = await execute_tool(tc["function"]["name"], tc["function"]["arguments"])
                self._log_action(rule.name, tc["function"]["name"], result)

        except Exception as e:
            self._log_action(rule.name, "error", {"error": str(e)})

    def _log_event(self, event: Event) -> None:
        """Log event to file."""
        try:
            with EVENT_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _log_action(self, rule_name: str, action: str, result: dict) -> None:
        """Log action execution."""
        log_entry = {
            "timestamp": time.time(),
            "rule": rule_name,
            "action": action,
            "result": result,
        }
        try:
            log_path = DATA_DIR / "event_actions.jsonl"
            with log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def recent_events(self, n: int = 20) -> list[Event]:
        """Get recent events."""
        return self._event_log[-n:]


# ---------------------------------------------------------------------------
# Background monitor tasks
# ---------------------------------------------------------------------------

async def battery_monitor(listener: EventListener, interval: int = 60):
    """Continuously monitor battery level."""
    try:
        from termux_hardware import battery_status
    except ImportError:
        return

    while True:
        try:
            result = await battery_status()
            if "result" in result:
                data = result["result"]
                await listener.emit(Event(
                    type=EventType.BATTERY,
                    data={
                        "level": data.get("percentage", 100),
                        "charging": data.get("status", "") == "CHARGING",
                        "temperature": data.get("temperature", 0),
                    },
                ))
        except Exception:
            pass
        await asyncio.sleep(interval)


async def sms_monitor(listener: EventListener, interval: int = 30):
    """Monitor for new SMS messages."""
    try:
        from termux_hardware import read_sms
    except ImportError:
        return

    last_id = None
    while True:
        try:
            result = await read_sms(limit=1)
            if "result" in result:
                messages = result["result"]
                if messages and isinstance(messages, list):
                    latest = messages[0]
                    msg_id = latest.get("received", "")
                    if msg_id != last_id:
                        last_id = msg_id
                        await listener.emit(Event(
                            type=EventType.SMS_RECEIVED,
                            data={
                                "from": latest.get("number", ""),
                                "message": latest.get("body", ""),
                                "timestamp": latest.get("received", ""),
                            },
                        ))
        except Exception:
            pass
        await asyncio.sleep(interval)


async def idle_detector(listener: EventListener, timeout: int = 300):
    """Detect when the agent has been idle for too long."""
    last_activity = time.time()

    while True:
        idle_time = time.time() - last_activity
        if idle_time > timeout:
            await listener.emit(Event(
                type=EventType.IDLE,
                data={"idle_seconds": int(idle_time)},
            ))
            last_activity = time.time()  # Reset after emit
        await asyncio.sleep(30)


# ---------------------------------------------------------------------------
# Rule management tools
# ---------------------------------------------------------------------------

rule_store = EventRuleStore()
event_listener = EventListener()


async def add_event_rule(
    name: str,
    event_type: str,
    condition: str,
    action: str,
    cooldown: int = 300,
) -> dict[str, Any]:
    """Add an event-driven rule."""
    rule = EventRule(
        name=name,
        event_type=event_type,
        condition=condition,
        action=action,
        cooldown=cooldown,
    )
    rule_store.add(rule)
    return {"result": f"Rule '{name}' added: when {condition} → {action}"}


async def remove_event_rule(name: str) -> dict[str, Any]:
    """Remove an event rule."""
    if rule_store.remove(name):
        return {"result": f"Rule '{name}' removed."}
    return {"error": f"Rule '{name}' not found."}


async def list_event_rules() -> dict[str, Any]:
    """List all event rules."""
    rules = rule_store.all_rules()
    if not rules:
        return {"result": "No event rules configured."}

    lines = []
    for r in rules:
        status = "✅" if r.enabled else "❌"
        lines.append(f"{status} {r.name}: [{r.event_type}] when {r.condition} → {r.action}")
    return {"result": "\n".join(lines)}


async def list_recent_events(n: int = 10) -> dict[str, Any]:
    """List recent events."""
    events = event_listener.recent_events(n)
    if not events:
        return {"result": "No recent events."}

    lines = []
    for e in events:
        ts = time.strftime("%H:%M:%S", time.localtime(e.timestamp))
        lines.append(f"[{ts}] {e.type}: {json.dumps(e.data)[:100]}")
    return {"result": "\n".join(lines)}


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

EVENT_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "add_event_rule",
            "description": "Create an event-driven automation rule. The agent will react when conditions are met.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Rule name"},
                    "event_type": {"type": "string", "enum": ["battery", "sms_received", "location_change", "time", "charging", "any"], "description": "Type of event to listen for"},
                    "condition": {"type": "string", "description": "Natural language condition (e.g. 'battery below 15%', 'sms contains 2fa code')"},
                    "action": {"type": "string", "description": "What to do when triggered (e.g. 'turn on battery saver and text my wife')"},
                    "cooldown": {"type": "integer", "description": "Minimum seconds between triggers (default 300)"},
                },
                "required": ["name", "event_type", "condition", "action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_event_rule",
            "description": "Remove an event-driven automation rule.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Rule name to remove"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_event_rules",
            "description": "List all configured event-driven rules.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_recent_events",
            "description": "Show recent system events that have been detected.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of events to show (default 10)"},
                },
            },
        },
    },
]

EVENT_TOOL_MAP = {
    "add_event_rule": add_event_rule,
    "remove_event_rule": remove_event_rule,
    "list_event_rules": list_event_rules,
    "list_recent_events": list_recent_events,
}


# ---------------------------------------------------------------------------
# Background monitor manager
# ---------------------------------------------------------------------------

class MonitorManager:
    """Manages background monitoring tasks."""

    def __init__(self, listener: EventListener):
        self.listener = listener
        self._tasks: list[asyncio.Task] = []

    async def start(self, monitors: list[str] | None = None):
        """Start background monitors."""
        available = {
            "battery": lambda: battery_monitor(self.listener, interval=60),
            "sms": lambda: sms_monitor(self.listener, interval=30),
            "idle": lambda: idle_detector(self.listener, timeout=300),
        }

        targets = monitors or list(available.keys())
        for name in targets:
            if name in available:
                task = asyncio.create_task(available[name]())
                self._tasks.append(task)

    async def stop(self):
        """Stop all monitors."""
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()


monitor_manager = MonitorManager(event_listener)
