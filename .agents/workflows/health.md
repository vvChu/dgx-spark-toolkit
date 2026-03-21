---
name: health
command: /health
description: Check health status of all vLLM models, GPU memory, and Docker services
type: workflow
category: custom
enabled: true
version: v3.0
---

// turbo-all

## Steps

1. Check GPU memory:
```bash
nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv
```

2. Check vLLM container status:
```bash
docker ps -a --filter "name=qwen" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

3. Check Qwen Local APIs:
```bash
echo "--- rag-core (35B) ---"
curl -s http://localhost:8004/v1/models | jq || echo "❌ 35B not responding"
echo "--- rag-light (4B) ---"
curl -s http://localhost:8003/v1/models | jq || echo "❌ 4B not responding"
```

4. Check AI Gateway API (Unified):
```bash
curl -s http://localhost:8090/v1/models -H "Authorization: Bearer $LITELLM_MASTER_KEY" 2>/dev/null | python3 -m json.tool || echo "❌ Gateway not responding"
```

5. Check RAG Data Consistency:
```bash
docker exec -it rag-watcher python3 verify_quality.py
```

5. Check Docker Compose services:
```bash
cd /home/vvc/Codebase/dgx-spark-toolkit && docker compose ps 2>/dev/null || docker-compose ps
```
