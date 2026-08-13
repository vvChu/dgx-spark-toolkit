# 0002: Centralized API Proxy Harmonization, Exponential Retry Backoff, and Image Routing

## Context & Decision

To improve AI Service availability, cost efficiency, and performance across all LLM-powered platform services, we audited connection benchmarks for the Centralized API Proxy (`100.83.192.30:8045` managing 7 accounts) and aligned the `ai-gateway` service configuration (`litellm_config.yaml`).

We decided to implement:

1. **Centralized Proxy Harmonization**: Standardize model route declarations (Anthropic Claude 4.6/4.5, Gemini 3.6/3.5 Flash, and GPT models) to funnel through `GATEWAY_PROXY_URL` (`http://100.83.192.30:8045`), maximizing prompt cache hits and sharing account rotation across all platform spokes.
2. **Exponential Retry Backoff & Resilience**: Add LiteLLM router resilience settings (`num_retries: 3`, `backoff_strategy: exponential`, `allowed_fails: 2`) to absorb short-lived upstream Rate Limits (HTTP 429) during peak parallel task execution.
3. **Dedicated Image Generation Routing**: Explicitly declare `mode: image_generation` for `gemini-3-pro-image` models to enforce OpenAI `/v1/images/generations` protocol, with dynamic fallback to direct Google AI Studio / Vertex AI credentials if proxy accounts lack Imagen quotas (HTTP 502/503).
4. **Primary & Backup Light Model Tiering**: Maintain `gemini-3.1-flash-lite` as the primary engine for OCR and lightweight extraction tasks, backed up by `gemini-3.5-flash-lite` for secondary redundancy.

## Status

Accepted

## Considered Options

- **Option A (Direct API Keys for All Providers)**: Route Gemini directly via local API Keys and Claude via Proxy. *Rejected due to fragmented key management, lack of centralized rate limit absorption, and higher quota burn.*
- **Option B (Immediate Cutover to Ultra-Low Latency Models)**: Replace all primary OCR models with `gemini-3.5-flash-low` (0.66s latency). *Rejected in favor of keeping proven `gemini-3.1-flash-lite` as primary with `gemini-3.5-flash-lite` backup to maintain production consistency.*
- **Option C (Forced Chat-Completions Image Routing)**: Route image generation requests through `/v1/chat/completions`. *Rejected due to protocol incompatibility returning HTTP 503 errors.*

## Consequences

- Significantly reduces rate-limiting errors (HTTP 429) under high worker concurrency.
- Ensures type-safe image generation routing via `/v1/images/generations`.
- Centralizes model access management and telemetry under `ai-gateway`.
