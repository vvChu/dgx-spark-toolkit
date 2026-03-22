"""Centralized async LLM client for all API-layer LLM calls.

Every service/router that needs an LLM completion should use ``call_llm``
(or ``call_llm_json`` for JSON-mode requests) instead of hand-rolling
httpx calls.  The function uses the lifespan-managed ``httpx.AsyncClient``
injected through FastAPI dependencies.
"""
import json
import logging
from typing import Any

import httpx

from core.config import get_settings

logger = logging.getLogger(__name__)


async def call_llm(
    http_client: httpx.AsyncClient,
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 1024,
    response_format: dict | None = None,
    extra_body: dict | None = None,
    stop: list[str] | None = None,
    timeout: float | None = None,
) -> str:
    """Send a chat-completion request to the AI Gateway and return the content.

    Parameters
    ----------
    http_client:
        The shared ``httpx.AsyncClient`` (typically from ``get_http_client`` DI).
    messages:
        OpenAI-style messages list.
    model:
        Model name; defaults to ``Settings.VLLM_MODEL``.
    temperature, max_tokens:
        Standard generation knobs.
    response_format:
        Optional ``{"type": "json_object"}`` etc.
    extra_body:
        Arbitrary extra keys merged into the request payload
        (e.g. ``{"chat_template_kwargs": {"enable_thinking": True}}``).
    stop:
        Optional list of stop sequences.
    timeout:
        Per-request timeout override (seconds).

    Returns
    -------
    str
        The ``choices[0].message.content`` string, stripped.

    Raises
    ------
    httpx.HTTPStatusError
        If the gateway returns a non-2xx status.
    """
    settings = get_settings()
    resolved_model = model or settings.VLLM_MODEL

    payload: dict[str, Any] = {
        "model": resolved_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format is not None:
        payload["response_format"] = response_format
    if stop is not None:
        payload["stop"] = stop
    if extra_body:
        payload.update(extra_body)

    kwargs: dict[str, Any] = {
        "json": payload,
        "headers": {
            "Authorization": f"Bearer {settings.LITELLM_MASTER_KEY.get_secret_value()}"
        },
    }
    if timeout is not None:
        kwargs["timeout"] = timeout

    resp = await http_client.post(
        f"{settings.VLLM_API_BASE}/chat/completions",
        **kwargs,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


async def call_llm_json(
    http_client: httpx.AsyncClient,
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 1024,
    timeout: float | None = None,
) -> Any:
    """Convenience wrapper: calls the LLM in JSON mode and parses the result.

    Returns the parsed JSON object (dict or list).
    """
    raw = await call_llm(
        http_client,
        messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        timeout=timeout,
    )
    # Strip markdown fences that some models wrap around JSON
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(cleaned)
