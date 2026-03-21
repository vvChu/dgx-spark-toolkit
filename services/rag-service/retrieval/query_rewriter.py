"""LLM-based query rewriting: standardize legal terms and expand acronyms."""
import asyncio
import logging
import threading

import httpx

from core.config import get_settings

logger = logging.getLogger(__name__)

# Single in-memory cache for query rewrites (bounded, FIFO)
# asyncio.Lock is created lazily inside the first coroutine call to avoid
# binding to the wrong event loop when the module is imported before the loop starts.
_query_rewrite_cache: dict = {}
_query_rewrite_lock: asyncio.Lock | None = None


def _get_rewrite_lock() -> asyncio.Lock:
    global _query_rewrite_lock
    if _query_rewrite_lock is None:
        _query_rewrite_lock = asyncio.Lock()
    return _query_rewrite_lock


# Module-level shared AsyncClient — avoids creating a new TCP connection per rewrite call
_rewrite_http_client: httpx.AsyncClient | None = None
_rewrite_http_client_thread_lock = threading.Lock()


def _get_rewrite_http_client() -> httpx.AsyncClient:
    global _rewrite_http_client
    if _rewrite_http_client is None:
        with _rewrite_http_client_thread_lock:
            if _rewrite_http_client is None:
                _rewrite_http_client = httpx.AsyncClient(timeout=30.0)
    return _rewrite_http_client


async def rewrite_query(original_query: str) -> str:
    """Standardize legal terms and expand acronyms using LLM."""
    lock = _get_rewrite_lock()
    async with lock:
        if original_query in _query_rewrite_cache:
            return _query_rewrite_cache[original_query]

    try:
        settings = get_settings()
        from core.prompts import QUERY_REWRITE_PROMPT

        prompt = QUERY_REWRITE_PROMPT.format(original_query=original_query)
        payload = {
            "model": settings.VLLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 100,
        }
        client = _get_rewrite_http_client()
        resp = await client.post(
            f"{settings.VLLM_API_BASE}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {settings.LITELLM_MASTER_KEY.get_secret_value()}"},
        )
        if resp.status_code == 200:
            rewritten = resp.json()["choices"][0]["message"]["content"].strip().strip('"')
            async with lock:
                if len(_query_rewrite_cache) >= 1000:
                    _query_rewrite_cache.pop(next(iter(_query_rewrite_cache)))
                _query_rewrite_cache[original_query] = rewritten
            return rewritten
    except Exception as e:
        logger.warning(f"Query rewriting failed: {e}")
    return original_query
