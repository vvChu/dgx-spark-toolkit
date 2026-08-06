---
name: health
command: /health
description: Check health status of all vLLM models, GPU memory, and Docker services
type: workflow
category: custom
enabled: true
version: v4.0
---

// turbo-all

## Steps

1. Check GPU memory:
```bash
nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu --format=csv
```

2. Check vLLM container status:
```bash
docker ps -a --filter "name=qwen" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

3. Check Qwen Local APIs:
```bash
echo "--- rag-core (35B) ---"
curl -s http://localhost:8004/v1/models | jq '.data[].id' 2>/dev/null || echo "❌ 35B not responding"
echo "--- rag-light (4B) ---"
curl -s http://localhost:8003/v1/models | jq '.data[].id' 2>/dev/null || echo "❌ 4B not responding"
```

4. Check AI Gateway API:
```bash
curl -s http://localhost:8090/v1/models -H "Authorization: Bearer $LITELLM_MASTER_KEY" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); [print(f'  ✅ {m[\"id\"]}') for m in d['data']]" 2>/dev/null || echo "❌ Gateway not responding"
```

5. Check Docker Compose services:
```bash
cd /home/vvc/Codebase/dgx-spark-toolkit && docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
```
