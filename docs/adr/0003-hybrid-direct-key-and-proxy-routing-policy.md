# 0003: Hybrid Direct-Key & Centralized Proxy Dual-Engine Routing Policy

## Context & Decision

To maximize system throughput, protect cost budgets, and guarantee high-volume document ingestion (OCR & RAG pipelines), we surveyed the exact rate limits and capabilities of Google AI Studio Direct API Free Tier vs the Centralized API Proxy (`100.83.192.30:8045`).

We decided to implement:

1. **Dual-Engine Free OCR Cascade (7,000 pages/day)**:
   - Primary OCR (`ocr-primary`): Route through 10 Google AI Studio Direct Keys using `gemini-3.1-flash-lite` (500 RPD/key = 5,000 pages/day).
   - Secondary OCR (`ocr-fallback`): Route through 10 Google AI Studio Direct Keys using `gemini-3.5-flash-lite` (200 RPD/key = 2,000 pages/day).
   - Local GPU Safety Net (`rag-core`): Failover to DGX vLLM Qwen 35B when cloud quotas are exhausted.

2. **Gemma Free-Farm Offloading (144,000 req/day)**:
   - Enforce 100% offloading of non-vision NLP tasks (chunk metadata extraction, synthetic HyDE queries, document summarization) to `Gemma 3 27B` (`text-gemma`) and `Gemma 3 12B` (`text-gemma-12b` [alias `text-light-gemma`]) via Direct Keys, preserving Gemini quotas exclusively for Vision OCR.

3. **Hybrid Provider Routing Boundary**:
   - Direct Keys: Dedicated to high-volume, free-tier models (`gemini-3.1-flash-lite`, `gemini-3.5-flash-lite`, `gemma-3-27b`, `gemini-embedding-1`) where Redis tracks per-key RPD budgets.
   - Centralized Proxy: Dedicated to high-speed/reasoning/pro models (`gemini-3.5-flash-low`, `gemini-3.6-flash-high`, `claude-sonnet-4-6`, `claude-opus-4-6`, `gpt-4o`) via `GATEWAY_PROXY_URL` (`100.83.192.30:8045`).

4. **Redis RPD Budget Automation**:
   - Enforce explicit `model_budget_config` caps on Redis for `gemini-3.5-flash-lite` (`max_budget: 2000`, `budget_duration: 1d`) to trigger proactive, smooth failover before Google returns HTTP 429 rate limit errors.

## Status

Accepted

## Considered Options

- **Option A (All Models via Centralized Proxy)**: Route all Gemini Flash Lite and Gemma requests through the Proxy. *Rejected to prevent exhausting the Proxy's 7-account pool during batch document OCR.*
- **Option B (All Models via Direct Keys)**: Route all models via Direct Keys. *Rejected because Gemini Pro, Gemini 3.6 Flash, and Claude models require Pro/Advanced quota available only via Proxy.*

## Consequences

- Expands daily free cloud OCR capacity from 5,000 to 7,000 pages/day.
- Protects Gemini free-tier daily quotas from being consumed by non-vision text tasks.
- Eliminates HTTP 429 rate-limit crashes via proactive Redis budget monitoring.
