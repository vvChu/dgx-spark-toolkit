#!/bin/bash
echo "=== HEALTH CHECK MỚI - Qwen3.5-9B AWQ + vLLM (Optimized) ==="
nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv
docker ps -a --filter "name=vllm-9b" --format "{{.Names}}\t{{.Status}}\t{{.Ports}}"
curl -s http://localhost:8004/v1/models | python3 -m json.tool || echo "❌ vLLM 35B not responding"
curl -s http://localhost:8090/v1/models -H "Authorization: Bearer sk-spark-secure-key-2026" | python3 -m json.tool || echo "❌ Gateway not responding"
docker exec -it rag-watcher python3 verify_quality.py
cd /home/vvc/Codebase/dgx-spark-toolkit && docker compose ps
