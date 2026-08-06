# T-02: Simplify RetrievalService to delegate to SearchPipeline

## Status
Open

## Blocking
Blocked by T-01

## Objective
Refactor `services/rag-service/services/retrieval_service.py` so `RetrievalService.search()` acts as a clean Facade seam delegating execution to `SearchPipeline`.

## Verification
- Existing callers receive identical search responses.
