from fastapi import APIRouter, Depends
from models.schemas import SearchRequest, SearchResponse
from core.database import get_retrieval_service

import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/search", tags=["Retrieval"], response_model=SearchResponse)
@router.post("/retrieve", tags=["Retrieval"], include_in_schema=False)
async def search_endpoint(
    request: SearchRequest,
    service=Depends(get_retrieval_service),
):
    """
    Perform semantic search with optional reranking and graph augmentation.
    """
    return await service.search(
        query=request.query,
        limit=request.limit,
        use_reranker=request.use_reranker,
        doc_type=request.doc_type,
        authority=request.authority,
        year=request.year,
        doc_number=request.doc_number,
        use_hyde=request.use_hyde,
        use_cache=request.use_cache,
        session_id=request.session_id,
    )
