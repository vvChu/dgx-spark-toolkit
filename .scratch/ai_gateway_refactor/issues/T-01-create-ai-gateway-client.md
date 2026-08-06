# T-01: Implement Deep AIGatewayClient & Mock Adapter

## Status
Open

## Blocking
None

## Objective
Implement `AIGatewayClient` and `MockAIGatewayClient` in `services/rag-service/core/ai_gateway_client.py`. Include fallback model chain, 429 rate limit backoff retry, automatic markdown fence stripping, and optional Pydantic schema validation. Provide backward compatibility wrappers in `core/llm_client.py`.

## Verification
- Unit tests pass with `MockAIGatewayClient`.
- Fallback chain switches models on simulated 429/500 errors.
