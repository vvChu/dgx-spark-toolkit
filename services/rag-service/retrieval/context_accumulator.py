"""Cross-query context accumulator for session-scoped document working sets.

Maintains a sliding window of relevant document chunks across related queries
within the same session.  Old entries decay over time so that the working set
stays focused on the current topic while retaining useful background context.
"""
import json
import logging
import time
from typing import Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_KEY_PREFIX = "ctx_accum:"
_TTL_SECONDS = 7200  # 2 hours, aligned with session TTL


class ContextAccumulator:
    """Redis-backed per-session context accumulator using sorted sets."""

    def __init__(self, redis_url: str, max_docs: int = 20, decay_factor: float = 0.8):
        base_url = redis_url.rsplit("/", 1)[0] if "/" in redis_url.rsplit(":", 1)[-1] else redis_url
        self.redis = aioredis.from_url(f"{base_url}/2", decode_responses=True)
        self.max_docs = max_docs
        self.decay_factor = decay_factor

    async def add_retrieval(
        self,
        session_id: str,
        chunks: list[dict],
        scores: list[float],
    ) -> None:
        """Add new retrieval results to the session's working set.

        First decays all existing scores, then adds the new chunks.
        The sorted set is trimmed to *max_docs* entries.
        """
        key = f"{_KEY_PREFIX}{session_id}"
        try:
            # 1. Decay existing scores
            existing = await self.redis.zrangebyscore(key, "-inf", "+inf", withscores=True)
            if existing:
                pipe = self.redis.pipeline()
                for member, old_score in existing:
                    pipe.zadd(key, {member: old_score * self.decay_factor})
                await pipe.execute()

            # 2. Add new chunks (use doc_number+page as member key for dedup)
            for chunk, score in zip(chunks, scores):
                member_key = f"{chunk.get('doc_number', 'unknown')}::p{chunk.get('page', 0)}::{chunk.get('text', '')[:80]}"
                member_data = json.dumps({
                    "text": chunk.get("text", "")[:3000],
                    "source": chunk.get("source", ""),
                    "doc_number": chunk.get("doc_number", ""),
                    "page": chunk.get("page", 0),
                    "added_at": time.time(),
                }, ensure_ascii=False)
                # Store the data in a hash, score in sorted set
                await self.redis.hset(f"{key}:data", member_key, member_data)
                await self.redis.zadd(key, {member_key: float(score)})

            # 3. Trim to max_docs (remove lowest-scored)
            total = await self.redis.zcard(key)
            if total > self.max_docs:
                # Remove lowest-scored entries
                to_remove = await self.redis.zrange(key, 0, total - self.max_docs - 1)
                if to_remove:
                    await self.redis.zrem(key, *to_remove)
                    await self.redis.hdel(f"{key}:data", *to_remove)

            # Reset TTL
            await self.redis.expire(key, _TTL_SECONDS)
            await self.redis.expire(f"{key}:data", _TTL_SECONDS)

        except Exception as e:
            logger.warning("Context accumulator write failed for %s: %s", session_id, e)

    async def get_accumulated_context(self, session_id: str) -> list[dict]:
        """Retrieve the current working set of documents, highest score first."""
        key = f"{_KEY_PREFIX}{session_id}"
        try:
            # Get top members by score (descending)
            members = await self.redis.zrevrange(key, 0, self.max_docs - 1, withscores=True)
            if not members:
                return []

            results = []
            for member_key, score in members:
                raw = await self.redis.hget(f"{key}:data", member_key)
                if raw:
                    data = json.loads(raw)
                    data["accumulated_score"] = round(score, 4)
                    results.append(data)
            return results

        except Exception as e:
            logger.warning("Context accumulator read failed for %s: %s", session_id, e)
            return []

    async def close(self):
        await self.redis.aclose()
