---
description: Stop all vLLM model containers and the Docker Compose stack
---

// turbo-all

## Steps

1. Stop vLLM containers:
```bash
docker stop qwen35-vllm qwen122b 2>/dev/null; echo "✅ vLLM containers stopped"
```

2. Stop Docker Compose stack:
```bash
cd /home/vvc/Codebase/dgx-spark-toolkit && docker compose down 2>/dev/null || docker-compose down; echo "✅ Stack stopped"
```

3. Confirm:
```bash
echo "🛑 All services stopped. Restart with: /start-all"
```
