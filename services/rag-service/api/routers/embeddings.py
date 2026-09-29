"""FastAPI router for OpenAI-compatible embedding endpoint using BAAI/bge-m3."""

from __future__ import annotations

import asyncio
from typing import List, Optional, Union
from fastapi import APIRouter
from pydantic import BaseModel
from retrieval.search_pipeline import get_embedding_model

router = APIRouter()


class EmbeddingRequest(BaseModel):
    """OpenAI-compatible embedding request schema."""

    input: Union[str, List[str]]
    model: Optional[str] = "bge-m3"
    user: Optional[str] = None
    encoding_format: Optional[str] = "float"


class EmbeddingObject(BaseModel):
    """OpenAI-compatible single embedding object."""

    object: str = "embedding"
    index: int
    embedding: List[float]


class EmbeddingUsage(BaseModel):
    """Token usage metadata."""

    prompt_tokens: int
    total_tokens: int


class EmbeddingResponse(BaseModel):
    """OpenAI-compatible embedding list response."""

    object: str = "list"
    data: List[EmbeddingObject]
    model: str
    usage: EmbeddingUsage


@router.post("/v1/embeddings", tags=["Retrieval"], response_model=EmbeddingResponse)
@router.post(
    "/embeddings", tags=["Retrieval"], response_model=EmbeddingResponse, include_in_schema=False
)
async def create_embeddings(request: EmbeddingRequest) -> EmbeddingResponse:
    """Generate dense vector embeddings using BAAI/bge-m3."""
    texts = [request.input] if isinstance(request.input, str) else request.input
    model = get_embedding_model()

    dense_vectors = await asyncio.to_thread(
        model.encode_dense_only, texts, batch_size=8, max_length=2048
    )

    data = [
        EmbeddingObject(object="embedding", index=i, embedding=vec)
        for i, vec in enumerate(dense_vectors)
    ]
    token_count = sum(len(t.split()) for t in texts)
    return EmbeddingResponse(
        object="list",
        data=data,
        model=request.model or "bge-m3",
        usage=EmbeddingUsage(prompt_tokens=token_count, total_tokens=token_count),
    )
