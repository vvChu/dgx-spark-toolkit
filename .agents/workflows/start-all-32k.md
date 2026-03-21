---
name: start-all-32k
command: /start-all-32k
description: Production mode - Start everything (rag-core + rag-light + RAG Service)
type: workflow
category: custom
enabled: true
version: v3.0
---

// turbo-all

## Steps

1. Start Qwen models:
```bash
docker compose up -d qwen35b vllm-fallback
```

2. Start RAG backend:
```bash
cd /home/vvc/Codebase/dgx-spark-toolkit && ./switch-vllm.sh prod && docker compose up -d
```

3. Prime AI Gateway fallbacks:
```bash
for model in "rag-core" "rag-light" "smartest-brain"; do
  curl -m 10 -s http://localhost:8090/v1/chat/completions \
    -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"model\": \"$model\", \"messages\": [{\"role\": \"user\", \"content\": \"ping\"}], \"max_tokens\": 5}" > /dev/null || true
done
```
