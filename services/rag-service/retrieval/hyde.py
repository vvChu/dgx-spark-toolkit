import logging

import httpx

from core.config import get_settings
from core.llm_client import call_llm

logger = logging.getLogger(__name__)

HYDE_PROMPT_TEMPLATE = """Bạn là một chuyên gia pháp luật Việt Nam.
Hãy viết một đoạn văn bản giả định trả lời câu hỏi dưới đây một cách chi tiết và chuyên nghiệp.
Đoạn văn này sẽ được dùng để tìm kiếm các văn bản pháp luật liên quan.

Câu hỏi: {query}

Câu trả lời giả định:"""


class HyDEGenerator:
    def __init__(self, http_client: httpx.AsyncClient | None = None):
        _s = get_settings()
        self.model = _s.VLLM_MODEL
        self._http_client = http_client

    async def generate_hypothetical_answer(self, query: str) -> str:
        """Generate a hypothetical document based on the query to improve embedding search."""
        if not query.strip():
            return ""

        messages = [
            {"role": "system", "content": "Bạn là trợ lý pháp luật chuyên nghiệp."},
            {"role": "user", "content": HYDE_PROMPT_TEMPLATE.format(query=query)}
        ]

        try:
            client = self._http_client or httpx.AsyncClient(timeout=30.0)
            content = await call_llm(
                client,
                messages,
                model=self.model,
                max_tokens=512,
                temperature=0.3,
            )
            logger.info(f"HyDE generated hypothetical answer for query: {query[:50]}...")
            return content if content else ""
        except Exception as e:
            logger.error(f"HyDE generation failed: {e}")
            return query
