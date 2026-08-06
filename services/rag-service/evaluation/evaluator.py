"""Unified deep RAGEvaluator module for RAG quality scoring and scorecard metrics."""
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import httpx

from core.ai_gateway_client import AIGatewayClient
from core.config import get_settings

logger = logging.getLogger(__name__)


class EvaluationScorecard(BaseModel):
    """Structured RAG evaluation scorecard."""

    faithfulness: float = Field(default=0.5, ge=0.0, le=1.0)
    relevancy: float = Field(default=0.5, ge=0.0, le=1.0)
    faithfulness_reason: str = Field(default="Evaluation completed")
    relevancy_reason: str = Field(default="Evaluation completed")
    suggestions: List[str] = Field(default_factory=list)
    overall_score: float = Field(default=50.0)


class RAGEvaluator:
    """Deep domain module for LLM-as-judge RAG quality evaluation."""

    def __init__(self, ai_gateway_client: Optional[AIGatewayClient] = None, http_client: Optional[httpx.AsyncClient] = None):
        self.ai_gateway_client = ai_gateway_client or AIGatewayClient(http_client=http_client)
        self.settings = get_settings()

    async def evaluate_pair(
        self,
        query: str,
        answer: str,
        context: List[str],
        ground_truth: Optional[str] = None,
        model: Optional[str] = None,
    ) -> EvaluationScorecard:
        """Evaluate a RAG Q&A pair and return a structured EvaluationScorecard."""
        context_text = "\n---\n".join(context[:5]) if context else "No context provided."

        eval_prompt = f"""You are an expert evaluator for a Vietnamese legal RAG system.

Given:
- Question: {query}
- Answer: {answer}
- Retrieved Context: {context_text}

Evaluate on two dimensions:
1. **Faithfulness** (0.0-1.0): Is the answer fully supported by the context? No hallucinations?
2. **Relevancy** (0.0-1.0): Does the answer address the question using the context?

Respond in JSON matching this schema:
{{
  "faithfulness": <float between 0.0 and 1.0>,
  "relevancy": <float between 0.0 and 1.0>,
  "faithfulness_reason": "<1 sentence>",
  "relevancy_reason": "<1 sentence>",
  "suggestions": ["<optional improvement>"]
}}"""

        try:
            raw_res = await self.ai_gateway_client.extract_json(
                eval_prompt,
                schema=EvaluationScorecard,
                model=model or self.settings.DEFAULT_RAG_MODEL,
            )
            scorecard = EvaluationScorecard(**raw_res)
            scorecard.overall_score = round((scorecard.faithfulness + scorecard.relevancy) / 2.0 * 100.0, 1)
            return scorecard
        except Exception as e:
            logger.error(f"RAGEvaluator failure: {e}", exc_info=True)
            return EvaluationScorecard(
                faithfulness=0.5,
                relevancy=0.5,
                faithfulness_reason="Evaluation failed — returning default scores.",
                relevancy_reason=str(e),
                suggestions=["Retry evaluation"],
                overall_score=50.0,
            )


class MockRAGEvaluator(RAGEvaluator):
    """In-memory test adapter for RAGEvaluator."""

    def __init__(self, faithfulness: float = 0.9, relevancy: float = 0.8):
        self.faithfulness = faithfulness
        self.relevancy = relevancy
        self.call_history: List[Dict[str, Any]] = []

    async def evaluate_pair(self, query: str, answer: str, context: List[str], **kwargs) -> EvaluationScorecard:
        self.call_history.append({"query": query, "answer": answer, "context": context, "kwargs": kwargs})
        return EvaluationScorecard(
            faithfulness=self.faithfulness,
            relevancy=self.relevancy,
            faithfulness_reason="Supported",
            relevancy_reason="Relevant",
            suggestions=["None"],
            overall_score=round((self.faithfulness + self.relevancy) / 2.0 * 100.0, 1),
        )
