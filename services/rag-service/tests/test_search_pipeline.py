"""Unit tests for SearchPipeline and SearchContext."""
import pytest
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
