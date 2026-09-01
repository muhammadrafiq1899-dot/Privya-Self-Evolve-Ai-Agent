"""
termux_hardware.py – Termux:API hardware access tools.

Provides tools for interacting with Android hardware via termux-api:
- Battery status
- GPS location
- SMS read/send
- Camera (photo/video)
- Device info (vibrate, ringtone, clipboard)
- Sensor readings (accelerometer, gyroscope)

Requires: pkg install termux-api (in Termux)
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Check if termux-api is available
# ---------------------------------------------------------------------------

TERMUX_API_AVAILABLE = shutil.which("termux-api-start") is not None or shutil.which("termux-battery-status") is not None


def _check_termux() -> str | None:
    """Return error message if termux-api is not available."""
    if not TERMUX_API_AVAILABLE:
        return "termux-api not installed. Run: pkg install termux-api"
    return None


async def _run_termux(cmd: str, timeout: int = 15) -> dict[str, Any]:
    """Run a termux-api command and return parsed output."""
    err = _check_termux()
    if err:
        return {"error": err}

    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        stdout_str = stdout.decode("utf-8", errors="replace").strip()
        stderr_str = stderr.decode("utf-8", errors="replace").strip()

        # Try to parse JSON output
        try:
            data = json.loads(stdout_str)
            return {"result": data}
        except (json.JSONDecodeError, ValueError):
            return {"result": stdout_str if stdout_str else stderr_str}

    except asyncio.TimeoutError:
        return {"error": f"Command timed out ({timeout}s): {cmd}"}
    except Exception as e:
        return {"error": f"Termux API error: {e}"}


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

async def battery_status() -> dict[str, Any]:
    """Get battery level, status, and temperature."""
    return await _run_termux("termux-battery-status")


async def get_location(provider: str = "gps") -> dict[str, Any]:
    """Get GPS location. provider: gps, network, passive."""
    return await _run_termux(f"termux-location -p {provider}", timeout=30)


async def get_gps() -> dict[str, Any]:
    """Get GPS coordinates (convenience wrapper)."""
    return await get_location("gps")


async def send_sms(number: str, message: str) -> dict[str, Any]:
    """Send an SMS message."""
    return await _run_termux(f'termux-sms-send -n "{number}" "{message}"')


async def read_sms(limit: int = 10, inbox: bool = True) -> dict[str, Any]:
    """Read recent SMS messages."""
    flag = "-i" if inbox else ""
    return await _run_termux(f"termux-sms-list {flag} -l {limit}")


async def take_photo(output_path: str | None = None) -> dict[str, Any]:
    """Take a photo using the camera. Returns file path."""
    if not output_path:
        output_path = str(Path(tempfile.gettempdir()) / f"photo_{int(asyncio.get_event_loop().time())}.jpg")
    result = await _run_termux(f'termux-camera-photo "{output_path}"', timeout=30)
    if "error" not in result:
        result["file_path"] = output_path
    return result


async def take_photo_back() -> dict[str, Any]:
    """Take a photo with the back camera."""
    output_path = str(Path(tempfile.gettempdir()) / f"photo_back_{int(asyncio.get_event_loop().time())}.jpg")
    return await _run_termux(f'termux-camera-photo -c 0 "{output_path}"', timeout=30)


async def take_photo_front() -> dict[str, Any]:
    """Take a photo with the front camera."""
    output_path = str(Path(tempfile.gettempdir()) / f"photo_front_{int(asyncio.get_event_loop().time())}.jpg")
    return await _run_termux(f'termux-camera-photo -c 1 "{output_path}"', timeout=30)


async def record_video(duration: int = 10, quality: int = 720) -> dict[str, Any]:
    """Record a video."""
    output_path = str(Path(tempfile.gettempdir()) / f"video_{int(asyncio.get_event_loop().time())}.mp4")
    return await _run_termux(f'termux-camera-video -l {duration} -q {quality} "{output_path}"', timeout=duration + 10)


async def vibrate(duration: int = 200) -> dict[str, Any]:
    """Vibrate the device."""
    return await _run_termux(f"termux-vibrate -d {duration}")


async def get_device_info() -> dict[str, Any]:
    """Get comprehensive device information."""
    results = {}
    for cmd, key in [
        ("termux-battery-status", "battery"),
        ("termux-location -p network", "location"),
        ("termux-wallpaper-info 2>/dev/null || echo '{}'", "wallpaper"),
        ("termux-getprop ro.product.model", "model"),
        ("termux-getprop ro.build.version.sdk", "android_version"),
    ]:
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            text = stdout.decode("utf-8", errors="replace").strip()
            try:
                results[key] = json.loads(text)
            except (json.JSONDecodeError, ValueError):
                results[key] = text
        except Exception:
            results[key] = "unavailable"
    return {"result": results}


async def get_clipboard() -> dict[str, Any]:
    """Get clipboard content."""
    return await _run_termux("termux-clipboard-get")


async def set_clipboard(text: str) -> dict[str, Any]:
    """Set clipboard content."""
    return await _run_termux(f'termux-clipboard-set "{text}"')


async def get_wifi_info() -> dict[str, Any]:
    """Get WiFi connection info."""
    return await _run_termux("termux-wifi-connectioninfo")


async def get_sensor(sensor_name: str = "accelerometer", delay: int = 200) -> dict[str, Any]:
    """Read sensor data. Sensors: accelerometer, gyroscope, magnetic_field, etc."""
    return await _run_termux(f"termux-sensor -s {sensor_name} -d {delay} -n 1", timeout=10)


async def get_brightness() -> dict[str, Any]:
    """Get current screen brightness."""
    return await _run_termux("termux-brightness ?")


async def set_brightness(level: int) -> dict[str, Any]:
    """Set screen brightness (0-255)."""
    level = max(0, min(255, level))
    return await _run_termux(f"termux-brightness {level}")


async def notification(title: str, content: str) -> dict[str, Any]:
    """Show a notification."""
    return await _run_termux(f'termux-notification -t "{title}" -c "{content}"')


async def toast(message: str, duration: str = "short") -> dict[str, Any]:
    """Show a toast message."""
    return await _run_termux(f'termux-toast -s "{message}" -d {duration}')


# ---------------------------------------------------------------------------
# Tool schemas for OpenAI function calling
# ---------------------------------------------------------------------------

HARDWARE_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "battery_status",
            "description": "Get battery level, charging status, and temperature.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_location",
            "description": "Get GPS coordinates (latitude, longitude). Requires location permission.",
            "parameters": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string", "enum": ["gps", "network", "passive"], "description": "Location provider (default: gps)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_sms",
            "description": "Send an SMS message to a phone number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "number": {"type": "string", "description": "Phone number to send to"},
                    "message": {"type": "string", "description": "Message content"},
                },
                "required": ["number", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_sms",
            "description": "Read recent SMS messages from inbox or outbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of messages to read (default 10)"},
                    "inbox": {"type": "boolean", "description": "True for inbox, false for outbox"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_photo",
            "description": "Take a photo with the device camera. Returns file path of the captured image.",
            "parameters": {
                "type": "object",
                "properties": {
                    "camera": {"type": "string", "enum": ["back", "front"], "description": "Which camera to use (default: back)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "vibrate",
            "description": "Vibrate the device for a specified duration.",
            "parameters": {
                "type": "object",
                "properties": {
                    "duration": {"type": "integer", "description": "Duration in milliseconds (default: 200)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_device_info",
            "description": "Get comprehensive device info (model, Android version, battery, location).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_clipboard",
            "description": "Get the current clipboard content.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_clipboard",
            "description": "Set the clipboard content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to set in clipboard"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_wifi_info",
            "description": "Get current WiFi connection information.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notification",
            "description": "Show a notification on the device.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Notification title"},
                    "content": {"type": "string", "description": "Notification content"},
                },
                "required": ["title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "toast",
            "description": "Show a brief toast message on screen.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Toast message"},
                },
                "required": ["message"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------

HARDWARE_TOOL_MAP = {
    "battery_status": battery_status,
    "get_location": get_location,
    "get_gps": get_gps,
    "send_sms": send_sms,
    "read_sms": read_sms,
    "take_photo": take_photo,
    "vibrate": vibrate,
    "get_device_info": get_device_info,
    "get_clipboard": get_clipboard,
    "set_clipboard": set_clipboard,
    "get_wifi_info": get_wifi_info,
    "get_sensor": get_sensor,
    "notification": notification,
    "toast": toast,
}
