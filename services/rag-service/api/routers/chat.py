from fastapi import APIRouter, Depends
from models.schemas import ChatRequest, ChatResponse
from core.database import get_chat_service
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/chat", tags=["Generation"], response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    service=Depends(get_chat_service),
):
    """
    Generate a chat response with retrieved legal document context.
    Supports Context Lake features: session memory, agentic retrieval.
    """
    return await service.generate_response(
        query=request.query,
        history=request.history,
        language=request.language,
        model=request.model,
        session_id=request.session_id,
        use_agentic=request.use_agentic,
    )
