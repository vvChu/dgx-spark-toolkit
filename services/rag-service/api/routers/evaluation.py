"""Evaluation and feedback endpoints."""
from fastapi import APIRouter, Depends
from core.config import get_settings
from core.database import get_http_client
from core.llm_client import call_llm_json
from models.schemas import EvaluationRequest, EvaluationResponse, FeedbackRequest

import httpx
import logging

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Monitoring"])


@router.post("/evaluate", response_model=EvaluationResponse, tags=["Monitoring"])
async def evaluate(
    request: EvaluationRequest,
    http_client: httpx.AsyncClient = Depends(get_http_client),
):
    """Evaluate RAG answer quality using LLM-as-judge."""
    settings = get_settings()

    context_text = "\n---\n".join(request.context[:5])

    eval_prompt = f"""You are an expert evaluator for a Vietnamese legal RAG system.

Given:
- Question: {request.query}
- Answer: {request.answer}
- Retrieved Context: {context_text}

Evaluate on two dimensions:
1. **Faithfulness** (0.0-1.0): Is the answer fully supported by the context? No hallucinations?
2. **Relevancy** (0.0-1.0): Does the answer address the question using the context?

Respond in JSON:
{{"faithfulness": <float>, "relevancy": <float>, "faithfulness_reason": "<1 sentence>", "relevancy_reason": "<1 sentence>", "suggestions": ["<optional improvement>"]}}
"""

    try:
        result = await call_llm_json(
            http_client,
            [{"role": "user", "content": eval_prompt}],
            model=settings.DEFAULT_RAG_MODEL,
        )
        return EvaluationResponse(**result)
    except Exception as e:
        logger.error(f"Evaluation error: {e}", exc_info=True)
        return EvaluationResponse(
            faithfulness=0.5,
            relevancy=0.5,
            faithfulness_reason="Evaluation failed — returning default scores.",
            relevancy_reason=str(e),
            suggestions=["Retry evaluation"],
        )


@router.post("/feedback", tags=["Monitoring"])
async def submit_feedback(request: FeedbackRequest):
    """Log user feedback."""
    logger.info(
        "USER_FEEDBACK",
        extra={
            "query": request.query[:200],
            "is_positive": request.is_positive,
            "comment": request.comment,
        },
    )
    return {"status": "ok", "message": "Feedback recorded"}
