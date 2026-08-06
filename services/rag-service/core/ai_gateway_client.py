"""Unified deep AI Gateway Client module for text, JSON, and Vision completions.

Provides a single, resilient seam for all AI Gateway (LiteLLM proxy / vLLM) interactions,
incorporating transparent fallback chains, rate-limit backoff retries, and markdown fence parsing.
"""
import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Type
import httpx
from pydantic import BaseModel

from core.config import get_settings

logger = logging.getLogger(__name__)


class AIGatewayClient:
    """Deep module for all AI Gateway interactions."""

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None, settings: Any = None):
        self.settings = settings or get_settings()
        self._http_client = http_client
        self.gateway_url = f"{self.settings.VLLM_API_BASE}/chat/completions"
        self.api_key = self.settings.LITELLM_MASTER_KEY.get_secret_value() if hasattr(self.settings.LITELLM_MASTER_KEY, 'get_secret_value') else str(self.settings.LITELLM_MASTER_KEY)

    def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=300.0)
        return self._http_client

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        *,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        response_format: Optional[Dict[str, Any]] = None,
        extra_body: Optional[Dict[str, Any]] = None,
        stop: Optional[List[str]] = None,
        timeout: Optional[float] = None,
        model_chain: Optional[List[str]] = None,
    ) -> str:
        """Send a chat completion request with automatic fallback chain retries."""
        chain = model_chain or [model or self.settings.VLLM_MODEL, "rag-core", "rag-light"]
        headers = {"Authorization": f"Bearer {self.api_key}"}

        last_error = None
        for target_model in chain:
            payload: Dict[str, Any] = {
                "model": target_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if response_format:
                payload["response_format"] = response_format
            if stop:
                payload["stop"] = stop
            if extra_body:
                payload.update(extra_body)

            client = self._get_client()
            for attempt in range(3):
                try:
                    resp = await client.post(self.gateway_url, json=payload, headers=headers, timeout=timeout or 300.0)
                    if getattr(resp, "status_code", 200) == 429:
                        await asyncio.sleep(2 * (attempt + 1))
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                except Exception as e:
                    last_error = e
                    logger.warning(f"AIGatewayClient completion error on model {target_model} (attempt {attempt+1}): {e}")
                    await asyncio.sleep(1)

        raise RuntimeError(f"AIGatewayClient failed all model fallbacks in chain {chain}: {last_error}") from last_error

    async def complete_json(
        self,
        messages: List[Dict[str, Any]],
        *,
        schema: Optional[Type[BaseModel]] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        timeout: Optional[float] = None,
    ) -> Any:
        """Completion in JSON mode, stripping markdown fences and optionally validating Pydantic schema."""
        resp_fmt = None
        if schema:
            resp_fmt = {"type": "json_schema", "json_schema": {"name": "schema", "strict": True, "schema": schema.model_json_schema()}}
        else:
            resp_fmt = {"type": "json_object"}

        raw = await self.complete(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=resp_fmt,
            timeout=timeout,
        )

        cleaned = raw.replace("```json", "").replace("```", "").strip()
        if schema:
            validated = schema.model_validate_json(cleaned)
            return validated.model_dump()
        return json.loads(cleaned)

    async def complete_vision(
        self,
        image_bytes_or_b64: Any,
        prompt: str = "Trích xuất toàn bộ văn bản tiếng Việt từ ảnh pháp lý này.",
        *,
        model: Optional[str] = None,
    ) -> str:
        """Send vision OCR completion."""
        import base64
        if isinstance(image_bytes_or_b64, bytes):
            b64 = base64.b64encode(image_bytes_or_b64).decode("utf-8")
        else:
            b64 = str(image_bytes_or_b64)

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                ]
            }
        ]
        target_model = model or getattr(self.settings, "PRIMARY_VISION_MODEL", "gemini-3-flash")
        return await self.complete(messages, model=target_model, model_chain=[target_model, "gemini-3.1-flash-lite", "rag-core"])

    # Sync Wrappers
    def complete_sync(self, messages: List[Dict[str, Any]], **kwargs) -> str:
        return asyncio.run(self.complete(messages, **kwargs))

    def complete_json_sync(self, messages: List[Dict[str, Any]], **kwargs) -> Any:
        return asyncio.run(self.complete_json(messages, **kwargs))

    def complete_vision_sync(self, image_bytes_or_b64: Any, prompt: str = "Trích xuất văn bản.", **kwargs) -> str:
        return asyncio.run(self.complete_vision(image_bytes_or_b64, prompt, **kwargs))


class MockAIGatewayClient(AIGatewayClient):
    """In-memory mock adapter for offline unit testing."""

    def __init__(self, default_response: str = "Mocked LLM completion"):
        self.default_response = default_response
        self.call_history: List[Dict[str, Any]] = []

    async def complete(self, messages: List[Dict[str, Any]], **kwargs) -> str:
        self.call_history.append({"messages": messages, "kwargs": kwargs})
        return self.default_response

    async def complete_json(self, messages: List[Dict[str, Any]], schema: Optional[Type[BaseModel]] = None, **kwargs) -> Any:
        self.call_history.append({"messages": messages, "schema": schema, "kwargs": kwargs})
        if schema:
            # Generate dummy dictionary matching schema fields
            fields = schema.model_fields if hasattr(schema, 'model_fields') else {}
            dummy = {k: "test" for k in fields.keys()}
            return dummy
        return {"result": self.default_response}

    async def complete_vision(self, image_bytes_or_b64: Any, prompt: str = "", **kwargs) -> str:
        self.call_history.append({"prompt": prompt, "kwargs": kwargs})
        return f"OCR: {self.default_response}"
