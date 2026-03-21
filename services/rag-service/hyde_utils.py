import os
import threading
import httpx
import logging
from core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

HYDE_PROMPT_TEMPLATE = """Bạn là một chuyên gia pháp luật Việt Nam.
Hãy viết một đoạn văn bản giả định trả lời câu hỏi dưới đây một cách chi tiết và chuyên nghiệp.
Đoạn văn này sẽ được dùng để tìm kiếm các văn bản pháp luật liên quan.

Câu hỏi: {query}

Câu trả lời giả định:"""

# Module-level shared AsyncClient — avoids a new TCP connection per HyDE call
_hyde_http_client: httpx.AsyncClient | None = None
_hyde_http_client_lock = threading.Lock()


def _get_hyde_http_client() -> httpx.AsyncClient:
    global _hyde_http_client
    if _hyde_http_client is None:
        with _hyde_http_client_lock:
            if _hyde_http_client is None:
                _hyde_http_client = httpx.AsyncClient(timeout=30.0)
    return _hyde_http_client


class HyDEGenerator:
    def __init__(self):
        self.api_url = f"{settings.VLLM_API_BASE}/chat/completions"
        self.model = settings.VLLM_MODEL

    async def generate_hypothetical_answer(self, query: str) -> str:
        """Generate a hypothetical document based on the query to improve embedding search."""
        if not query.strip():
            return ""

        messages = [
            {"role": "system", "content": "Bạn là trợ lý pháp luật chuyên nghiệp."},
            {"role": "user", "content": HYDE_PROMPT_TEMPLATE.format(query=query)}
        ]

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 512,
            "temperature": 0.3,
        }

        try:
            client = _get_hyde_http_client()
            resp = await client.post(
                self.api_url, json=payload,
                headers={"Authorization": f"Bearer {settings.LITELLM_MASTER_KEY.get_secret_value()}"}
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            logger.info(f"HyDE generated hypothetical answer for query: {query[:50]}...")
            return content if content else ""
        except Exception as e:
            logger.error(f"HyDE generation failed: {e}")
            return query  # Fallback to original query
