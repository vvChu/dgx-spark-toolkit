# T-01: Consolidate StateManager & Implement InMemory Adapter

## Status
Open

## Blocking
None

## Objective
Consolidate `PostgresStateManager` and `AsyncStateManager` into a single, clean async `StateManager` class in `services/rag-service/ingestion/state_manager.py`. Add `InMemoryStateManager` for offline unit testing. Delete `async_state_manager.py`.

## Verification
- Unit tests pass with `InMemoryStateManager`.
- Async DB operations connect and query properly.
