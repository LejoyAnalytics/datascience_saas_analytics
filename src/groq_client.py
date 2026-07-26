"""
Thin wrapper around the Groq API — the chatbot's only LLM call site.

GROQ_API_KEY is read from the environment/.env and never leaves this
backend process: it is never written into any Streamlit output, session
state that gets rendered, log message, or otherwise surfaced to the browser.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


def is_configured() -> bool:
    return bool(os.getenv("GROQ_API_KEY"))


def chat(messages: list[dict], temperature: float = 0.1, max_tokens: int = 1024, json_mode: bool = False) -> str:
    """Single non-streaming chat completion. Raises RuntimeError with a
    caller-safe message on any failure (missing key, network, API error)."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set.")

    try:
        from groq import Groq
    except ImportError as e:
        raise RuntimeError("The 'groq' package is not installed.") from e

    client = Groq(api_key=api_key)
    kwargs = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
    except Exception as e:
        raise RuntimeError(f"Groq request failed: {e}") from e

    return response.choices[0].message.content or ""
