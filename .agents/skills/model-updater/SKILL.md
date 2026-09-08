---
name: model-updater
description: Audits Google AI Studio & Proxy models, auto-patches litellm_config.yaml, and restarts AI Gateway. Use when models are deprecated or updated.
---

# Model Updater Skill for DGX Spark

This skill provides full automation for auditing live models from Google AI Studio Direct API and Centralized API Proxy (`100.83.192.30:8045`), patching `litellm_config.yaml` with updated model identifiers, and restarting `ai-gateway`.

## How to Trigger

Run the slash command:
`/ccba-update-models`

Or run the underlying Python script directly with flags:
```bash
# 1. Audit only (inspect upstream differences without modifying files)
python3 /home/vvc/Codebase/dgx-spark-toolkit/scripts/model_auto_updater.py --audit

# 2. Dry-run (show patches that would be applied)
python3 /home/vvc/Codebase/dgx-spark-toolkit/scripts/model_auto_updater.py --dry-run

# 3. Force update & restart
python3 /home/vvc/Codebase/dgx-spark-toolkit/scripts/model_auto_updater.py --force
```

## Key Responsibilities

1. **Query Live Models**: Fetches available models from Google API (`https://generativelanguage.googleapis.com/v1beta/models?key=...`) and Centralized Proxy (`GATEWAY_PROXY_URL/models`).
2. **Auto-Patching**: Scans `services/ai-gateway/litellm_config.yaml` for deprecated model names (such as Gemma/Gemini variants) and replaces them with active equivalents.
3. **Container Restart & Verification**: Restarts the `ai-gateway` container cleanly and runs live HTTP endpoint health checks.
4. **Notifications**: Sends a summary report via Telegram if `TELEGRAM_BOT_TOKEN` is configured in `.env`.

## Domain Model Archetypes (Standard Roles)

| Archetype | Model Aliases | Target Backend |
| :--- | :--- | :--- |
| **OCR / Vision Ingestion** | `ocr-primary`, `ocr-fallback`, `ocr-tier4` | Google AI Studio Direct (10 keys) |
| **Standard / Coding** | `gemini-3.8-flash`, `gemini-3.7-flash` (medium / low), `text-gemma` | Google API + Centralized Proxy |
| **Deep Reasoning** | `claude-opus-4-6-thinking`, `gemini-3.8-flash-high`, `gemini-3.7-flash-high`, `claude-sonnet-4-6-thinking` | Google API + Proxy |
| **Local Private / Zero-Cost** | `rag-core`, `qwen-local-primary` | Local vLLM Qwen 35B FP8 |

### Proxy Provider Prefix Invariant
All models routed through `GATEWAY_PROXY_URL` (including Anthropic Claude models) **must** be defined with the `openai/` prefix (`model: openai/<model-id>`). Never use `anthropic/` with `GATEWAY_PROXY_URL`, as LiteLLM will append `/v1/messages` and cause HTTP 404 Not Found.

## Client Integration Guidelines

- **Timeout**: Set client HTTP timeout to **30s – 60s** (use **60s – 90s** for Claude Opus Thinking models).
- **Thinking Parameters**: Zero-config on client side — `custom_callbacks.gemini_corrector` normalizes thinking levels automatically.
- **Reference Doc**: Detailed guide available at [`services/ai-gateway/CLIENT_INTEGRATION_GUIDE.md`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/ai-gateway/CLIENT_INTEGRATION_GUIDE.md).
