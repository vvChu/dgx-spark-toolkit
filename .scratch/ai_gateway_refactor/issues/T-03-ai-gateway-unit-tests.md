# T-03: Add AIGatewayClient Seam Unit Tests

## Status
Open

## Blocking
Blocked by T-02

## Objective
Add a dedicated unit test suite in `services/rag-service/tests/test_ai_gateway_client.py` testing `AIGatewayClient` and `MockAIGatewayClient` through its public seam. Test fallback chains, Pydantic schema validation, and sync/async wrappers.

## Verification
- `uv run pytest tests/` passes 100%.
