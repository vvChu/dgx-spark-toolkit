from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from core.config import get_settings

settings = get_settings()

class SearchRequest(BaseModel):
    query: str
    limit: int = 10
    use_reranker: bool = True
    doc_type: Optional[str] = None
    authority: Optional[str] = None
    year: Optional[int] = None
    doc_number: Optional[str] = None
    use_hyde: bool = Field(default=settings.ENABLE_HYDE)
    use_cache: bool = Field(default=settings.ENABLE_SEMANTIC_CACHE)

class ChatRequest(BaseModel):
    query: str
    history: Optional[List[Dict[str, str]]] = []
    context_limit: Optional[int] = 5
    language: Optional[str] = "vi" # vi or en
    model: Optional[str] = None # Optional override

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
    query: str # The topic to analyze (e.g., "regulations on fire safety")
    depth: int = 1

class ComplianceCheckRequest(BaseModel):
    project_profile: str
    focus_area: Optional[str] = "BIM"

class UpdateRelationRequest(BaseModel):
    source_id: str
    target_id: str
    rel_type: str
    action: str # "ADD" or "DELETE"

class SyncStatusRequest(BaseModel):
    doc_id: str
    new_status: str = Field(..., pattern="^(ACTIVE|OUTDATED|REPLACED|EXPIRED)$")
