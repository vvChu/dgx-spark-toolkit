"""Unit tests for SearchPipeline and SearchContext."""
from unittest.mock import AsyncMock, MagicMock

from retrieval.search_pipeline import SearchPipeline, SearchContext


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


