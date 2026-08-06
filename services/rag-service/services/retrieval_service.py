"""RetrievalService Facade module delegating search execution to SearchPipeline."""
import logging
from typing import Dict, Any, Optional

from repositories.milvus_repo import MilvusRepository
from repositories.neo4j_repo import Neo4jRepository
from retrieval.search_pipeline import SearchPipeline, SearchContext, get_embedding_model
from retrieval.query_tracer import QueryTracer

logger = logging.getLogger(__name__)


class RetrievalService:
    def __init__(self, milvus_repo: MilvusRepository, neo4j_repo: Neo4jRepository):
        self.milvus = milvus_repo
        self.neo4j = neo4j_repo
        self.pipeline = SearchPipeline(milvus_repo, neo4j_repo)

    async def search(
        self,
        query: str,
        limit: int = 10,
        use_reranker: bool = True,
        doc_type: Optional[str] = None,
        authority: Optional[str] = None,
        year: Optional[int] = None,
        doc_number: Optional[str] = None,
        use_hyde: bool = False,
        use_cache: bool = True,
        session_id: Optional[str] = None,
        tracer: Optional[QueryTracer] = None,
    ) -> Dict[str, Any]:
        """End-to-end search facade delegating to SearchPipeline."""
        ctx = SearchContext(
            raw_query=query,
            limit=limit,
            use_reranker=use_reranker,
            doc_type=doc_type,
            authority=authority,
            year=year,
            doc_number=doc_number,
            use_hyde=use_hyde,
            use_cache=use_cache,
            session_id=session_id,
            tracer=tracer,
        )
        return await self.pipeline.execute(ctx)
