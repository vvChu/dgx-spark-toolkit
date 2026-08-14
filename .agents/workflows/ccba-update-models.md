---
name: ccba-update-models
command: /ccba-update-models
description: Audit Google AI Studio & Proxy models, auto-patch litellm_config.yaml, and restart AI Gateway
type: workflow
category: custom
enabled: true
version: v1.1
---

Audit available models from Google AI Studio Direct API and Centralized API Proxy, automatically patch `litellm_config.yaml` for obsolete or new models, and restart `ai-gateway`.

### Step 1: (Optional) Inspect live models without applying changes:
// turbo
```bash
python3 /home/vvc/Codebase/dgx-spark-toolkit/scripts/model_auto_updater.py --audit
```

### Step 2: Run the model auto-updater in force mode:
// turbo
```bash
python3 /home/vvc/Codebase/dgx-spark-toolkit/scripts/model_auto_updater.py --force
```

### Step 3: Check `ai-gateway` container health status:
// turbo
```bash
docker ps -f name=ai-gateway
```

### Step 4: Verify `ai-gateway` endpoints responsiveness:
// turbo
```bash
# Verify OCR Primary
curl -s -m 8 -X POST "http://localhost:8090/v1/chat/completions" \
  -H "Authorization: Bearer sk-spark-secure-key-2026" \
  -H "Content-Type: application/json" \
  -d '{"model": "ocr-primary", "messages": [{"role": "user", "content": "Health check"}]}' | jq -c '{model: .model, status: "OK"}'

# Verify Gemini 3.6 / 3.7 Tiered Models
curl -s -m 8 -X POST "http://localhost:8090/v1/chat/completions" \
  -H "Authorization: Bearer sk-spark-secure-key-2026" \
  -H "Content-Type: application/json" \
  -d '{"model": "gemini-3.6-flash-high", "messages": [{"role": "user", "content": "Health check"}]}' | jq -c '{model: .model, status: "OK"}'
```
