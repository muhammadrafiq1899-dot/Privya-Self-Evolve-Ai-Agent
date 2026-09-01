"""
voice.py – Voice I/O for hands-free agent interaction.

Speech-to-Text (STT):
- Groq Whisper API (fastest, requires GROQ_API_KEY)
- Local fallback via termux-speech-to-text

Text-to-Speech (TTS):
- termux-tts (native, requires termux-api)
- edge-tts (Microsoft Edge, free, high quality)
"""

from __future__ import annotations

import asyncio
import io
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Speech-to-Text via Groq Whisper
# ---------------------------------------------------------------------------

async def stt_groq(
    audio_path: str | None = None,
    audio_bytes: bytes | None = None,
    language: str = "en",
) -> dict[str, Any]:
    """Transcribe audio using Groq's Whisper API.

    Args:
        audio_path: Path to audio file (WAV, MP3, M4A, WEBM, MP4, MPEG, MPGA, OGA, OGGA, FLAC)
        audio_bytes: Raw audio bytes (alternative to path)
        language: ISO language code (default: "en")

    Returns:
        {"text": str, "language": str, "duration": float} or {"error": str}
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return {"error": "GROQ_API_KEY required for Whisper STT"}

    # Read audio data
    if audio_path:
        path = Path(audio_path).expanduser().resolve()
        if not path.exists():
            return {"error": f"Audio file not found: {audio_path}"}
        audio_data = path.read_bytes()
        filename = path.name
    elif audio_bytes:
        audio_data = audio_bytes
        filename = "recording.wav"
    else:
        return {"error": "Provide audio_path or audio_bytes"}

    # Determine MIME type
    ext = Path(filename).suffix.lower()
    mime_map = {
        ".wav": "audio/wav", ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4", ".webm": "audio/webm",
        ".mp4": "audio/mp4", ".flac": "audio/flac",
        ".ogg": "audio/ogg", ".oga": "audio/ogg",
    }
    content_type = mime_map.get(ext, "audio/wav")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (filename, audio_data, content_type)},
                data={"model": "whisper-large-v3", "language": language, "response_format": "verbose_json"},
            )
            resp.raise_for_status()
            result = resp.json()
            return {
                "text": result.get("text", ""),
                "language": result.get("language", language),
                "duration": result.get("duration", 0),
            }
    except httpx.HTTPStatusError as e:
        return {"error": f"Groq API error: {e.response.status_code} {e.response.text[:200]}"}
    except Exception as e:
        return {"error": f"STT error: {e}"}


# ---------------------------------------------------------------------------
# Termux speech-to-text (offline fallback)
# ---------------------------------------------------------------------------

async def stt_termux() -> dict[str, Any]:
    """Use Termux's built-in speech recognition (uses Google's API)."""
    if not shutil.which("termux-speech-to-text"):
        return {"error": "termux-speech-to-text not available. Install termux-api."}

    try:
        proc = await asyncio.create_subprocess_shell(
            "termux-speech-to-text",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        text = stdout.decode("utf-8", errors="replace").strip()
        if text:
            return {"text": text, "language": "auto", "source": "termux"}
        return {"error": "No speech detected"}
    except asyncio.TimeoutError:
        return {"error": "Speech recognition timed out (30s)"}
    except Exception as e:
        return {"error": f"Termux STT error: {e}"}


# ---------------------------------------------------------------------------
# Text-to-Speech via Termux
# ---------------------------------------------------------------------------

async def tts_termux(
    text: str,
    engine: str | None = None,
    language: str = "en",
    pitch: float = 1.0,
    rate: float = 1.0,
) -> dict[str, Any]:
    """Speak text using Termux TTS.

    Args:
        text: Text to speak
        engine: TTS engine name (optional)
        language: Language code
        pitch: Speech pitch (0.5-2.0)
        rate: Speech rate (0.5-2.0)
    """
    if not shutil.which("termux-tts-speak"):
        return {"error": "termux-tts-speak not available. Install termux-api."}

    cmd = f'termux-tts-speak -l {language} -p {pitch} -r {rate}'
    if engine:
        cmd += f' -e {engine}'
    cmd += f' "{text}"'

    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=30)
        return {"result": "Speech played", "text": text}
    except Exception as e:
        return {"error": f"TTS error: {e}"}


# ---------------------------------------------------------------------------
# Text-to-Speech via edge-tts (high quality, no API key)
# ---------------------------------------------------------------------------

async def tts_edge(
    text: str,
    voice: str = "en-US-AriaNeural",
    output_path: str | None = None,
) -> dict[str, Any]:
    """Generate speech audio using Microsoft Edge TTS (free, high quality).

    Args:
        text: Text to speak
        voice: Voice name (see edge-tts --list-voices)
        output_path: Save audio to this path (optional)

    Returns:
        {"result": str, "audio_path": str} or {"error": str}
    """
    try:
        import edge_tts
    except ImportError:
        return {"error": "edge-tts not installed. Run: pip install edge-tts"}

    if not output_path:
        output_path = str(Path(tempfile.gettempdir()) / f"tts_{hash(text) & 0xFFFFFFFF}.mp3")

    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
        return {"result": "Speech generated", "audio_path": output_path, "text": text}
    except Exception as e:
        return {"error": f"Edge TTS error: {e}"}


# ---------------------------------------------------------------------------
# Listen loop (record → transcribe → return)
# ---------------------------------------------------------------------------

async def listen(
    duration: int = 10,
    source: str = "termux",
    language: str = "en",
) -> dict[str, Any]:
    """Record audio and transcribe it.

    Args:
        duration: Recording duration in seconds (for termux-microphone-record)
        source: "groq" for Whisper API, "termux" for device speech recognition
        language: Language code for Groq

    Returns:
        {"text": str, "source": str} or {"error": str}
    """
    if source == "termux":
        return await stt_termux()

    # Record audio via termux
    if not shutil.which("termux-microphone-record"):
        return {"error": "termux-microphone-record not available"}

    recording_path = str(Path(tempfile.gettempdir()) / "voice_recording.wav")
    try:
        # Record audio
        proc = await asyncio.create_subprocess_shell(
            f'termux-microphone-record -f {recording_path} -l {duration}s',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=duration + 5)

        # Transcribe
        return await stt_groq(audio_path=recording_path, language=language)
    except Exception as e:
        return {"error": f"Listen error: {e}"}


# ---------------------------------------------------------------------------
# Voice chat convenience
# ---------------------------------------------------------------------------

async def voice_chat(
    agent_response_text: str,
    speak: bool = True,
    voice: str = "en-US-AriaNeural",
) -> dict[str, Any]:
    """Speak the agent's response aloud.

    Args:
        agent_response_text: The text to speak
        speak: Whether to actually speak (can be disabled)
        voice: Edge TTS voice name
    """
    if not speak:
        return {"result": "Speech disabled"}

    # Try Termux TTS first, fall back to edge-tts
    if shutil.which("termux-tts-speak"):
        return await tts_termux(agent_response_text)
    else:
        return await tts_edge(agent_response_text, voice=voice)


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

VOICE_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "speech_to_text",
            "description": "Transcribe audio from a file or recording. Supports WAV, MP3, M4A, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "audio_path": {"type": "string", "description": "Path to audio file"},
                    "language": {"type": "string", "description": "Language code (default: en)"},
                },
                "required": ["audio_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listen",
            "description": "Listen to the user's voice (record + transcribe). Best used in hands-free mode.",
            "parameters": {
                "type": "object",
                "properties": {
                    "duration": {"type": "integer", "description": "Recording duration in seconds (default 10)"},
                    "language": {"type": "string", "description": "Language code (default: en)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "text_to_speech",
            "description": "Speak text aloud using TTS. Use for reading responses, notifications, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to speak"},
                    "voice": {"type": "string", "description": "Voice name (default: en-US-AriaNeural)"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "voice_chat",
            "description": "Speak the agent's response aloud using TTS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to speak"},
                    "voice": {"type": "string", "description": "Voice name"},
                },
                "required": ["text"],
            },
        },
    },
]


VOICE_TOOL_MAP = {
    "speech_to_text": stt_groq,
    "listen": listen,
    "text_to_speech": tts_edge,
    "voice_chat": voice_chat,
}
