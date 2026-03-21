# Shared Utilities

Shared helper modules used by multiple agent skills. Not a standalone skill.

## Files

- **`vllm_client.py`** — Unified vLLM/AI Gateway client for all skills. Routes through LiteLLM proxy for model access, fallbacks, and cloud support.
