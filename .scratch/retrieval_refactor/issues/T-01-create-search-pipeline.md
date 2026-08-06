# T-01: Implement Deep SearchPipeline & SearchContext

## Status
Open

## Blocking
None

## Objective
Implement `SearchContext` dataclass and `SearchPipeline` class in `services/rag-service/retrieval/search_pipeline.py`. Consolidate all 11 search steps behind clear private stage methods (`_stage_intent_and_cache`, `_stage_rewrite_and_hyde`, `_stage_hybrid_search`, `_stage_rerank_and_score`, `_stage_graph_enrichment`).

## Verification
- `SearchPipeline` instantiates cleanly with Milvus & Neo4j repos.
