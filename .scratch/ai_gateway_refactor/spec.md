# Technical Spec: AI Gateway Client Consolidation & Deepening

## 1. Overview & Goal

Consolidate the fragmented LLM/Vision invocation wrappers (`core/llm_client.py`, `ingestion/rag_router.py`, `ingestion/cloud_vision.py`) into a single, deep `AIGatewayClient` module at `services/rag-service/core/ai_gateway_client.py`.

## 2. Target Architecture

### Module Seam (`services/rag-service/core/ai_gateway_client.py`)

```python
class AIGatewayClient:
    def __init__(self, http_client: httpx.AsyncClient | None = None, settings: Settings | None = None):
        ...

    async def complete(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        extra_body: dict | None = None,
    ) -> str:
        """Async text completion with transparent fallback chain."""

    async def complete_json(
        self,
        messages: list[dict],
        *,
        schema: Type[BaseModel] | None = None,
        model: str | None = None,
    ) -> Any:
        """Async structured JSON completion with fence stripping & Pydantic validation."""

    async def complete_vision(
        self,
        image_bytes: bytes | str,
        prompt: str,
        *,
        model_chain: list[str] | None = None,
    ) -> str:
        """Async vision OCR completion with 429 backoff & fallback chain."""

    # Sync helper wrappers for non-async callers
    def complete_sync(self, messages: list[dict], **kwargs) -> str: ...
    def complete_json_sync(self, messages: list[dict], **kwargs) -> Any: ...
    def complete_vision_sync(self, image_bytes: bytes | str, prompt: str, **kwargs) -> str: ...
```

## 3. Tickets & Execution Plan

1. **`T-01`**: Create `AIGatewayClient` & `MockAIGatewayClient` in `core/ai_gateway_client.py` with fallback chains, markdown fence stripping, and Pydantic validation. Add `core/llm_client.py` backward-compatibility aliases.
2. **`T-02`**: Refactor `cloud_vision.py` and `rag_router.py` to delegate all LLM/Vision calls to `AIGatewayClient`.
3. **`T-03`**: Add comprehensive unit tests in `tests/test_ai_gateway_client.py` validating offline mocking, fallback chains, and schema validation.
