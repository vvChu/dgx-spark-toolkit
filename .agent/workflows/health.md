---
description: Check health status of all vLLM models, GPU memory, and Docker services
---

// turbo-all

## Steps

1. Check GPU memory:
```bash
nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv
```

2. Check vLLM container status:
```bash
docker ps -a --filter "ancestor=vllm/vllm-openai:cu130-nightly" --format "{{.Names}}\t{{.Status}}\t{{.Ports}}"
```

3. Check Qwen 35B API:
```bash
curl -s http://localhost:8001/v1/models 2>/dev/null | python3 -m json.tool || echo "❌ 35B not responding"
```

4. Check Qwen 122B API:
```bash
curl -s http://localhost:8003/v1/models 2>/dev/null | python3 -m json.tool || echo "❌ 122B not responding"
```

5. Check Docker Compose services:
```bash
cd /home/vvc/Codebase/dgx-spark-toolkit && docker compose ps 2>/dev/null || docker-compose ps
```
