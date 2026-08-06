"""Multi-hop agentic retrieval with plan-retrieve-reflect loop.

For complex legal queries that require information from multiple documents
or sections, the agent decomposes the query into sub-queries, retrieves
iteratively, and evaluates whether the collected evidence is sufficient.
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from core.config import get_settings
from core.llm_client import call_llm
from retrieval.query_tracer import QueryTracer

logger = logging.getLogger(__name__)

_PLAN_PROMPT = """Bạn là chuyên gia pháp luật Việt Nam. Phân tích câu hỏi sau và xác định các thông tin cần tra cứu.

Câu hỏi: {query}

Trả về JSON với format:
{{
  "sub_queries": ["câu hỏi phụ 1", "câu hỏi phụ 2"],
  "reasoning": "giải thích tại sao cần các thông tin này"
}}

Quy tắc:
- Nếu câu hỏi đơn giản, trả về 1 sub_query giống câu hỏi gốc.
- Nếu phức tạp (so sánh, liên hệ giữa nhiều luật), chia thành 2-3 sub_queries.
- Tối đa 3 sub_queries."""

_EVAL_PROMPT = """Đánh giá xem context dưới đây có đủ để trả lời câu hỏi không.

Câu hỏi: {query}

Context đã thu thập:
{context}

Trả về JSON:
{{
  "is_sufficient": true/false,
  "confidence": 0.0-1.0,
  "missing": "mô tả thông tin còn thiếu (nếu có)",
  "follow_up_query": "câu hỏi bổ sung (nếu cần)"
}}"""


@dataclass
class AgenticResult:
    """Result from multi-hop retrieval."""
    results: list[dict] = field(default_factory=list)
    hops: int = 0
    sub_queries: list[str] = field(default_factory=list)
    reasoning: str = ""


class AgenticRetriever:
    """Multi-hop retrieval with plan → retrieve → reflect loop."""

    MAX_HOPS = 3
    SUFFICIENCY_THRESHOLD = 0.70

    def __init__(self, retrieval_service, http_client):
        self.retrieval_service = retrieval_service
        self.http_client = http_client

    async def retrieve(
        self,
        query: str,
        tracer: Optional[QueryTracer] = None,
        session_id: Optional[str] = None,
    ) -> AgenticResult:
        """Execute multi-hop retrieval.

        1. Plan: Decompose query into sub-queries
        2. Retrieve: Execute each sub-query
        3. Reflect: Evaluate if context is sufficient
        4. Repeat if needed (up to MAX_HOPS)
        """
        settings = get_settings()
        result = AgenticResult()

        # Step 1: Plan
        if tracer:
            tracer.start_step("agentic_plan")
        plan = await self._plan(query)
        result.sub_queries = plan.get("sub_queries", [query])
        result.reasoning = plan.get("reasoning", "")
        if tracer:
            tracer.end_step(sub_queries=result.sub_queries)

        # Collect all results across hops
        all_results: list[dict] = []
        seen_texts: set[str] = set()

        for hop in range(self.MAX_HOPS):
            result.hops = hop + 1

            # Step 2: Retrieve for each sub-query
            if tracer:
                tracer.start_step(f"agentic_retrieve_hop{hop + 1}")

            queries_to_run = result.sub_queries if hop == 0 else [plan.get("follow_up_query", query)]

            for sub_q in queries_to_run:
                if not sub_q:
                    continue
                search_res = await self.retrieval_service.search(
                    query=sub_q,
                    limit=10,
                    use_reranker=True,
                    use_cache=True,
                )
                for r in search_res.get("results", []):
                    text_key = r.get("text", "")[:200]
                    if text_key not in seen_texts:
                        seen_texts.add(text_key)
                        all_results.append(r)

            if tracer:
                tracer.end_step(total_results=len(all_results))

            # Step 3: Evaluate sufficiency (skip on last hop)
            if hop < self.MAX_HOPS - 1 and len(all_results) > 0:
                if tracer:
                    tracer.start_step("agentic_evaluate")

                evaluation = await self._evaluate(query, all_results)
                confidence = evaluation.get("confidence", 1.0)
                is_sufficient = evaluation.get("is_sufficient", True)

                if tracer:
                    tracer.end_step(
                        confidence=confidence,
                        is_sufficient=is_sufficient,
                    )

                if is_sufficient or confidence >= self.SUFFICIENCY_THRESHOLD:
                    break

                # Refine plan for next hop
                follow_up = evaluation.get("follow_up_query", "")
                if follow_up:
                    plan["follow_up_query"] = follow_up
                    result.sub_queries.append(follow_up)
                else:
                    break  # No follow-up suggested, stop
            else:
                break

        # Sort by score and return top results
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        result.results = all_results[:15]
        return result

    async def _plan(self, query: str) -> dict:
        """Decompose query into sub-queries using LLM."""
        try:
            settings = get_settings()
            messages = [
                {"role": "system", "content": "You are a JSON-only response bot."},
                {"role": "user", "content": _PLAN_PROMPT.format(query=query)},
            ]
            response = await call_llm(
                self.http_client,
                messages,
                model=settings.DEFAULT_RAG_MODEL,
                max_tokens=500,
                temperature=0.1,
            )
            # Extract JSON from response
            return self._parse_json(response)
        except Exception as e:
            logger.warning("Agentic plan failed: %s", e)
            return {"sub_queries": [query], "reasoning": "Fallback to direct query"}

    async def _evaluate(self, query: str, results: list[dict]) -> dict:
        """Evaluate if collected context is sufficient."""
        try:
            settings = get_settings()
            context_str = "\n".join([
                f"[{r.get('doc_number', '?')}] {r.get('text', '')[:500]}"
                for r in results[:10]
            ])
            messages = [
                {"role": "system", "content": "You are a JSON-only response bot."},
                {"role": "user", "content": _EVAL_PROMPT.format(query=query, context=context_str)},
            ]
            response = await call_llm(
                self.http_client,
                messages,
                model=settings.DEFAULT_RAG_MODEL,
                max_tokens=300,
                temperature=0.1,
            )
            return self._parse_json(response)
        except Exception as e:
            logger.warning("Agentic evaluation failed: %s", e)
            return {"is_sufficient": True, "confidence": 1.0}

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Extract JSON from LLM response, handling markdown code blocks."""
        text = text.strip()
        # Remove markdown code fences
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                try:
                    return json.loads(part)
                except (json.JSONDecodeError, ValueError):
                    continue
        try:
            # Try parsing the whole response as JSON
            start = text.index("{")
            end = text.rindex("}") + 1
            return json.loads(text[start:end])
        except (json.JSONDecodeError, ValueError):
            return {}
