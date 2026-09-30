"""Unit tests for SearchPipeline and SearchContext."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.config import Settings, get_settings
from retrieval.query_classifier import QueryIntent
from retrieval.query_tracer import QueryTracer
from retrieval.search_pipeline import (
    RERANK_CANDIDATES,
    RERANK_LATENCY,
    SearchContext,
    SearchPipeline,
)


class TestSearchPipeline:
    def test_search_pipeline_execution_with_mocks(self):
        import asyncio
        milvus = MagicMock()
        milvus.hybrid_search = AsyncMock(return_value=[[]])
        milvus.get_parent_chunks = AsyncMock(return_value=[])

        neo4j = MagicMock()
        neo4j.driver = MagicMock()
        neo4j.find_document_status = AsyncMock(return_value={})

        pipeline = SearchPipeline(milvus, neo4j)
        ctx = SearchContext(raw_query="Quy định PCCC", limit=5, use_cache=False)

        res = asyncio.run(pipeline.execute(ctx))
        assert isinstance(res, dict)
        assert "results" in res
        assert "trace" in res
        assert "query_intent" in res
        assert milvus.hybrid_search.called

    def test_in_memory_search_pipeline(self):
        import asyncio
        from retrieval.search_pipeline import InMemorySearchPipeline

        pipeline = InMemorySearchPipeline()
        res = asyncio.run(pipeline.search("Quy chuẩn xây dựng", limit=3))
        assert isinstance(res, dict)
        assert len(res["results"]) == 1
        assert res["results"][0]["doc_number"] == "01/2024/TT-BXD"
        assert res["query_intent"] == "GENERAL"
        assert len(pipeline.call_history) == 1

    def test_in_memory_search_pipeline_agentic(self):
        import asyncio
        from retrieval.search_pipeline import InMemorySearchPipeline

        pipeline = InMemorySearchPipeline()
        res = asyncio.run(pipeline.search("So sánh quy chuẩn PCCC và tiêu chuẩn xây dựng", limit=3, use_agentic=True))
        assert isinstance(res, dict)
        assert res["query_intent"] == "COMPLEX"
        assert res["hops"] == 2
        assert len(res["sub_queries"]) == 2
        assert "Mock in-memory agentic plan" in res["reasoning"]

    def test_in_memory_search_pipeline_timeline(self):
        import asyncio
        from retrieval.search_pipeline import InMemorySearchPipeline

        pipeline = InMemorySearchPipeline()
        timeline = asyncio.run(pipeline.get_legal_timeline("01/2024/TT-BXD"))
        assert isinstance(timeline, list)
        assert len(timeline) >= 1
        assert timeline[0]["id"] == "01/2024/TT-BXD"

    def test_search_pipeline_sampler_hook(self):
        import asyncio
        milvus = MagicMock()
        milvus.hybrid_search = AsyncMock(return_value=[[]])
        milvus.get_parent_chunks = AsyncMock(return_value=[])

        neo4j = MagicMock()
        neo4j.driver = MagicMock()
        neo4j.find_document_status = AsyncMock(return_value={})

        mock_sampler = MagicMock()
        pipeline = SearchPipeline(milvus, neo4j, sampler_hook=mock_sampler)
        ctx = SearchContext(raw_query="Tra cứu tiêu chuẩn", session_id="test-session", use_cache=False)

        res = asyncio.run(pipeline.execute(ctx))
        assert isinstance(res, dict)
        mock_sampler.assert_called_once_with("Tra cứu tiêu chuẩn", res["results"], "test-session")

    def test_search_pipeline_sampler_hook_arbitrary_callable_and_error_handling(self):
        import asyncio
        milvus = MagicMock()
        milvus.hybrid_search = AsyncMock(return_value=[[]])
        milvus.get_parent_chunks = AsyncMock(return_value=[])

        neo4j = MagicMock()
        neo4j.driver = MagicMock()
        neo4j.find_document_status = AsyncMock(return_value={})

        recorded = []

        # Hook without parameter named session_id (e.g. 3-arg positional callback)
        def custom_hook(q, docs, sid):
            recorded.append((q, len(docs), sid))

        pipeline = SearchPipeline(milvus, neo4j, sampler_hook=custom_hook)
        ctx = SearchContext(raw_query="Tìm QCVN", session_id="sess-123", use_cache=False)
        res = asyncio.run(pipeline.execute(ctx))
        assert isinstance(res, dict)
        assert recorded == [("Tìm QCVN", 0, "sess-123")]

        # Hook that raises exception should not fail query
        def failing_hook(q, docs, sid):
            raise RuntimeError("Telemetry failure")

        pipeline_fail = SearchPipeline(milvus, neo4j, sampler_hook=failing_hook)
        res_fail = asyncio.run(pipeline_fail.execute(ctx))
        assert isinstance(res_fail, dict)

    def test_search_pipeline_results_with_doc_number_no_timeline_driver(self):
        """Regression test for P0: ensures SearchPipeline does not crash when results have doc_number but driver is None."""
        import asyncio
        from unittest.mock import patch

        mock_hit = MagicMock()
        mock_hit.entity = {
            "id": "c1",
            "text": "Quy định điều 5",
            "doc_number": "136/2020/ND-CP",
            "chunk_type": "parent",
        }
        mock_hit.distance = 0.95

        milvus = MagicMock()
        milvus.hybrid_search = AsyncMock(return_value=[[mock_hit]])
        milvus.get_parent_chunks = AsyncMock(return_value=[])

        neo4j = MagicMock()
        neo4j.driver = None
        neo4j._driver = None
        neo4j.find_document_status = AsyncMock(return_value={})

        mock_ai = MagicMock()
        mock_ai.complete = AsyncMock(return_value="Query rewritten")
        mock_ai.embed_query = AsyncMock(return_value=[0.1] * 1024)
        mock_ai.embed_sparse = AsyncMock(return_value={"1": 0.5})

        pipeline = SearchPipeline(milvus, neo4j, ai_client=mock_ai)
        assert pipeline.graph_timeline is None
        ctx = SearchContext(raw_query="PCCC", limit=2, use_cache=False, ai_client=mock_ai)

        with patch("retrieval.search_pipeline.get_reranker") as mock_get_reranker:
            mock_reranker = MagicMock()
            mock_reranker.rerank = AsyncMock(return_value=[("Quy định điều 5", 0.95)])
            mock_get_reranker.return_value = mock_reranker

            res = asyncio.run(pipeline.execute(ctx))
            assert isinstance(res, dict)
            assert len(res["results"]) == 1
            assert res["results"][0]["doc_number"] == "136/2020/ND-CP"

    def test_search_pipeline_results_with_doc_number_timeline_enrichment(self):
        """Tests that when timeline is available, it enriches results properly."""
        import asyncio
        from unittest.mock import patch

        mock_hit = MagicMock()
        mock_hit.entity = {
            "id": "c1",
            "text": "Nội dung gốc",
            "doc_number": "136/2020/ND-CP",
            "chunk_type": "parent",
        }
        mock_hit.distance = 0.95

        milvus = MagicMock()
        milvus.hybrid_search = AsyncMock(return_value=[[mock_hit]])
        milvus.get_parent_chunks = AsyncMock(return_value=[])

        neo4j = MagicMock()
        neo4j.driver = MagicMock()
        neo4j.find_document_status = AsyncMock(return_value={})

        mock_ai = MagicMock()
        mock_ai.complete = AsyncMock(return_value="Query rewritten")
        mock_ai.embed_query = AsyncMock(return_value=[0.1] * 1024)
        mock_ai.embed_sparse = AsyncMock(return_value={"1": 0.5})

        pipeline = SearchPipeline(milvus, neo4j, ai_client=mock_ai)
        pipeline.graph_timeline = MagicMock()
        pipeline.graph_timeline.get_legal_timeline = AsyncMock(return_value=[
            {"id": "136/2020/ND-CP", "status": "ACTIVE"},
            {"id": "50/2024/ND-CP", "status": "ACTIVE"},
        ])
        pipeline.graph_timeline.generate_timeline_summary = AsyncMock(return_value="NĐ 50 sửa đổi NĐ 136")

        ctx = SearchContext(raw_query="PCCC", limit=2, use_cache=False, ai_client=mock_ai)

        with patch("retrieval.search_pipeline.get_reranker") as mock_get_reranker:
            mock_reranker = MagicMock()
            mock_reranker.rerank = AsyncMock(return_value=[("Nội dung gốc", 0.95)])
            mock_get_reranker.return_value = mock_reranker

            res = asyncio.run(pipeline.execute(ctx))
            assert isinstance(res, dict)
            assert len(res["results"]) == 1
            assert res["results"][0]["legal_timeline_summary"] == "NĐ 50 sửa đổi NĐ 136"
            assert "[LEGAL TIMELINE]" in res["results"][0]["text"]

    def test_search_pipeline_timeline_exception_fallback(self):
        """Tests that when graph timeline retrieval raises an exception, search still succeeds gracefully."""
        import asyncio
        from unittest.mock import patch

        mock_hit = MagicMock()
        mock_hit.entity = {
            "id": "c1",
            "text": "Nội dung gốc",
            "doc_number": "136/2020/ND-CP",
            "chunk_type": "parent",
        }
        mock_hit.distance = 0.95

        milvus = MagicMock()
        milvus.hybrid_search = AsyncMock(return_value=[[mock_hit]])
        milvus.get_parent_chunks = AsyncMock(return_value=[])

        neo4j = MagicMock()
        neo4j.driver = MagicMock()
        neo4j.find_document_status = AsyncMock(return_value={})

        mock_ai = MagicMock()
        mock_ai.complete = AsyncMock(return_value="Query rewritten")
        mock_ai.embed_query = AsyncMock(return_value=[0.1] * 1024)
        mock_ai.embed_sparse = AsyncMock(return_value={"1": 0.5})

        pipeline = SearchPipeline(milvus, neo4j, ai_client=mock_ai)
        pipeline.graph_timeline = MagicMock()
        pipeline.graph_timeline.get_legal_timeline = AsyncMock(side_effect=RuntimeError("Neo4j down"))

        ctx = SearchContext(raw_query="PCCC", limit=2, use_cache=False, ai_client=mock_ai)

        with patch("retrieval.search_pipeline.get_reranker") as mock_get_reranker:
            mock_reranker = MagicMock()
            mock_reranker.rerank = AsyncMock(return_value=[("Nội dung gốc", 0.95)])
            mock_get_reranker.return_value = mock_reranker

            res = asyncio.run(pipeline.execute(ctx))
            assert isinstance(res, dict)
            assert len(res["results"]) == 1
            assert res["results"][0]["text"] == "Nội dung gốc"


def _histogram_count(metric) -> float:
    total = 0.0
    for family in metric.collect():
        for sample in family.samples:
            if sample.name.endswith("_count"):
                total += sample.value
    return total


def _hit(
    text: str,
    *,
    chunk_id: str,
    doc_number: str,
    hop: int = 1,
    score: float = 0.5,
    page: int = 1,
    validity: str = "ACTIVE",
    is_table: bool = False,
) -> dict:
    return {
        "score": score,
        "hop": hop,
        "entity": {
            "text": text,
            "chunk_id": chunk_id,
            "doc_number": doc_number,
            "page": page,
            "chunk_type": "parent",
            "validity_status": validity,
            "is_table": is_table,
            "source": f"{doc_number}.pdf",
        },
    }


def _pipeline_with_ai():
    milvus = MagicMock()
    milvus.hybrid_search = AsyncMock(return_value=[[]])
    milvus.get_parent_chunks = AsyncMock(return_value=[])
    neo4j = MagicMock()
    neo4j.driver = None
    neo4j._driver = None
    neo4j.find_document_status = AsyncMock(return_value={})
    ai = MagicMock()
    ai.complete_json = AsyncMock(return_value={"top_indices": [1]})
    ai.extract_json = AsyncMock(return_value={})
    pipeline = SearchPipeline(milvus, neo4j, ai_client=ai)
    return pipeline, ai


def _ctx(hits, *, limit: int = 10, intent: QueryIntent = QueryIntent.SEMANTIC, ai=None) -> SearchContext:
    ctx = SearchContext(
        raw_query="Quy định phòng cháy",
        limit=limit,
        use_reranker=True,
        use_cache=False,
        raw_hits=hits,
        intent=intent,
        ai_client=ai,
    )
    ctx.tracer = QueryTracer(ctx.raw_query)
    return ctx


class TestStageRerankAndScore:
    """Border cases for direct bge-reranker scoring without the LLM stage."""

    def test_rerank_empty_hits(self):
        pipeline, ai = _pipeline_with_ai()
        before_candidates = _histogram_count(RERANK_CANDIDATES)
        with patch("retrieval.search_pipeline.get_reranker") as mock_get:
            mock_reranker = MagicMock()
            mock_reranker.rerank = AsyncMock(return_value=[])
            mock_get.return_value = mock_reranker

            for raw_hits in ([], None):
                ctx = _ctx(raw_hits, ai=ai)
                asyncio.run(pipeline._stage_rerank_and_score(ctx))
                assert ctx.top_results == []

            mock_reranker.rerank.assert_not_called()
        ai.complete_json.assert_not_called()
        assert _histogram_count(RERANK_CANDIDATES) == before_candidates

    def test_rerank_single_hit(self):
        pipeline, ai = _pipeline_with_ai()
        hit = _hit("Điều 5.", chunk_id="doc::p1::art_5", doc_number="01/2024/TT-BXD", score=0.5, page=3)
        ctx = _ctx([hit], ai=ai)
        before_latency = _histogram_count(RERANK_LATENCY)

        async def _rerank(query, docs, top_k=5):
            assert query == ctx.raw_query
            assert docs == ["Điều 5."]
            assert top_k == 1
            return [("Điều 5.", 0.95, 0)]

        with patch("retrieval.search_pipeline.get_reranker") as mock_get:
            mock_reranker = MagicMock()
            mock_reranker.rerank = AsyncMock(side_effect=_rerank)
            mock_get.return_value = mock_reranker
            asyncio.run(pipeline._stage_rerank_and_score(ctx))

        assert len(ctx.top_results) == 1
        assert ctx.top_results[0]["doc_number"] == "01/2024/TT-BXD"
        assert ctx.top_results[0]["page"] == 3
        assert ctx.top_results[0]["text"] == "Điều 5."
        settings = get_settings()
        expected = (
            (0.95 * settings.RERANK_WEIGHT)
            + (0.5 * settings.MILVUS_WEIGHT)
            + settings.VALIDITY_BOOST_ACTIVE
        )
        assert ctx.top_results[0]["score"] == pytest.approx(expected)
        rerank_steps = [step for step in ctx.tracer.steps if step.get("action") == "rerank"]
        assert rerank_steps[-1]["input_count"] == 1
        assert rerank_steps[-1]["output_count"] == 1
        assert _histogram_count(RERANK_LATENCY) == before_latency + 1

    def test_rerank_safety_cap_60(self):
        assert Settings.model_fields["RERANK_MAX_CANDIDATES"].default == 60
        pipeline, ai = _pipeline_with_ai()
        texts = [f"chunk-text-{i}" for i in range(65)]
        hits = [
            _hit(text, chunk_id=f"chunk-{i}", doc_number=f"{i}/2024/TT-BXD", score=1.0 - (i / 1000))
            for i, text in enumerate(texts)
        ]
        ctx = _ctx(hits, ai=ai, intent=QueryIntent.SEMANTIC)
        captured = {}

        async def _rerank(query, docs, top_k=5):
            captured["docs"] = list(docs)
            captured["top_k"] = top_k
            return [(doc, 0.5, i) for i, doc in enumerate(docs)]

        with patch("retrieval.search_pipeline.get_reranker") as mock_get:
            mock_reranker = MagicMock()
            mock_reranker.rerank = AsyncMock(side_effect=_rerank)
            mock_get.return_value = mock_reranker
            asyncio.run(pipeline._stage_rerank_and_score(ctx))

        assert captured["docs"] == texts[:60]
        assert captured["top_k"] == 60
        for dropped in texts[60:]:
            assert dropped not in captured["docs"]
        assert len(ctx.top_results) == ctx.limit

    def test_rerank_exact_intent_uses_narrow_cap(self):
        assert Settings.model_fields["RERANK_EXACT_CANDIDATES"].default == 20
        pipeline, ai = _pipeline_with_ai()
        texts = [f"exact-text-{i}" for i in range(25)]
        hits = [_hit(text, chunk_id=f"exact-{i}", doc_number=f"{i}/2024/NĐ-CP") for i, text in enumerate(texts)]
        ctx = _ctx(hits, ai=ai, intent=QueryIntent.EXACT)
        captured = {}

        async def _rerank(query, docs, top_k=5):
            captured["docs"] = list(docs)
            return [(doc, 0.4, i) for i, doc in enumerate(docs)]

        with patch("retrieval.search_pipeline.get_reranker") as mock_get:
            mock_reranker = MagicMock()
            mock_reranker.rerank = AsyncMock(side_effect=_rerank)
            mock_get.return_value = mock_reranker
            asyncio.run(pipeline._stage_rerank_and_score(ctx))

        assert captured["docs"] == texts[:20]
        assert texts[20] not in captured["docs"]

    def test_rerank_duplicate_text_different_metadata(self):
        pipeline, ai = _pipeline_with_ai()
        shared = "Điều 12. Chiều cao công trình tối đa là 50 mét."
        hits = [
            _hit(shared, chunk_id="law-a::p1::art_12", doc_number="01/2024/TT-BXD", page=1, score=0.4),
            _hit(shared, chunk_id="law-b::p4::art_12", doc_number="02/2024/TT-BXD", page=4, score=0.4),
        ]
        ctx = _ctx(hits, ai=ai)

        async def _rerank(query, docs, top_k=5):
            assert docs == [shared, shared]
            return [(docs[1], 0.9, 1), (docs[0], 0.2, 0)]

        with patch("retrieval.search_pipeline.get_reranker") as mock_get:
            mock_reranker = MagicMock()
            mock_reranker.rerank = AsyncMock(side_effect=_rerank)
            mock_get.return_value = mock_reranker
            asyncio.run(pipeline._stage_rerank_and_score(ctx))

        assert [row["doc_number"] for row in ctx.top_results] == ["02/2024/TT-BXD", "01/2024/TT-BXD"]
        assert [row["page"] for row in ctx.top_results] == [4, 1]
        assert ctx.top_results[0]["text"] == shared
        assert ctx.top_results[1]["text"] == shared

    def test_rerank_dedup_same_chunk_id(self):
        pipeline, ai = _pipeline_with_ai()
        hits = [
            _hit("alpha", chunk_id="dup", doc_number="01/2024/TT-BXD"),
            _hit("beta", chunk_id="dup", doc_number="02/2024/TT-BXD"),
            _hit("gamma", chunk_id="other", doc_number="03/2024/TT-BXD"),
        ]
        ctx = _ctx(hits, ai=ai)
        captured = {}

        async def _rerank(query, docs, top_k=5):
            captured["docs"] = list(docs)
            return [(doc, 0.5, i) for i, doc in enumerate(docs)]

        with patch("retrieval.search_pipeline.get_reranker") as mock_get:
            mock_reranker = MagicMock()
            mock_reranker.rerank = AsyncMock(side_effect=_rerank)
            mock_get.return_value = mock_reranker
            asyncio.run(pipeline._stage_rerank_and_score(ctx))

        assert captured["docs"] == ["alpha", "gamma"]
        assert [row["doc_number"] for row in ctx.top_results] == ["01/2024/TT-BXD", "03/2024/TT-BXD"]

    def test_rerank_preserves_agentic_hop2(self):
        assert Settings.model_fields["RERANK_AGENTIC_HOP2_MIN_QUOTA"].default == 20
        pipeline, ai = _pipeline_with_ai()
        hop1 = [
            _hit(f"hop1-{i}", chunk_id=f"h1-{i}", doc_number=f"H1-{i}", hop=1, score=0.9)
            for i in range(50)
        ]
        hop2 = [
            _hit(f"hop2-{i}", chunk_id=f"h2-{i}", doc_number=f"H2-{i}", hop=2, score=0.2)
            for i in range(15)
        ]
        ctx = _ctx(hop1 + hop2, ai=ai, intent=QueryIntent.COMPLEX)
        captured = {}

        async def _rerank(query, docs, top_k=5):
            captured["docs"] = list(docs)
            return [(doc, 0.3, i) for i, doc in enumerate(docs)]

        with patch("retrieval.search_pipeline.get_reranker") as mock_get:
            mock_reranker = MagicMock()
            mock_reranker.rerank = AsyncMock(side_effect=_rerank)
            mock_get.return_value = mock_reranker
            asyncio.run(pipeline._stage_rerank_and_score(ctx))

        docs = captured["docs"]
        assert len(docs) == 60
        assert sum(text.startswith("hop2-") for text in docs) == 15
        assert sum(text.startswith("hop1-") for text in docs) == 45
        for i in range(15):
            assert f"hop2-{i}" in docs
        for i in range(45, 50):
            assert f"hop1-{i}" not in docs

    def test_rerank_does_not_call_complete_json(self):
        import retrieval.search_pipeline as search_pipeline_module

        assert not hasattr(search_pipeline_module, "stage1_fast_batch_rerank")
        pipeline, ai = _pipeline_with_ai()
        hits = [
            _hit(f"bulk-{i}", chunk_id=f"bulk-{i}", doc_number=f"B-{i}")
            for i in range(65)
        ]
        ctx = _ctx(hits, ai=ai)

        async def _rerank(query, docs, top_k=5):
            return [(doc, 0.2, i) for i, doc in enumerate(docs[:top_k])]

        with patch("retrieval.search_pipeline.get_reranker") as mock_get:
            mock_reranker = MagicMock()
            mock_reranker.rerank = AsyncMock(side_effect=_rerank)
            mock_get.return_value = mock_reranker
            asyncio.run(pipeline._stage_rerank_and_score(ctx))

        ai.complete_json.assert_not_called()
        ai.complete_json.assert_not_awaited()

    def test_rerank_fallback_scores_keep_candidate_order(self):
        pipeline, ai = _pipeline_with_ai()
        hits = [
            _hit("first", chunk_id="a", doc_number="A", score=0.1),
            _hit("second", chunk_id="b", doc_number="B", score=0.2),
            _hit("third", chunk_id="c", doc_number="C", score=0.9),
        ]
        ctx = _ctx(hits, ai=ai)

        async def _rerank(query, docs, top_k=5):
            return [(doc, 0.0, i) for i, doc in enumerate(docs)]

        with patch("retrieval.search_pipeline.get_reranker") as mock_get:
            mock_reranker = MagicMock()
            mock_reranker.rerank = AsyncMock(side_effect=_rerank)
            mock_get.return_value = mock_reranker
            asyncio.run(pipeline._stage_rerank_and_score(ctx))

        assert [row["doc_number"] for row in ctx.top_results] == ["A", "B", "C"]
        rerank_steps = [step for step in ctx.tracer.steps if step.get("action") == "rerank"]
        assert rerank_steps[-1]["fallback"] is True

    def test_rerank_exception_keeps_candidate_order(self):
        pipeline, ai = _pipeline_with_ai()
        hits = [
            _hit("first", chunk_id="a", doc_number="A", score=0.1),
            _hit("second", chunk_id="b", doc_number="B", score=0.2),
            _hit("third", chunk_id="c", doc_number="C", score=0.9),
        ]
        ctx = _ctx(hits, ai=ai)

        with patch("retrieval.search_pipeline.get_reranker") as mock_get:
            mock_reranker = MagicMock()
            mock_reranker.rerank = AsyncMock(side_effect=RuntimeError("CUDA out of memory"))
            mock_get.return_value = mock_reranker
            asyncio.run(pipeline._stage_rerank_and_score(ctx))

        assert [row["doc_number"] for row in ctx.top_results] == ["A", "B", "C"]

    def test_prepare_intent_and_filters_chunk_type_exclusion(self):
        milvus = MagicMock()
        neo4j = MagicMock()
        pipeline = SearchPipeline(milvus, neo4j)

        # Standard technical query
        ctx = SearchContext(raw_query="khoảng cách an toàn PCCC cho nhà cao tầng", use_cache=False)
        pipeline._prepare_intent_and_filters(ctx)
        assert ctx.filter_expr is not None
        assert 'chunk_type not in ["amendment", "diff_matrix", "superseded", "instrument"]' in ctx.filter_expr
        assert ctx.cache_filter_key == ctx.filter_expr

    def test_prepare_intent_and_filters_comparison_query(self):
        milvus = MagicMock()
        neo4j = MagicMock()
        pipeline = SearchPipeline(milvus, neo4j)

        # Comparison query should NOT exclude amendments / diff matrices
        ctx = SearchContext(raw_query="So sánh thay đổi giữa QCVN 06:2022 và Sửa đổi 1:2023", use_cache=False)
        pipeline._prepare_intent_and_filters(ctx)
        # Exclusion filter should not be present
        if ctx.filter_expr:
            assert 'chunk_type not in' not in ctx.filter_expr


