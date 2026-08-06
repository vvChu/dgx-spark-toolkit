"""Redis-backed session memory for multi-turn conversation context.

Stores conversation history per session ID with automatic TTL expiration.
Uses Redis DB 2 to avoid conflicts with LiteLLM (DB 0) and ingestion queue (DB 1).
"""
import json
import logging
import time
from typing import Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Maximum turns to retain per session (oldest are trimmed on write)
_MAX_TURNS = 20
# Key prefix for session data in Redis
_KEY_PREFIX = "session:"


class SessionMemory:
    """Async Redis-backed session memory with TTL."""

    def __init__(self, redis_url: str, ttl_seconds: int = 7200):
        # Force DB 2 regardless of what's in the URL
        base_url = redis_url.rsplit("/", 1)[0] if "/" in redis_url.rsplit(":", 1)[-1] else redis_url
        self.redis = aioredis.from_url(f"{base_url}/2", decode_responses=True)
        self.ttl = ttl_seconds

    async def health_check(self) -> dict:
        try:
            await self.redis.ping()
            return {"status": "healthy"}
        except Exception as e:
            return {"status": "unavailable", "error": str(e)}

    async def get_history(self, session_id: str) -> list[dict]:
        """Retrieve conversation history for a session."""
        key = f"{_KEY_PREFIX}{session_id}"
        try:
            raw = await self.redis.get(key)
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.warning("Failed to read session %s: %s", session_id, e)
        return []

    async def add_turn(
        self,
        session_id: str,
        query: str,
        answer: str,
        sources: list[str] | None = None,
    ) -> None:
        """Append a Q&A turn to the session history."""
        key = f"{_KEY_PREFIX}{session_id}"
        history = await self.get_history(session_id)

        turn = {
            "role_user": query,
            "role_assistant": answer[:2000],  # Truncate long answers
            "sources": (sources or [])[:5],   # Top 5 sources
            "ts": time.time(),
        }
        history.append(turn)

        # Trim to max turns
        if len(history) > _MAX_TURNS:
            history = history[-_MAX_TURNS:]

        try:
            await self.redis.set(key, json.dumps(history, ensure_ascii=False), ex=self.ttl)
        except Exception as e:
            logger.warning("Failed to write session %s: %s", session_id, e)

    def build_context_messages(self, history: list[dict], max_turns: int = 6) -> list[dict]:
        """Convert session history into OpenAI-format messages for LLM context.

        Returns at most *max_turns* recent exchanges (user + assistant pairs).
        """
        messages: list[dict] = []
        for turn in history[-max_turns:]:
            messages.append({"role": "user", "content": turn["role_user"]})
            messages.append({"role": "assistant", "content": turn["role_assistant"]})
        return messages

    async def get_context_summary(self, session_id: str) -> Optional[str]:
        """Return a compact text summary of the session for injection into prompts.

        Includes the topics discussed and key document references so the LLM
        can reason about follow-up questions without re-retrieving everything.
        """
        history = await self.get_history(session_id)
        if not history:
            return None

        lines = []
        all_sources: set[str] = set()
        for i, turn in enumerate(history[-6:], 1):
            lines.append(f"Q{i}: {turn['role_user'][:200]}")
            lines.append(f"A{i}: {turn['role_assistant'][:300]}")
            for s in turn.get("sources", []):
                all_sources.add(s)

        summary = "=== CONVERSATION CONTEXT ===\n"
        summary += "\n".join(lines)
        if all_sources:
            summary += f"\n\nDocuments referenced: {', '.join(sorted(all_sources))}"
        return summary

    async def close(self):
        await self.redis.aclose()
