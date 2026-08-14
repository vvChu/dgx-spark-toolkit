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
