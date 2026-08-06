"""Evaluation and feedback endpoints."""
from fastapi import APIRouter, Depends
from core.database import get_rag_evaluator
from evaluation.evaluator import RAGEvaluator
from models.schemas import EvaluationRequest, EvaluationResponse, FeedbackRequest

import logging

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Monitoring"])


@router.post("/evaluate", response_model=EvaluationResponse, tags=["Monitoring"])
async def evaluate(
    request: EvaluationRequest,
    evaluator: RAGEvaluator = Depends(get_rag_evaluator),
):
    """Evaluate RAG answer quality using deep RAGEvaluator."""
    scorecard = await evaluator.evaluate_pair(
        query=request.query,
        answer=request.answer,
        context=request.context,
    )
    return EvaluationResponse(
        faithfulness=scorecard.faithfulness,
        relevancy=scorecard.relevancy,
        faithfulness_reason=scorecard.faithfulness_reason,
        relevancy_reason=scorecard.relevancy_reason,
        suggestions=scorecard.suggestions,
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
