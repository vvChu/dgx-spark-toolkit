"""Unified deep AI Gateway Client module for text, JSON, and Vision completions.

Provides a single, resilient seam for all AI Gateway (LiteLLM proxy / vLLM) interactions,
incorporating transparent fallback chains, rate-limit backoff retries, and markdown fence parsing.
"""
import asyncio
import json
import logging
import os
import re
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

    def _clean_and_parse_json(self, text: str, schema: Optional[Type[BaseModel]] = None) -> Any:
        """Robust JSON extraction helper using regex fences and fallback JSON parsing."""
        if not text:
            raise ValueError("Empty response string received for JSON extraction")

        # 1. Try regex extraction for Markdown json code fence ```json { ... } ``` or ``` { ... } ```
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        if fence_match:
            candidate = fence_match.group(1).strip()
        else:
            # 2. Fallback: find outer-most braces { ... } or brackets [ ... ]
            brace_match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
            if brace_match:
                candidate = brace_match.group(1).strip()
            else:
                candidate = text.strip()

        # Clean control characters except space/tabs/newlines
        candidate = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', candidate)

        if schema:
            validated = schema.model_validate_json(candidate)
            return validated.model_dump()
        return json.loads(candidate)

    async def extract_json(
        self,
        prompt_or_messages: Any,
        *,
        schema: Optional[Type[BaseModel]] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        timeout: Optional[float] = None,
        retry_on_error: bool = True,
    ) -> Any:
        """Extract structured JSON dictionary or Pydantic model directly from LLM completion."""
        if isinstance(prompt_or_messages, str):
            messages = [{"role": "user", "content": prompt_or_messages}]
        elif isinstance(prompt_or_messages, list):
            messages = prompt_or_messages
        else:
            raise TypeError("prompt_or_messages must be a str or list of dicts")

        raw_completion = await self.complete(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )

        try:
            return self._clean_and_parse_json(raw_completion, schema=schema)
        except Exception as first_err:
            if not retry_on_error:
                raise first_err

            logger.warning(f"Initial JSON parsing failed ({first_err}), retrying with repair prompt...")
            repair_messages = messages + [
                {"role": "assistant", "content": raw_completion},
                {"role": "user", "content": "The output was not valid JSON. Please fix it and respond with valid JSON inside ```json ... ``` code fence ONLY."}
            ]
            repair_raw = await self.complete(
                repair_messages,
                model=model,
                temperature=0.0,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            return self._clean_and_parse_json(repair_raw, schema=schema)

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
        """Completion in JSON mode using extract_json."""
        return await self.extract_json(
            messages,
            schema=schema,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )

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

    def extract_json_sync(self, prompt_or_messages: Any, **kwargs) -> Any:
        return asyncio.run(self.extract_json(prompt_or_messages, **kwargs))

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

    async def extract_json(self, prompt_or_messages: Any, schema: Optional[Type[BaseModel]] = None, **kwargs) -> Any:
        messages = prompt_or_messages if isinstance(prompt_or_messages, list) else [{"role": "user", "content": prompt_or_messages}]
        return await self.complete_json(messages, schema=schema, **kwargs)

    async def complete_vision(self, image_bytes_or_b64: Any, prompt: str = "", **kwargs) -> str:
        self.call_history.append({"prompt": prompt, "kwargs": kwargs})
        return f"OCR: {self.default_response}"
