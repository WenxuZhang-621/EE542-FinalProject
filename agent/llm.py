"""The chat model used by the agent, through the same OpenAI-compatible settings as extract/.

    LLM_API_KEY, LLM_MODEL, LLM_BASE_URL     where the model runs (OpenAI, Qwen API, our vLLM)
    LLM_JSON_MODE=object                     for servers without json_schema structured output
    LLM_DISABLE_THINKING=1                   for Qwen3 on vLLM

extract/extract.py keeps its own client; this module avoids importing it because extract/
is also put on sys.path as a flat folder, which makes `import extract` ambiguous.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

_client = None


class LLMError(RuntimeError):
    """The model is not configured, did not answer, or answered with unusable output."""


def model_name() -> str:
    return os.getenv("LLM_MODEL", "gpt-4o-mini")


def client():
    global _client
    if _client is None:
        from openai import OpenAI

        key = os.getenv("LLM_API_KEY")
        if not key:
            raise LLMError("LLM_API_KEY is not set. Configure the model in .env.")
        _client = OpenAI(api_key=key, base_url=os.getenv("LLM_BASE_URL") or None,
                         timeout=90.0, max_retries=1)
    return _client


def extra_options() -> dict:
    """Request options every call needs for the configured server."""
    if os.getenv("LLM_DISABLE_THINKING") == "1":
        return {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
    return {}


def json_chat(messages: list[dict], schema: dict, *, name: str = "answer",
              temperature: float = 0.3) -> dict:
    """One completion that must return a JSON object matching `schema`."""
    from openai import APIError

    if os.getenv("LLM_JSON_MODE", "schema") == "object":
        fmt = {"type": "json_object"}
    else:
        fmt = {"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}}
    try:
        resp = client().chat.completions.create(
            model=model_name(), temperature=temperature, response_format=fmt,
            messages=messages, **extra_options(),
        )
    except APIError as exc:
        raise LLMError(f"The model call failed: {exc}") from exc
    content = resp.choices[0].message.content or ""
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMError("The model did not return valid JSON.") from exc
    if not isinstance(data, dict):
        raise LLMError("The model returned JSON that is not an object.")
    return data
