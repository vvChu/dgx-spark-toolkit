from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Dict, Any


class SearchRequest(BaseModel):
    query: str
    limit: int = 10
    use_reranker: bool = True
    doc_type: Optional[str] = None
    authority: Optional[str] = None
    year: Optional[int] = None
    doc_number: Optional[str] = None
    use_hyde: Optional[bool] = None
    use_cache: Optional[bool] = None
    session_id: Optional[str] = None  # Context Lake: session-scoped context

    @model_validator(mode="before")
    @classmethod
    def apply_settings_defaults(cls, values):
        """Apply config defaults at request time, not import time."""
        from core.config import get_settings
        settings = get_settings()
        if values.get("use_hyde") is None:
            values["use_hyde"] = settings.ENABLE_HYDE
        if values.get("use_cache") is None:
            values["use_cache"] = settings.ENABLE_SEMANTIC_CACHE
        return values


class ChatRequest(BaseModel):
    query: str
    history: Optional[List[Dict[str, str]]] = []
    context_limit: Optional[int] = 5
    language: Optional[str] = "vi"  # vi or en
    model: Optional[str] = None  # Optional override
    session_id: Optional[str] = None  # Context Lake: session-scoped memory
    use_agentic: Optional[bool] = False  # Context Lake: multi-hop retrieval


class EvaluationRequest(BaseModel):
    query: str
    answer: str
    context: List[str]


class EvaluationResponse(BaseModel):
    faithfulness: float
    relevancy: float
    faithfulness_reason: str
    relevancy_reason: str
    suggestions: Optional[List[str]] = None


class FeedbackRequest(BaseModel):
    query: str
    answer: str
    is_positive: bool
    comment: Optional[str] = None


class ConflictAnalysisRequest(BaseModel):
    doc_id: str
    query: str  # The topic to analyze (e.g., "regulations on fire safety")
    depth: int = 1


class ComplianceCheckRequest(BaseModel):
    project_profile: str
    focus_area: Optional[str] = "BIM"


class UpdateRelationRequest(BaseModel):
    source_id: str
    target_id: str
    rel_type: str
    action: str  # "ADD" or "DELETE"


class SyncStatusRequest(BaseModel):
    doc_id: str
    new_status: str = Field(..., pattern="^(ACTIVE|OUTDATED|REPLACED|EXPIRED)$")


# ── Response Models ──────────────────────────────────────────────────────

class SearchResultItem(BaseModel):
    """A single document chunk returned from search."""
    text: str
    doc_number: str = ""
    page: int = 0
    score: float = 0.0
    bbox: Optional[List[float]] = None
    doc_type: Optional[str] = None
    authority: Optional[str] = None
    year: Optional[int] = None
    doc_id: Optional[str] = None

    model_config = {"extra": "allow"}


class SearchResponse(BaseModel):
    """Response from /search and /retrieve endpoints."""
    results: List[SearchResultItem] = []
    query: str = ""
    rewritten_query: Optional[str] = None
    cached: bool = False
    trace: Optional[Dict[str, Any]] = None  # Context Lake: reasoning trace


class ChatResponse(BaseModel):
    """Response from /chat endpoint."""
    answer: str
    context: List[Dict[str, Any]] = []
    usage: Optional[Dict[str, Any]] = None
    cached: bool = False
    thought: Optional[str] = None
    session_id: Optional[str] = None  # Context Lake: session identifier
    trace: Optional[Dict[str, Any]] = None  # Context Lake: reasoning trace


class HealthCheckResponse(BaseModel):
    """Response from /health endpoint."""
    status: str
    version: str
    checks: Dict[str, str]


class StatsResponse(BaseModel):
    """Response from /stats endpoint."""
    neo4j_docs: int = 0
    neo4j_rels: int = 0
    milvus_entities: int = 0
    total_target: int = 8870


class SyncStatusResponse(BaseModel):
    """Response from /admin/sync-status endpoint."""
    status: str
    doc_id: str
    new_status: str
    updates: Dict[str, str] = {}


class DiagramGenerationRequest(BaseModel):
    """Request for generating visual SOP/QCVN workflow diagrams via Imagen 4 Fast."""
    sop_title: str
    workflow_steps: List[str]
    style: Optional[str] = "technical_flowchart"


class DiagramGenerationResponse(BaseModel):
    """Response containing generated diagram metadata and image prompt."""
    status: str
    sop_title: str
    image_prompt: str
    model: str = "imagen-4-fast"
    daily_quota_limit: int = 25

