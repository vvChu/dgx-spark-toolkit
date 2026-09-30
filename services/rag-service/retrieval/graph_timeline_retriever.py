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
        Iterative Cypher traversal to retrieve comprehensive legal timeline for a document node.

        Traverses:
        - Promulgating circulars: (promulgator)-[:PROMULGATES]->(start)
        - Outgoing promulgations: (start)-[:PROMULGATES]->(promulgated)
        - Amending circulars: (amender)-[:AMENDS]->(start)
        - Outgoing amendments: (start)-[:AMENDS]->(amended)
        - Replacement chains: (start)-[:REPLACES*1..10]->(old)
        - Superseding documents: (newer)-[:REPLACES]->(start)
        """
        if not doc_number or not self._driver:
            return []

        query = """
        MATCH (start:Document)
        WHERE start.doc_number = $doc_number
           OR start.id = $doc_number
           OR start.id = 'VBPL/' + $doc_number
           OR start.id = 'ROOT/' + $doc_number
           OR start.doc_number = replace($doc_number, 'ROOT/', '')
        WITH start LIMIT 1
        OPTIONAL MATCH (newer:Document)-[:REPLACES]->(start)
        OPTIONAL MATCH (p:Document)-[:PROMULGATES]->(start)
        OPTIONAL MATCH (start)-[:PROMULGATES]->(out_p:Document)
        OPTIONAL MATCH (a:Document)-[:AMENDS]->(start)
        OPTIONAL MATCH (start)-[:AMENDS]->(out_a:Document)
        OPTIONAL MATCH path = (start)-[:REPLACES|REFERENCES*1..10]->(current)
        WITH start,
             collect(DISTINCT newer) AS superseding,
             collect(DISTINCT p) AS promulgators,
             collect(DISTINCT out_p) AS out_promulgates,
             collect(DISTINCT a) AS amenders,
             collect(DISTINCT out_a) AS out_amends,
             collect(path) AS rep_paths
        RETURN start, superseding, promulgators, out_promulgates, amenders, out_amends, rep_paths
        """
        try:
            async with self._driver.session() as session:
                result = await session.run(query, doc_number=doc_number)
                record = await result.single()
                if not record or not record.get("start"):
                    return []

                start = record["start"]
                superseding = record["superseding"]
                promulgators = record["promulgators"]
                out_promulgates = record["out_promulgates"]
                amenders = record["amenders"]
                out_amends = record["out_amends"]
                rep_paths = record["rep_paths"]

                timeline: list[dict] = []

                # 1. Superseding documents
                for n in superseding:
                    timeline.append({
                        "doc_number": n.get("doc_number") or n.get("id"),
                        "id": n.get("id"),
                        "effective_date": n.get("effective_date") or n.get("date") or "unknown",
                        "status": n.get("status", "ACTIVE"),
                        "relation_to_next": "REPLACES",
                    })

                # 2. Promulgating circulars
                for p in promulgators:
                    timeline.append({
                        "doc_number": p.get("doc_number") or p.get("id"),
                        "id": p.get("id"),
                        "effective_date": p.get("effective_date") or p.get("date") or "unknown",
                        "status": p.get("status", "ACTIVE"),
                        "relation_to_next": "PROMULGATES",
                    })

                # 3. Amending circulars
                for a in amenders:
                    timeline.append({
                        "doc_number": a.get("doc_number") or a.get("id"),
                        "id": a.get("id"),
                        "effective_date": a.get("effective_date") or a.get("date") or "unknown",
                        "status": a.get("status", "ACTIVE"),
                        "relation_to_next": "AMENDS",
                    })

                # 4. Longest replacement path
                longest_path = None
                if rep_paths:
                    valid_paths = [p for p in rep_paths if p and hasattr(p, "relationships")]
                    if valid_paths:
                        longest_path = max(valid_paths, key=lambda p: len(p.relationships))

                # Determine start's relation_to_next
                start_rel = None
                if out_promulgates:
                    start_rel = "PROMULGATES"
                elif out_amends:
                    start_rel = "AMENDS"
                elif longest_path and len(longest_path.relationships) > 0:
                    start_rel = longest_path.relationships[0].type

                timeline.append({
                    "doc_number": start.get("doc_number") or start.get("id"),
                    "id": start.get("id"),
                    "effective_date": start.get("effective_date") or start.get("date") or "unknown",
                    "status": start.get("status", "UNKNOWN"),
                    "relation_to_next": start_rel,
                })

                # 5. Outgoing promulgations
                for op in out_promulgates:
                    timeline.append({
                        "doc_number": op.get("doc_number") or op.get("id"),
                        "id": op.get("id"),
                        "effective_date": op.get("effective_date") or op.get("date") or "unknown",
                        "status": op.get("status", "ACTIVE"),
                        "relation_to_next": None,
                    })

                # 6. Outgoing amendments
                for oa in out_amends:
                    timeline.append({
                        "doc_number": oa.get("doc_number") or oa.get("id"),
                        "id": oa.get("id"),
                        "effective_date": oa.get("effective_date") or oa.get("date") or "unknown",
                        "status": oa.get("status", "ACTIVE"),
                        "relation_to_next": None,
                    })

                # 7. Predecessors in replacement chain
                if longest_path:
                    path_nodes = list(longest_path.nodes)
                    path_rels = list(longest_path.relationships)
                    for i in range(1, len(path_nodes)):
                        node = path_nodes[i]
                        rel_type = path_rels[i].type if i < len(path_rels) else None
                        timeline.append({
                            "doc_number": node.get("doc_number") or node.get("id"),
                            "id": node.get("id"),
                            "effective_date": node.get("effective_date") or node.get("date") or "unknown",
                            "status": node.get("status", "OUTDATED"),
                            "relation_to_next": rel_type,
                        })

                return timeline
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

        realtime_model = os.getenv("REALTIME_CHAT_MODEL", "fast-realtime")
        realtime_timeout = float(os.getenv("TIMELINE_TIMEOUT_SECONDS", "5.0"))
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
                model=realtime_model,
                model_chain=[realtime_model, "rag-core"],
                timeout=realtime_timeout,
            )
            from ingestion.normalizers.boilerplate import strip_ai_monologue
            return strip_ai_monologue(raw_summary)
        except Exception as e:
            logger.error(f"Error generating timeline summary: {e}")

        return "Không thể tạo tóm tắt dòng thời gian tại thời điểm này."
