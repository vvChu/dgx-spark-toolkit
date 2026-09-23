import asyncio
import logging
import re

import httpx

from core.config import get_settings
from core.ai_gateway_client import get_ai_gateway_client, AIGatewayClient

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


async def rewrite_query(
    original_query: str,
    http_client: httpx.AsyncClient | None = None,
    ai_client: AIGatewayClient | None = None,
) -> str:
    """Standardize legal terms and expand acronyms using LLM with multi-tier timeout."""
    lock = _get_rewrite_lock()
    async with lock:
        if original_query in _query_rewrite_cache:
            return _query_rewrite_cache[original_query]

    try:
        from core.prompts import QUERY_REWRITE_PROMPT

        prompt = QUERY_REWRITE_PROMPT.format(original_query=original_query)
        client = ai_client or get_ai_gateway_client(http_client)

        rewritten = ""
        # Tier 1: gemini-3.5-flash-lite (1.8s timeout)
        try:
            rewritten = await asyncio.wait_for(
                client.complete(
                    [{"role": "user", "content": prompt}],
                    model="gemini-3.5-flash-lite",
                    model_chain=["gemini-3.5-flash-lite"],
                    temperature=0.0,
                    max_tokens=256,
                    timeout=1.8,
                ),
                timeout=1.8,
            )
        except (asyncio.TimeoutError, Exception) as e1:
            logger.debug(f"Query rewrite Tier 1 (gemini-3.5-flash-lite) skipped/timed out: {e1}")

        # Tier 2: claude-haiku-4 (2.2s timeout) if Tier 1 failed or returned empty
        if not rewritten or not rewritten.strip():
            try:
                rewritten = await asyncio.wait_for(
                    client.complete(
                        [{"role": "user", "content": prompt}],
                        model="claude-haiku-4",
                        model_chain=["claude-haiku-4"],
                        temperature=0.0,
                        max_tokens=256,
                        timeout=2.2,
                    ),
                    timeout=2.2,
                )
            except (asyncio.TimeoutError, Exception) as e2:
                logger.debug(f"Query rewrite Tier 2 (claude-haiku-4) skipped/timed out: {e2}")

        if rewritten and rewritten.strip():
            # Strip reasoning/thought traces
            rewritten = re.sub(r'<think>.*?</think>', '', rewritten, flags=re.DOTALL)
            rewritten = re.sub(r'<thought>.*?</thought>', '', rewritten, flags=re.DOTALL)
            rewritten = re.sub(r'(?i)Thinking Process:.*?(?=\n\n|\Z)', '', rewritten, flags=re.DOTALL)
            rewritten = rewritten.strip().strip('"').strip("'")

            if len(rewritten) > 5:
                async with lock:
                    if len(_query_rewrite_cache) >= 1000:
                        _query_rewrite_cache.pop(next(iter(_query_rewrite_cache)))
                    _query_rewrite_cache[original_query] = rewritten
                return rewritten
    except Exception as e:
        logger.warning(f"Query rewriting failed: {e}")

    return original_query
