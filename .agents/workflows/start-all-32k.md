---
name: start-all-32k
command: /start-all-32k
description: Production mode — Start everything (rag-core 35B + rag-light 4B + RAG stack)
type: workflow
category: custom
enabled: true
version: v4.0
---

// turbo-all

## Steps

1. Start vLLM models + full stack:
```bash
cd /home/vvc/Codebase/dgx-spark-toolkit && docker compose up -d
```

2. Show status:
```bash
echo "⏳ Waiting for services..."
sleep 10
docker compose -f /home/vvc/Codebase/dgx-spark-toolkit/docker-compose.yml ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
```

3. Prime AI Gateway fallbacks:
```bash
for model in "rag-core" "rag-light"; do
  curl -m 10 -s http://localhost:8090/v1/chat/completions \
    -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"model\": \"$model\", \"messages\": [{\"role\": \"user\", \"content\": \"ping\"}], \"max_tokens\": 5}" > /dev/null || true
done
echo "✅ All services started (Production mode)"
```
