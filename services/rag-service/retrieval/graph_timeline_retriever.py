import json
import logging
from neo4j import AsyncDriver
import httpx

from core.ai_gateway_client import get_ai_gateway_client, AIGatewayClient

logger = logging.getLogger(__name__)


class AdvancedGraphRAG:
    """
    Handles iterative traversal of legal relationships in Neo4j
    to build a historical timeline of a document.
    """

    def __init__(self, driver: AsyncDriver, http_client: httpx.AsyncClient | None = None, ai_client: AIGatewayClient | None = None):
        self._driver = driver
        # Accept an injected shared client; fall back to creating one if not provided
        # (e.g. when called from the ingestion pipeline outside the FastAPI lifespan)
        self._http_client = http_client
        self._owns_client = http_client is None
        self.ai_client = ai_client or get_ai_gateway_client(http_client)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=60.0)
        return self._http_client

    async def close(self):
        """Release the HTTP client if we own it."""
        if self._owns_client and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def get_legal_timeline(self, doc_number: str, max_hops: int = 10) -> list[dict]:
        """
        Iterative Cypher traversal to retrieve the chain of amendments, replacements, and references.
        """
        if not doc_number or not self._driver:
            return []

        query = """
        MATCH (start:Document)
        USING INDEX start:Document(doc_number)
        WHERE start.doc_number = $doc_number
           OR start.id = $doc_number
           OR start.id = 'ROOT/' + $doc_number
           OR start.doc_number = replace($doc_number, 'ROOT/', '')
        MATCH path = (start)-[:AMENDS|REPLACES|REFERENCES*0..10]->(current)
        WITH path, current
        ORDER BY length(path) DESC
        LIMIT 1
        RETURN
            [i in range(0, length(path)) | {
                doc_number: nodes(path)[i].doc_number,
                id: nodes(path)[i].id,
                effective_date: coalesce(nodes(path)[i].effective_date, nodes(path)[i].date, 'unknown'),
                status: coalesce(nodes(path)[i].status, 'UNKNOWN'),
                relation_to_next: CASE
                    WHEN i < length(path) THEN type(relationships(path)[i])
                    ELSE null
                END
            }] AS timeline
        """
        try:
            async with self._driver.session() as session:
                result = await session.run(query, doc_number=doc_number)
                record = await result.single()
                if record:
                    return record["timeline"]
        except Exception as e:
            logger.error(f"Failed to retrieve legal timeline for {doc_number}: {e}")
        return []

    async def generate_timeline_summary(self, timeline: list, user_query: str) -> str:
        """
        Use rag-core via LiteLLM API to summarize the legal timeline in natural language.
        """
        if not timeline:
            return ""

        prompt = f"""Dựa trên dòng thời gian pháp lý sau đây, hãy trả lời câu hỏi của người dùng: "{user_query}"

        Dòng thời gian (Timeline):
        {json.dumps(timeline, ensure_ascii=False, indent=2)}

        Yêu cầu trả lời:
        1. Liệt kê rõ thứ tự thay đổi (kèm ngày hiệu lực nếu có).
        2. Xác định rõ văn bản nào đang là HIỆN HÀNH (ACTIVE) và văn bản nào đã HẾT HIỆU LỰC (OUTDATED).
        3. Giải thích ngắn gọn mối liên hệ giữa chúng dựa vào timeline.
        4. Trình bày bằng tiếng Việt, rõ ràng, dễ hiểu.
        """

        try:
            raw_summary = await self.ai_client.complete(
                [
                    {
                        "role": "system",
                        "content": (
                            "Bạn là chuyên gia về pháp luật và đồ thị tri thức. "
                            "Hãy tóm tắt timeline pháp lý một cách chính xác. "
                            "TUYỆT ĐỐI KHÔNG xuất quá trình suy luận hay thinking process, chỉ xuất câu trả lời trực tiếp."
                        ),
                    },
                    {"role": "user", "content": prompt}
                ],
                model="claude-haiku-4",
                model_chain=["claude-haiku-4", "rag-core"],
                timeout=5.0,
            )
            from ingestion.normalizers.boilerplate import strip_ai_monologue
            return strip_ai_monologue(raw_summary)
        except Exception as e:
            logger.error(f"Error generating timeline summary: {e}")

        return "Không thể tạo tóm tắt dòng thời gian tại thời điểm này."
