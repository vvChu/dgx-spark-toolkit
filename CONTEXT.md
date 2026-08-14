# DGX Spark Vietnamese Legal RAG System

The core domain model, ubiquitous language, and canonical entity definitions for the Vietnamese Legal Document RAG System.

## Ingestion Domain

**DocumentIngestionPipeline**:
The single entry-point module orchestrating multi-stage legal document extraction, normalization, embedding, and indexing.
_Avoid_: Ingestor, ingestion script, pipeline runner

**IngestionState**:
The status lifecycle of a document within the processing queue and database (`PENDING`, `CLAIMED`, `PROCESSING`, `COMPLETED`, `FAILED`).
_Avoid_: Document status, job progress

**IngestionResult**:
The structured summary returned upon completion of document ingestion containing metrics, chunk counts, and execution duration.
_Avoid_: Ingestion response, pipeline output

**StateManager**:
The database adapter responsible for persisting and querying document `IngestionState` across processing workers.
_Avoid_: State tracker, queue state handler

**TextNormalizer**:
The text normalization engine responsible for legal OCR typo correction, header/footer stripping, structure formatting, and table recovery.
_Avoid_: Text cleaner, string sanitizer

**DocumentStore**:
The unified persistence module orchestrating vector indexing (Milvus), knowledge graph relationships (Neo4j), and state tracking.
_Avoid_: Database manager, storage layer

**DocumentReader**:
The unified multi-format document reader and extraction engine orchestrating native text parsing, PDF tier classification, OCR routing, and Office/image format conversion behind a single extraction interface.
_Avoid_: PDF reader, document converter, file extractor

**InMemoryDocumentReader**:
An in-memory test adapter for `DocumentReader` providing deterministic multi-page document extractions for hermetic offline testing.
_Avoid_: Mock reader, fake extractor

## AI Gateway & LLM Domain

**AIGatewayClient**:
The unified client interface providing standardized access, fallback chains, retry policies, and structured schema parsing via LiteLLM proxy.
_Avoid_: LLM client, proxy connector

**MockAIGatewayClient**:
An in-memory test adapter for `AIGatewayClient` providing deterministic LLM completions for offline testing.
_Avoid_: Fake LLM, dummy client

## Retrieval & Search Domain

**SearchPipeline**:
The search execution engine combining hybrid vector retrieval, knowledge graph traversal, multi-hop agentic reflection, and reranking behind a single query interface.
_Avoid_: Query engine, search executor

**SearchContext**:
The type-safe state container holding query parameters, candidate hits, reranked results, multi-hop plan traces, and execution telemetry across search stages.
_Avoid_: Query context, search state

**AgenticRetrieval**:
The iterative plan-retrieve-reflect loop within `SearchPipeline` that decomposes complex legal queries into sub-queries and evaluates contextual sufficiency across multiple hops.
_Avoid_: Agentic search loop, multi-step searcher

## Frontend Stream Domain

**StreamClient**:
The frontend client module managing Server-Sent Events (SSE) streaming connections with automatic reconnection and REST fallback.
_Avoid_: EventSource wrapper, stream handler

## Agent & Skill Infrastructure Domain

**SkillState**:
The status lifecycle of an agent skill within the system manifest (`installed`, `errored`, `repairing`, `disabled`).
_Avoid_: Skill status

**SkillRepairAssistant**:
The agent skill procedure responsible for diagnosing, patching, validating, and synchronizing agent skill sources.
_Avoid_: Skill fixer, skill debugger
