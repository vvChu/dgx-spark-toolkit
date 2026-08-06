"""Centralized async LLM client for all API-layer LLM calls.

Backward-compatibility wrapper delegating to the unified AIGatewayClient.
"""
import logging
from typing import Any
import httpx

from core.ai_gateway_client import AIGatewayClient

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
    """Send a chat-completion request to AI Gateway using AIGatewayClient."""
    client = AIGatewayClient(http_client=http_client)
    return await client.complete(
        messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format=response_format,
        extra_body=extra_body,
        stop=stop,
        timeout=timeout,
    )


async def call_llm_json(
    http_client: httpx.AsyncClient,
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 1024,
    timeout: float | None = None,
) -> Any:
    """Call LLM in JSON mode and parse result using AIGatewayClient."""
    client = AIGatewayClient(http_client=http_client)
    return await client.complete_json(
        messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )
