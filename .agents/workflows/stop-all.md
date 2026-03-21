---
name: stop-all
command: /stop-all
description: Stop all vLLM model containers and the Docker Compose stack
type: workflow
category: custom
enabled: true
version: v3.0
---

// turbo-all

## Steps

1. Stop vLLM containers:
```bash
docker stop qwen35-vllm qwen35b 2>/dev/null; echo "✅ vLLM containers stopped"
```

2. Stop Docker Compose stack:
```bash
cd /home/vvc/Codebase/dgx-spark-toolkit && docker compose down 2>/dev/null || docker-compose down; echo "✅ Stack stopped"
```

3. Confirm:
```bash
echo "🛑 All services stopped. Restart with: /start-all"
```
