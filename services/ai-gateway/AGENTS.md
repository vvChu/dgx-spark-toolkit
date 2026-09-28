# AI Gateway (services/ai-gateway)

LiteLLM proxy instance managing LLM routing, semantic caching, and quota management for DGX Spark services and federated spokes.

## Quick Commands
- **Check Config Syntax**: `python3 -c "import yaml; yaml.safe_load(open('services/ai-gateway/litellm_config.yaml'))"`
- **Health Check**: `curl -s http://localhost:8090/health/liveliness`
- **Models List**: `curl -s http://localhost:8090/v1/models`

## Architecture & Topology
- **Config & Routing**: [`litellm_config.yaml`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/ai-gateway/litellm_config.yaml) — Defines model groups, fallbacks, semantic caching (DB 0), and timeouts.
- **Custom Callbacks**: [`custom_callbacks.py`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/ai-gateway/custom_callbacks.py) — `KeyCooldownManager` (circuit breaker on 429) and `ParameterNormalizer`.
- **Docker Orchestration**: Exposed on external port `8090` (mapped to internal container port `4000`).

## Invariants & Routing Policy
- **3-Tier Topology**: Tier 1: Google AI Studio Free Pool (OCR/vision); Tier 2: Centralized API Proxy (Tailscale `100.83.192.30:8045`); Tier 3: Local GPU (`rag-core` on Blackwell GB10).
- **drop_params**: `litellm_settings.drop_params: true` must be enabled to prevent 400 UnsupportedParamsError from embedding SDKs.
- **Virtual Keys**: Issue spoke keys with fixed 30-day budget (`budget_duration="30d"`) and rate limits.
