# Technical Spec: Retrieval Layer & Search Pipeline Refactoring

## 1. Overview & Goal

Consolidate the monolithic 291-line `_search_internal` method in `services/rag-service/services/retrieval_service.py` into a deep, modular `SearchPipeline` module at `services/rag-service/retrieval/search_pipeline.py`.

## 2. Architecture & Seams

### `SearchContext` Dataclass (`retrieval/search_pipeline.py`)

```python
@dataclass
class SearchContext:
    raw_query: str
    limit: int = 10
    use_reranker: bool = True
    doc_type: Optional[str] = None
    authority: Optional[str] = None
    year: Optional[int] = None
    doc_number: Optional[str] = None
    use_hyde: bool = False
    use_cache: bool = True
    session_id: Optional[str] = None
    tracer: Optional[QueryTracer] = None

    # Transient processing state
    intent: Optional[QueryIntent] = None
    search_query: Optional[str] = None
    query_vector: Optional[list] = None
    sparse_query: Optional[dict] = None
    raw_hits: Optional[list] = None
    results: list = field(default_factory=list)
```

### `SearchPipeline` Execution Stages

1. `_stage_intent_and_cache`: Zero-latency regex intent classification + Semantic cache check.
2. `_stage_rewrite_and_hyde`: Query rewriting & hypothetical document generation.
3. `_stage_hybrid_search`: Milvus hybrid dense/sparse vector search.
4. `_stage_rerank_and_score`: Cross-encoder re-ranking & validity status score weighting.
5. `_stage_graph_enrichment`: Neo4j document status verification, parent-child chunk expansion & Graph RAG timeline summary traversal.

## 3. Tickets & Execution Plan

1. **`T-01`**: Implement `SearchContext` and `SearchPipeline` in `services/rag-service/retrieval/search_pipeline.py`.
2. **`T-02`**: Simplify `services/rag-service/services/retrieval_service.py` to delegate `search()` directly to `SearchPipeline`.
3. **`T-03`**: Add comprehensive unit tests in `services/rag-service/tests/test_search_pipeline.py` and verify all 350 existing tests pass.
