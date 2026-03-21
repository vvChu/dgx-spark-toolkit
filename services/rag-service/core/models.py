from pydantic import BaseModel, Field
from typing import List, Optional, Dict

class SearchRequest(BaseModel):
    query: str
    limit: int = 10
    use_reranker: bool = True
    doc_type: Optional[str] = None
    authority: Optional[str] = None
    year: Optional[int] = None
    doc_number: Optional[str] = None
    use_hyde: bool = False
    use_cache: bool = True

class ChatRequest(BaseModel):
    query: str
    history: Optional[List[Dict[str, str]]] = []
    context_limit: Optional[int] = 5
    language: Optional[str] = "vi" # vi or en
    model: Optional[str] = None # Optional override

class FeedbackRequest(BaseModel):
    query: str
    answer: str
    is_positive: bool 
    comment: Optional[str] = None

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
