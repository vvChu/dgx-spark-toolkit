---
name: ccba-update-models
command: /ccba-update-models
description: Audit Google AI Studio & Proxy models, auto-patch litellm_config.yaml, and restart AI Gateway
type: workflow
category: custom
enabled: true
version: v1.0
---

Audit available models from Google AI Studio Direct API and Centralized API Proxy, automatically patch `litellm_config.yaml` for obsolete or new models, and restart `ai-gateway`.

1. Run the model auto-updater with `--force` flag:
// turbo
```bash
python3 /home/vvc/Codebase/dgx-spark-toolkit/scripts/model_auto_updater.py --force
```

2. Check `ai-gateway` container health status:
// turbo
```bash
docker ps -f name=ai-gateway
```

3. Verify `ai-gateway` endpoints responsiveness:
// turbo
```bash
curl -s -m 5 -X POST "http://localhost:8090/v1/chat/completions" \
  -H "Authorization: Bearer sk-spark-secure-key-2026" \
  -H "Content-Type: application/json" \
  -d '{"model": "ocr-primary", "messages": [{"role": "user", "content": "Health check"}]}' | jq -c '{model: .model, status: "OK"}'
```
