"""Evaluation and feedback endpoints."""
from fastapi import APIRouter, Depends
from core.config import get_settings
from core.database import get_http_client
from models.schemas import EvaluationRequest, EvaluationResponse, FeedbackRequest

import httpx
import json
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
    gateway_url = settings.VLLM_API_BASE
    model = settings.DEFAULT_RAG_MODEL

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
        resp = await http_client.post(
            f"{gateway_url}/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": eval_prompt}],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        result = json.loads(content)
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
