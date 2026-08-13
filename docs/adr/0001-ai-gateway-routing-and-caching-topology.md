# 0001: AI Gateway Routing, Fallback Topology, and Caching Strategy

## Context & Decision

During high-volume ingestion and legal document RAG retrieval, API rate limits (Cloud Gemini Free Tier) and GPU VRAM constraints (local Qwen 35B `rag-core` on DGX Spark) require a balance between latency, cost, and system safety.

We decided to implement:
1. **Hybrid Staircase GPU Offloading**: Route ~12-15% of OCR traffic to local `rag-core`, guarded by an instant fail-fast non-blocking mutex (`LOCAL_GPU_OCR_LOCK`). On lock contention, requests immediately spill over to Cloud Gemini burst capacity.
2. **Selective Reasoning Model Scoping**: Reserve reasoning models (`gemini-3.5-flash` with medium thinking level primary, `reasoning-gemma` fallback) strictly for HyDE generation, legal conflict analysis (`/analysis`), and query synthesis. Use lightweight non-reasoning models (`gemini-2.5-flash-lite`, `text-light-gemma`) for metadata extraction and structured chunking.
3. **Split Cache Policy**: Enforce **Exact Hash Matching** (`cache:ocr:<sha256>:<doc_id>:p<page_num>`) for OCR page extractions to prevent cache poisoning across document revisions, and **Semantic Caching (0.85 similarity)** for user search queries and HyDE expansion.
4. **Lazy Failover**: Maintain `background_health_checks: false` in LiteLLM config to prevent quota drain on 60+ endpoints, relying on `allowed_fails: 1` and `cooldown_time: 3600s` for dynamic endpoint failover.

## Status

Accepted

## Considered Options

- **Option A (Pure Cloud Primary)**: Exhaust cloud rate limits first before falling back to local GPU. *Rejected due to unnecessary rate-limit exhaustion during peak batch ingestion.*
- **Option B (Uniform Reasoning Scoping)**: Apply reasoning models across all stages including chunking and metadata. *Rejected due to excessive token latency and quota waste on simple extraction.*
- **Option C (Unified Semantic Caching)**: Use 0.85 semantic caching for both OCR page extraction and search queries. *Rejected due to potential OCR hallucination and cross-document page collisions.*

## Consequences

- Prevents GPU VRAM Out-Of-Memory (OOM) errors during parallel worker execution.
- Eliminates cache poisoning on re-scanned legal PDF documents.
- Protects Gemini free-tier daily rate limits while keeping average query latency low.
