---
description: Start all vLLM model containers and the Docker Compose stack (RAG + Gateway + Milvus + Monitoring)
---

// turbo-all

## Steps

1. Check and start Qwen 3.5 35B (port 8001):
```bash
if docker ps --format '{{.Names}}' | grep -q '^qwen35-vllm$'; then echo "✅ qwen35-vllm already running"; else docker rm -f qwen35-vllm 2>/dev/null || true && docker run -d --name qwen35-vllm --gpus all --ipc host --shm-size 64gb -p 8001:8000 -v ~/.cache/huggingface:/root/.cache/huggingface vllm/vllm-openai:cu130-nightly --model Qwen/Qwen3.5-35B-A3B --served-model-name qwen3.5-35b --max-model-len 131072 --gpu-memory-utilization 0.40 --reasoning-parser qwen3 --enable-auto-tool-choice --tool-call-parser qwen3_coder --enable-prefix-caching --kv-cache-dtype auto && echo "✅ qwen35-vllm started"; fi
```

2. Check and start Qwen 3.5 122B (port 8003):
```bash
if docker ps --format '{{.Names}}' | grep -q '^qwen122b$'; then echo "✅ qwen122b already running"; elif [ -d "/home/vvc/Codebase/dgx-spark-toolkit/qwen122b-fixed" ] && [ -f "/home/vvc/Codebase/dgx-spark-toolkit/qwen122b-fixed/config.json" ]; then docker rm -f qwen122b 2>/dev/null || true && docker run -d --name qwen122b --gpus all --ipc host --shm-size 128gb -p 8003:8000 -v /home/vvc/Codebase/dgx-spark-toolkit/qwen122b-fixed:/model vllm/vllm-openai:cu130-nightly --model /model --served-model-name qwen3.5-122b --max-model-len 262144 --gpu-memory-utilization 0.87 --quantization compressed-tensors --reasoning-parser qwen3 --enable-auto-tool-choice --tool-call-parser qwen3_coder --enable-prefix-caching --kv-cache-dtype auto && echo "✅ qwen122b started"; else echo "⚠️ 122B model directory not ready, skipping"; fi
```

3. Start Docker Compose stack (RAG + Gateway + Milvus + Monitoring):
```bash
cd /home/vvc/Codebase/dgx-spark-toolkit && docker compose up -d 2>/dev/null || docker-compose up -d
```

4. Show running services:
```bash
echo "🚀 Active endpoints:"; echo "  • Qwen 35B:  http://localhost:8001/v1"; echo "  • Qwen 122B: http://localhost:8003/v1"; echo "  • RAG:       http://localhost:8000"; echo "  • Gateway:   http://localhost:8090"; echo "  • Grafana:   http://localhost:3000"; docker ps --format "  {{.Names}}\t{{.Status}}\t{{.Ports}}" | head -10
```
