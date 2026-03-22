from fastapi import APIRouter, Depends
from models.schemas import ChatRequest, ChatResponse
from core.database import get_milvus_repo, get_neo4j_repo, get_http_client
from repositories.milvus_repo import MilvusRepository
from repositories.neo4j_repo import Neo4jRepository
from services.chat_service import ChatService
import httpx
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_legal_docs",
        "description": "Semantic search for specific information within legal and BIM documents. Priority: Construction (BXD), BIM (ISO), and Government Decrees (ND-CP). Always include relevant domain keywords in query if ambiguous.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The semantic search query for document retrieval."},
                "limit": {"type": "integer", "description": "Number of document chunks to retrieve (default 5)."},
                "doc_type": {"type": "string", "description": "Filter by type (QD, TT, ND, etc.) if known."}
            },
            "required": ["query"]
        }
    }
}

GRAPH_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "graph_search",
        "description": "Traverse the legal graph to find relations (REPLACES, AMENDS, REFERENCES) or descendants (GUIDES) of a document.",
        "parameters": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "description": "The document exact ID/Number (e.g. 15/2021/ND-CP)"},
                "find_guides": {"type": "boolean", "description": "If true, finds Circulars (Thông tư) that guide this Decree (Nghị định)."}
            },
            "required": ["doc_id"]
        }
    }
}

@router.post("/chat", tags=["Generation"], response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    milvus_repo: MilvusRepository = Depends(get_milvus_repo),
    neo4j_repo: Neo4jRepository = Depends(get_neo4j_repo),
    http_client: httpx.AsyncClient = Depends(get_http_client),
):
    """
    Generate a chat response with retrieved legal document context.
    """
    service = ChatService(milvus_repo, neo4j_repo, http_client)
    return await service.generate_response(
        query=request.query,
        history=request.history,
        language=request.language,
        model=request.model
    )
