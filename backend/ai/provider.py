"""LLM provider abstraction.

Encapsulates access to the generative-AI backend so that swapping providers does
not require changes elsewhere in the application. When no provider is configured
(no NVIDIA_API_KEY), the application transparently uses the local NL->SQL engine.
"""
import logging
import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("app.ai.provider")

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
USE_AI = bool(NVIDIA_API_KEY and len(NVIDIA_API_KEY.strip()) > 10)
MODEL = os.getenv("NVIDIA_MODEL", "deepseek-ai/deepseek-v4-pro")
BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
TIMEOUT_SECONDS = int(os.getenv("AI_TIMEOUT_SECONDS", "60"))
MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "2048"))

_client = None


def _get_client():
    global _client
    if _client is None and USE_AI:
        try:
            import httpx
            from openai import OpenAI

            _client = OpenAI(
                api_key=NVIDIA_API_KEY,
                base_url=BASE_URL,
                timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=15.0),
                max_retries=1,
            )
            logger.info("AI provider connected (%s)", MODEL)
        except Exception as exc:  # pragma: no cover - depends on network deps
            logger.warning("Failed to initialize AI provider: %s", exc)
            return None
    return _client


def is_enabled() -> bool:
    return USE_AI and _get_client() is not None


def chat(system: str, user: str, temperature: float = 0.2) -> str:
    """Run a chat completion and return the assistant text.

    Returns an empty string when the provider is unavailable (callers then fall
    back to the local engine). Returns a string prefixed with ``AI_ERROR`` when a
    provider call fails at runtime; the API layer must never surface raw AI
    errors to end users.
    """
    client = _get_client()
    if client is None:
        return ""
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=MAX_TOKENS,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("AI provider request failed: %s", exc)
        return f"AI_ERROR: {str(exc)}"


def provider_info() -> dict:
    """Non-sensitive provider metadata for the health endpoint."""
    return {"enabled": is_enabled(), "model": MODEL if is_enabled() else None}
