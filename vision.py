"""
vision.py – Vision & multimodal support.

Supports image analysis via:
- Gemini 1.5 Pro/Flash (native vision)
- Claude 3.5 Sonnet (via OpenRouter)
- GPT-4o (via OpenRouter)

Handles image encoding, file-to-base64 conversion, and vision prompt construction.
"""

from __future__ import annotations

import asyncio
import base64
import mimetypes
import os
from pathlib import Path
from typing import Any, Optional

import httpx
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

from llm import get_client, PROVIDERS


# ---------------------------------------------------------------------------
# Image encoding utilities
# ---------------------------------------------------------------------------

def encode_image_base64(image_path: str) -> str | None:
    """Read and base64-encode an image file."""
    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        return None


def get_mime_type(image_path: str) -> str:
    """Get MIME type for an image file."""
    mime, _ = mimetypes.guess_type(image_path)
    return mime or "image/jpeg"


def image_to_content(image_path: str, detail: str = "auto") -> dict[str, Any] | None:
    """Convert an image path to OpenAI vision content block."""
    b64 = encode_image_base64(image_path)
    if not b64:
        return None

    mime = get_mime_type(image_path)
    return {
        "type": "image_url",
        "image_url": {
            "url": f"data:{mime};base64,{b64}",
            "detail": detail,
        },
    }


def url_to_content(url: str, detail: str = "auto") -> dict[str, Any]:
    """Convert a URL to OpenAI vision content block."""
    return {
        "type": "image_url",
        "image_url": {
            "url": url,
            "detail": detail,
        },
    }


# ---------------------------------------------------------------------------
# Vision analysis functions
# ---------------------------------------------------------------------------

async def analyze_image(
    image_path: str,
    prompt: str = "Describe this image in detail.",
    provider: str | None = None,
    detail: str = "auto",
) -> dict[str, Any]:
    """Analyze an image with a vision-capable model.

    Args:
        image_path: Local file path to the image
        prompt: Question/instruction about the image
        provider: LLM provider (auto-selected if None)
        detail: Image detail level ("low", "high", "auto")

    Returns:
        {"result": str, "error": str | None}
    """
    # Check if image exists
    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        return {"result": "", "error": f"Image not found: {image_path}"}

    # Encode image
    content_block = image_to_content(str(path), detail=detail)
    if not content_block:
        return {"result": "", "error": f"Failed to encode image: {image_path}"}

    # Build messages with image
    messages = [
        {
            "role": "user",
            "content": [
                content_block,
                {"type": "text", "text": prompt},
            ],
        }
    ]

    try:
        client, pname, model = get_client(provider)
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=2000,
            temperature=0.3,
        )
        text = response.choices[0].message.content or ""
        return {"result": text}
    except Exception as e:
        return {"result": "", "error": f"Vision analysis error: {e}"}


async def analyze_image_url(
    image_url: str,
    prompt: str = "Describe this image in detail.",
    provider: str | None = None,
    detail: str = "auto",
) -> dict[str, Any]:
    """Analyze an image from a URL."""
    content_block = url_to_content(image_url, detail=detail)

    messages = [
        {
            "role": "user",
            "content": [
                content_block,
                {"type": "text", "text": prompt},
            ],
        }
    ]

    try:
        client, pname, model = get_client(provider)
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=2000,
            temperature=0.3,
        )
        text = response.choices[0].message.content or ""
        return {"result": text}
    except Exception as e:
        return {"result": "", "error": f"Vision analysis error: {e}"}


async def take_and_analyze(
    prompt: str = "Describe what you see.",
    camera: str = "back",
    provider: str | None = None,
) -> dict[str, Any]:
    """Take a photo and immediately analyze it.

    Combines termux-camera-photo with vision analysis.
    """
    try:
        from termux_hardware import take_photo, take_photo_front, take_photo_back
    except ImportError:
        return {"result": "", "error": "termux_hardware module not available"}

    # Take photo
    if camera == "front":
        photo_result = await take_photo_front()
    else:
        photo_result = await take_photo_back()

    if "error" in photo_result:
        return {"result": "", "error": f"Failed to take photo: {photo_result['error']}"}

    file_path = photo_result.get("file_path")
    if not file_path:
        return {"result": "", "error": "No file path returned from camera"}

    # Analyze
    return await analyze_image(file_path, prompt, provider=provider)


# ---------------------------------------------------------------------------
# OCR (Optical Character Recognition) via vision model
# ---------------------------------------------------------------------------

async def ocr_image(
    image_path: str,
    provider: str | None = None,
) -> dict[str, Any]:
    """Extract text from an image using vision model as OCR."""
    prompt = (
        "Extract ALL visible text from this image. "
        "Output ONLY the extracted text, preserving the original formatting and layout. "
        "Do not add any commentary or description."
    )
    return await analyze_image(image_path, prompt, provider=provider, detail="high")


async def read_handwriting(
    image_path: str,
    provider: str | None = None,
) -> dict[str, Any]:
    """Read handwritten text from an image."""
    prompt = (
        "This is a handwritten note. Please transcribe all the handwritten text. "
        "Output ONLY the transcribed text. If you're unsure about a word, "
        "put it in [brackets]. Preserve line breaks and any structure."
    )
    return await analyze_image(image_path, prompt, provider=provider, detail="high")


async def analyze_chart(
    image_path: str,
    provider: str | None = None,
) -> dict[str, Any]:
    """Analyze a chart or graph in an image."""
    prompt = (
        "Analyze this chart/graph in detail. Describe:\n"
        "1. The type of chart\n"
        "2. Axes, labels, and units\n"
        "3. Key data points and trends\n"
        "4. Any notable patterns or insights\n"
        "5. Summary statistics if visible"
    )
    return await analyze_image(image_path, prompt, provider=provider, detail="high")


# ---------------------------------------------------------------------------
# Tool schemas for OpenAI function calling
# ---------------------------------------------------------------------------

VISION_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "analyze_image",
            "description": "Analyze an image file and answer questions about it. Supports photos, screenshots, charts, documents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "Path to the image file"},
                    "prompt": {"type": "string", "description": "What to analyze or ask about the image"},
                },
                "required": ["image_path", "prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_image_url",
            "description": "Analyze an image from a URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_url": {"type": "string", "description": "URL of the image"},
                    "prompt": {"type": "string", "description": "What to analyze about the image"},
                },
                "required": ["image_url", "prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_and_analyze",
            "description": "Take a photo with the device camera and immediately analyze it. Requires termux-api.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "What to analyze in the photo"},
                    "camera": {"type": "string", "enum": ["back", "front"], "description": "Which camera (default: back)"},
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ocr_image",
            "description": "Extract all text from an image (OCR). Works on screenshots, documents, signs, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "Path to the image file"},
                },
                "required": ["image_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_handwriting",
            "description": "Read and transcribe handwritten text from an image.",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "Path to the handwritten image"},
                },
                "required": ["image_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_chart",
            "description": "Analyze a chart or graph image, extracting data points, trends, and insights.",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "Path to the chart image"},
                },
                "required": ["image_path"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------

VISION_TOOL_MAP = {
    "analyze_image": analyze_image,
    "analyze_image_url": analyze_image_url,
    "take_and_analyze": take_and_analyze,
    "ocr_image": ocr_image,
    "read_handwriting": read_handwriting,
    "analyze_chart": analyze_chart,
}
