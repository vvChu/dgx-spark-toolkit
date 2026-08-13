"""Unit tests for the deep RAGEvaluator module and MockRAGEvaluator adapter."""
import asyncio
import pytest
from unittest.mock import AsyncMock

from evaluation.evaluator import RAGEvaluator, MockRAGEvaluator, EvaluationScorecard


class TestRAGEvaluator:
    def test_mock_evaluator_evaluate_pair(self):
        evaluator = MockRAGEvaluator(faithfulness=0.95, relevancy=0.85)
        scorecard = asyncio.run(
            evaluator.evaluate_pair(
                query="QCVN 06:2022 la gi?",
                answer="QCVN 06:2022 la Quy chuẩn kỹ thuật quốc gia về an toàn cháy cho nhà và công trình.",
                context=["QCVN 06:2022/BXD Quy chuẩn kỹ thuật quốc gia về an toàn cháy..."],
            )
        )
        assert isinstance(scorecard, EvaluationScorecard)
        assert scorecard.faithfulness == 0.95
        assert scorecard.relevancy == 0.85
        assert scorecard.overall_score == 90.0
        assert len(evaluator.call_history) == 1

    def test_evaluator_with_mock_gateway(self):
        mock_gateway = AsyncMock()
        mock_gateway.extract_json = AsyncMock(
            return_value={
                "faithfulness": 0.9,
                "relevancy": 0.9,
                "faithfulness_reason": "Fully supported",
                "relevancy_reason": "Highly relevant",
                "suggestions": [],
            }
        )
        evaluator = RAGEvaluator(ai_gateway_client=mock_gateway)
        scorecard = asyncio.run(
            evaluator.evaluate_pair(
                query="QCVN query",
                answer="QCVN answer",
                context=["ctx line"],
            )
        )
        assert scorecard.faithfulness == 0.9
        assert scorecard.relevancy == 0.9
        assert scorecard.overall_score == 90.0
        assert mock_gateway.extract_json.call_count == 1
