# T-02: Refactor Cloud Vision & RAGRouter to consume AIGatewayClient

## Status
Open

## Blocking
Blocked by T-01

## Objective
Refactor `ingestion/cloud_vision.py` and `ingestion/rag_router.py` to delegate all LLM text, structured JSON, and Vision OCR completions to `AIGatewayClient`. Remove hand-rolled HTTP retry loops from `cloud_vision.py`.

## Verification
- `cloud_vision.py` and `rag_router.py` call `AIGatewayClient` methods.
- Existing tests pass cleanly without errors.
