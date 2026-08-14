"""Multi-hop agentic retrieval facade delegating to SearchPipeline.

Preserves backward compatibility for callers while consolidating execution into SearchPipeline.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from core.ai_gateway_client import get_ai_gateway_client, AIGatewayClient
from retrieval.query_tracer import QueryTracer

logger = logging.getLogger(__name__)


@dataclass
class AgenticResult:
    """Result from multi-hop retrieval."""
    results: list[dict] = field(default_factory=list)
    hops: int = 0
    sub_queries: list[str] = field(default_factory=list)
    reasoning: str = ""


class AgenticRetriever:
    """Facade for multi-hop retrieval, delegating directly to SearchPipeline."""

    def __init__(self, retrieval_service: Any = None, http_client: Any = None, ai_client: Optional[AIGatewayClient] = None):
        self.retrieval_service = retrieval_service
        self.http_client = http_client
        self.ai_client = ai_client or get_ai_gateway_client(http_client)

    async def retrieve(
        self,
        query: str,
        tracer: Optional[QueryTracer] = None,
        session_id: Optional[str] = None,
    ) -> AgenticResult:
        """Execute multi-hop retrieval via SearchPipeline."""
        if self.retrieval_service is not None and hasattr(self.retrieval_service, "search"):
            res = await self.retrieval_service.search(
                query=query,
                limit=15,
                use_reranker=True,
                use_agentic=True,
                session_id=session_id,
                tracer=tracer,
            )
            return AgenticResult(
                results=res.get("results", []),
                hops=res.get("hops", 1),
                sub_queries=res.get("sub_queries", [query]),
                reasoning=res.get("reasoning", ""),
            )

        logger.warning("No search pipeline attached to AgenticRetriever; returning empty result.")
        return AgenticResult(results=[], hops=0, sub_queries=[query], reasoning="No retrieval service")
