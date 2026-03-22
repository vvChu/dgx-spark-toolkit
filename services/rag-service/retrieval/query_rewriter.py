"""LLM-based query rewriting: standardize legal terms and expand acronyms."""
import asyncio
import logging

import httpx

from core.config import get_settings
from core.llm_client import call_llm

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


async def rewrite_query(original_query: str, http_client: httpx.AsyncClient | None = None) -> str:
    """Standardize legal terms and expand acronyms using LLM."""
    lock = _get_rewrite_lock()
    async with lock:
        if original_query in _query_rewrite_cache:
            return _query_rewrite_cache[original_query]

    try:
        from core.prompts import QUERY_REWRITE_PROMPT

        prompt = QUERY_REWRITE_PROMPT.format(original_query=original_query)

        # Use injected client if available, otherwise create a one-off
        if http_client is None:
            http_client = httpx.AsyncClient(timeout=30.0)

        rewritten = await call_llm(
            http_client,
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=100,
        )
        rewritten = rewritten.strip('"')
        async with lock:
            if len(_query_rewrite_cache) >= 1000:
                _query_rewrite_cache.pop(next(iter(_query_rewrite_cache)))
            _query_rewrite_cache[original_query] = rewritten
        return rewritten
    except Exception as e:
        logger.warning(f"Query rewriting failed: {e}")
    return original_query
