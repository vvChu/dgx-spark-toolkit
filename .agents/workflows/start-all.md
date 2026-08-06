---
name: start-all
command: /start-all
description: Start all services — vLLM models (35B + 4B) + RAG stack + Monitoring
type: workflow
category: custom
enabled: true
version: v4.0
---

// turbo-all

## Steps

1. Start all Docker Compose services:
```bash
cd /home/vvc/Codebase/dgx-spark-toolkit && docker compose up -d
```

2. Wait for models to load, then show status:
```bash
echo "⏳ Waiting for services to start..."
sleep 10
echo "🚀 Service status:"
docker compose -f /home/vvc/Codebase/dgx-spark-toolkit/docker-compose.yml ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
```

3. Prime AI Gateway fallbacks:
```bash
echo "⏳ Priming AI Gateway fallbacks..."
for model in "rag-core" "rag-light"; do
  echo "  - Pinging $model..."
  curl -m 10 -s http://localhost:8090/v1/chat/completions \
    -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"model\": \"$model\", \"messages\": [{\"role\": \"user\", \"content\": \"ping\"}], \"max_tokens\": 5}" > /dev/null || true
done
echo "✅ Fallback routing primed!"
```
