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
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type, AsyncIterator
import httpx
from pydantic import BaseModel

from core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class StreamChunk:
    """Represents a streaming token chunk from the AI Gateway."""
    text: str
    is_thought: bool = False
    finish_reason: Optional[str] = None


class AIGatewayClient:
    """Deep module for all AI Gateway interactions."""

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None, settings: Any = None):
        self.settings = settings or get_settings()
        self._http_client = http_client
        self.gateway_url = f"{self.settings.VLLM_API_BASE}/chat/completions"
        self.api_key = self.settings.LITELLM_MASTER_KEY.get_secret_value() if hasattr(self.settings.LITELLM_MASTER_KEY, 'get_secret_value') else str(self.settings.LITELLM_MASTER_KEY)

    def _get_client(self) -> httpx.AsyncClient:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        client_loop = getattr(self, "_client_loop", None)
        if self._http_client is None or self._http_client.is_closed or (client_loop is not None and client_loop != current_loop):
            self._http_client = httpx.AsyncClient(timeout=300.0)
            self._client_loop = current_loop
        return self._http_client

    async def stream(
        self,
        messages: List[Dict[str, Any]],
        *,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 8192,
        stop: Optional[List[str]] = None,
        extra_body: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = 120.0,
        model_chain: Optional[List[str]] = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream chat completion tokens from AI Gateway with fallback chain resilience.

        Yields StreamChunk objects differentiating final content tokens from reasoning/thought tokens.
        """
        chain = model_chain or [model or self.settings.VLLM_MODEL, "rag-core", "rag-light"]
        headers = {"Authorization": f"Bearer {self.api_key}"}
        client = self._get_client()

        last_error = None
        started_yielding = False

        for target_model in chain:
            enable_thinking = (
                "instruct" not in target_model.lower()
                and (
                    target_model in {"qwen-local-primary", "local-coder"}
                    or ("qwen" in target_model.lower() and "primary" in target_model.lower())
                    or "coder" in target_model.lower()
                )
            )
            model_extra = {"chat_template_kwargs": {"enable_thinking": True}} if enable_thinking else {}
            if extra_body:
                model_extra.update(extra_body)

            payload: Dict[str, Any] = {
                "model": target_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            }
            if stop:
                payload["stop"] = stop
            if model_extra:
                payload.update(model_extra)

            try:
                async with client.stream(
                    "POST",
                    self.gateway_url,
                    json=payload,
                    headers=headers,
                    timeout=timeout or 120.0,
                ) as resp:
                    if resp.status_code == 429 and not started_yielding:
                        logger.warning(f"AIGatewayClient stream got 429 on model {target_model}, attempting fallback...")
                        await asyncio.sleep(1)
                        continue

                    resp.raise_for_status()

                    in_thought_block = False
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if not data_str:
                            continue
                        if data_str == "[DONE]":
                            return

                        try:
                            chunk_json = json.loads(data_str)
                            choice = chunk_json.get("choices", [{}])[0]
                            delta = choice.get("delta", {})
                            finish_reason = choice.get("finish_reason")

                            # 1. Check reasoning / thought field (vLLM / LiteLLM / DeepSeek format)
                            reasoning_content = (
                                delta.get("reasoning_content")
                                or delta.get("thought")
                                or delta.get("reasoning")
                            )
                            if reasoning_content:
                                started_yielding = True
                                yield StreamChunk(text=reasoning_content, is_thought=True, finish_reason=finish_reason)

                            # 2. Check standard content field
                            content = delta.get("content", "")
                            if content:
                                # Handle embedded <think>...</think> tags if present in content
                                if "<think>" in content:
                                    in_thought_block = True
                                    content = content.replace("<think>", "")
                                if "</think>" in content:
                                    in_thought_block = False
                                    content = content.replace("</think>", "")

                                if content:
                                    started_yielding = True
                                    yield StreamChunk(text=content, is_thought=in_thought_block, finish_reason=finish_reason)
                        except (json.JSONDecodeError, IndexError):
                            continue
                return
            except Exception as e:
                last_error = e
                logger.warning(f"AIGatewayClient stream error on model {target_model}: {e}")
                if started_yielding:
                    raise
                await asyncio.sleep(0.5)

        if not started_yielding:
            raise RuntimeError(f"AIGatewayClient streaming failed all model fallbacks in chain {chain}: {last_error}") from last_error

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
        **kwargs: Any,
    ) -> str:
        """Send a chat completion request with automatic fallback chain retries."""
        chain = model_chain or [model or self.settings.VLLM_MODEL, "rag-core", "rag-light"]
        headers = {"Authorization": f"Bearer {self.api_key}"}
        max_retries = int(kwargs.pop("retries", 3))

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
            if kwargs:
                payload.update(kwargs)

            client = self._get_client()
            for attempt in range(max_retries):
                try:
                    resp = await client.post(self.gateway_url, json=payload, headers=headers, timeout=timeout or 300.0)
                    if getattr(resp, "status_code", 200) == 429:
                        await asyncio.sleep(2 * (attempt + 1))
                        continue
                    res_status = resp.raise_for_status()
                    if asyncio.iscoroutine(res_status):
                        await res_status
                    data = resp.json()
                    if asyncio.iscoroutine(data):
                        data = await data
                    choice = data["choices"][0]
                    content = (choice.get("message", {}).get("content") or "").strip()
                    if content:
                        return content
                    finish = choice.get("finish_reason")
                    logger.warning(
                        "AIGatewayClient model %s returned empty content (finish_reason: %s). Trying next fallback.",
                        target_model, finish
                    )
                    break  # Break retry loop for this model and proceed to next model in chain
                except Exception as e:
                    last_error = e
                    err_name = type(e).__name__
                    err_detail = str(e) or "Timeout or empty response"
                    logger.warning(
                        "AIGatewayClient completion error on model %s (attempt %d/%d): %s: %s",
                        target_model, attempt + 1, max_retries, err_name, err_detail
                    )
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
        model_chain: Optional[List[str]] = None,
        retry_on_error: bool = True,
        **kwargs: Any,
    ) -> Any:
        """Extract structured JSON dictionary or Pydantic model directly from LLM completion."""
        if isinstance(prompt_or_messages, str):
            messages = [{"role": "user", "content": prompt_or_messages}]
        elif isinstance(prompt_or_messages, list):
            messages = prompt_or_messages
        else:
            raise TypeError("prompt_or_messages must be a str or list of dicts")

        extra_body = dict(kwargs.pop("extra_body", None) or {})
        chat_template_kwargs = dict(extra_body.get("chat_template_kwargs", {}) or {})
        if "enable_thinking" not in chat_template_kwargs:
            chat_template_kwargs["enable_thinking"] = False
        extra_body["chat_template_kwargs"] = chat_template_kwargs

        raw_completion = await self.complete(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            model_chain=model_chain,
            extra_body=extra_body,
            **kwargs,
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
                model_chain=model_chain,
                extra_body=extra_body,
                **kwargs,
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
        model_chain: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Any:
        """Completion in JSON mode using extract_json."""
        return await self.extract_json(
            messages,
            schema=schema,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            model_chain=model_chain,
            **kwargs,
        )

    async def complete_vision(
        self,
        image_bytes_or_b64: Any,
        prompt: str = "Trích xuất toàn bộ văn bản tiếng Việt từ ảnh pháp lý này.",
        *,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        model_chain: Optional[List[str]] = None,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        timeout: Optional[float] = None,
    ) -> str:
        """Send vision OCR or multimodal completion with automated base64 formatting and fallback cascade."""
        import base64
        from io import BytesIO

        mime_type = "image/jpeg"
        if isinstance(image_bytes_or_b64, bytes):
            if image_bytes_or_b64.startswith(b'\x89PNG\r\n\x1a\n'):
                mime_type = "image/png"
            b64 = base64.b64encode(image_bytes_or_b64).decode("utf-8")
            data_uri = f"data:{mime_type};base64,{b64}"
        elif hasattr(image_bytes_or_b64, "save"):  # PIL Image
            bio = BytesIO()
            image_bytes_or_b64.save(bio, format="JPEG")
            b64 = base64.b64encode(bio.getvalue()).decode("utf-8")
            data_uri = f"data:image/jpeg;base64,{b64}"
        else:
            b64_str = str(image_bytes_or_b64)
            if b64_str.startswith("data:"):
                data_uri = b64_str
            else:
                data_uri = f"data:{mime_type};base64,{b64_str}"

        messages: List[Dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri}}
                ]
            }
        )
        target_model = model or getattr(self.settings, "PRIMARY_VISION_MODEL", "gemini-3-flash")
        chain = model_chain or [target_model, "ocr-primary", "ocr-fallback", "rag-core"]
        extra_body = {"chat_template_kwargs": {"enable_thinking": False}}

        res = await self.complete(
            messages,
            model=target_model,
            model_chain=chain,
            max_tokens=max_tokens,
            temperature=temperature,
            extra_body=extra_body,
            timeout=timeout,
        )

        res = re.sub(r'<think>[\s\S]*?</think>\s*', '', res)
        tp_match = re.match(
            r'(?:Thinking Process|Internal Monologue|Reasoning):?\s*\n[\s\S]*?\n\n([\s\S]+)',
            res, re.IGNORECASE
        )
        if tp_match:
            res = tp_match.group(1)
        return res.strip()

    # Sync Wrappers
    def complete_sync(self, messages: List[Dict[str, Any]], **kwargs) -> str:
        return asyncio.run(self.complete(messages, **kwargs))

    def complete_json_sync(self, messages: List[Dict[str, Any]], **kwargs) -> Any:
        return asyncio.run(self.complete_json(messages, **kwargs))

    def extract_json_sync(self, prompt_or_messages: Any, **kwargs) -> Any:
        return asyncio.run(self.extract_json(prompt_or_messages, **kwargs))

    def complete_vision_sync(
        self,
        image_bytes_or_b64: Any,
        prompt: str = "Trích xuất văn bản.",
        *,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> str:
        return asyncio.run(self.complete_vision(image_bytes_or_b64, prompt, system_prompt=system_prompt, **kwargs))


class MockAIGatewayClient(AIGatewayClient):
    """In-memory mock adapter for offline unit testing."""

    def __init__(self, default_response: str = "Mocked LLM completion"):
        self.default_response = default_response
        self.call_history: List[Dict[str, Any]] = []
        self._mock_vision_handler = None

    def set_mock_vision_response(self, handler_or_str: Any) -> None:
        """Configure mock vision response (string or callable(prompt, image) -> str)."""
        self._mock_vision_handler = handler_or_str

    async def complete(self, messages: List[Dict[str, Any]], **kwargs) -> str:
        self.call_history.append({"messages": messages, "kwargs": kwargs})
        return self.default_response

    async def stream(
        self,
        messages: List[Dict[str, Any]],
        *,
        model: Optional[str] = None,
        custom_chunks: Optional[List[StreamChunk]] = None,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        """Mock stream generator for offline unit testing."""
        self.call_history.append({"messages": messages, "model": model, "kwargs": kwargs, "stream": True})
        if custom_chunks:
            for chunk in custom_chunks:
                yield chunk
            return

        words = self.default_response.split(" ")
        for i, word in enumerate(words):
            token = word if i == 0 else " " + word
            yield StreamChunk(text=token, is_thought=False)

    async def complete_json(self, messages: List[Dict[str, Any]], schema: Optional[Type[BaseModel]] = None, **kwargs) -> Any:
        self.call_history.append({"messages": messages, "schema": schema, "kwargs": kwargs})
        if schema:
            fields = schema.model_fields if hasattr(schema, 'model_fields') else {}
            dummy = {k: "test" for k in fields.keys()}
            return dummy
        return {"result": self.default_response}

    async def extract_json(self, prompt_or_messages: Any, schema: Optional[Type[BaseModel]] = None, **kwargs) -> Any:
        messages = prompt_or_messages if isinstance(prompt_or_messages, list) else [{"role": "user", "content": prompt_or_messages}]
        return await self.complete_json(messages, schema=schema, **kwargs)

    async def complete_vision(self, image_bytes_or_b64: Any, prompt: str = "", *, system_prompt: Optional[str] = None, **kwargs) -> str:
        self.call_history.append({"prompt": prompt, "system_prompt": system_prompt, "kwargs": kwargs, "vision": True})
        if self._mock_vision_handler is not None:
            if callable(self._mock_vision_handler):
                return self._mock_vision_handler(prompt, image_bytes_or_b64)
            return str(self._mock_vision_handler)
        return f"OCR: {self.default_response}"


_global_ai_gateway_client: Optional[AIGatewayClient] = None


def get_ai_gateway_client(http_client: Optional[httpx.AsyncClient] = None) -> AIGatewayClient:
    """Return shared stateful AIGatewayClient instance."""
    global _global_ai_gateway_client
    if _global_ai_gateway_client is None:
        _global_ai_gateway_client = AIGatewayClient(http_client=http_client)
    elif http_client is not None and _global_ai_gateway_client._http_client is None:
        _global_ai_gateway_client._http_client = http_client
    return _global_ai_gateway_client


def set_ai_gateway_client(client: Optional[AIGatewayClient]) -> None:
    """Set global AIGatewayClient instance (useful for unit testing)."""
    global _global_ai_gateway_client
    _global_ai_gateway_client = client

