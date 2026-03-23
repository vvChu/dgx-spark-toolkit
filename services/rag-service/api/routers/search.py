from fastapi import APIRouter, Depends
from models.schemas import SearchRequest, SearchResponse
from core.database import get_neo4j_repo, get_milvus_repo
from repositories.neo4j_repo import Neo4jRepository
from repositories.milvus_repo import MilvusRepository
from services.retrieval_service import RetrievalService
from retrieval.query_rewriter import rewrite_query

import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/search", tags=["Retrieval"], response_model=SearchResponse)
@router.post("/retrieve", tags=["Retrieval"], include_in_schema=False)
async def search_endpoint(
    request: SearchRequest,
    milvus_repo: MilvusRepository = Depends(get_milvus_repo),
    neo4j_repo: Neo4jRepository = Depends(get_neo4j_repo)
):
    """
    Perform semantic search with optional reranking and graph augmentation.
    """
    service = RetrievalService(milvus_repo, neo4j_repo)
    return await service.search(
        query=request.query,
        limit=request.limit,
        use_reranker=request.use_reranker,
        doc_type=request.doc_type,
        authority=request.authority,
        year=request.year,
        doc_number=request.doc_number,
        use_hyde=request.use_hyde,
        use_cache=request.use_cache
    )
