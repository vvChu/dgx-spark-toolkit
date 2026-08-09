"""Server-Sent Events (SSE) streaming endpoint for chat responses.

Provides real-time token streaming for the /chat/stream endpoint,
delegating RAG context assembly, token streaming, and session tracking
to the deep ChatService module behind a single seam.
"""
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from models.schemas import ChatRequest
from core.database import get_chat_service
from services.chat_service import ChatService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/chat/stream", tags=["Generation"])
async def chat_stream_endpoint(
    request: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
):
    """Stream a chat response with retrieved legal document context via SSE."""
    return StreamingResponse(
        chat_service.stream_response(
            query=request.query,
            history=request.history,
            language=request.language,
            model=request.model,
            session_id=request.session_id,
            use_agentic=getattr(request, "use_agentic", False),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
