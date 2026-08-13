---
name: model-updater
description: Audits Google AI Studio & Proxy models, auto-patches litellm_config.yaml, and restarts AI Gateway. Use when models are deprecated or updated.
---

# Model Updater Skill for DGX Spark

This skill provides full automation for auditing live models from Google AI Studio Direct API and Centralized API Proxy (`100.83.192.30:8045`), patching `litellm_config.yaml` with updated model identifiers, and restarting `ai-gateway`.

## How to Trigger

Run the slash command:
`/ccba-update-models`

Or run the underlying Python script directly:
```bash
python3 /home/vvc/Codebase/dgx-spark-toolkit/scripts/model_auto_updater.py --force
```

## Key Responsibilities

1. **Query Live Models**: Fetches available models from Google API (`https://generativelanguage.googleapis.com/v1beta/models?key=...`).
2. **Auto-Patching**: Scans `services/ai-gateway/litellm_config.yaml` for deprecated model names and replaces them with active equivalents.
3. **Container Restart**: Restarts the `ai-gateway` container cleanly.
4. **Notifications**: Sends a summary report via Telegram if `TELEGRAM_BOT_TOKEN` is configured in `.env`.
