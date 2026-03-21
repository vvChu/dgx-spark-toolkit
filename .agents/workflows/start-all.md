---
name: start-all
command: /start-all
description: Start all vLLM model containers and the Docker Compose stack (RAG + Gateway + Milvus + Monitoring)
type: workflow
category: custom
enabled: true
version: v3.0
---

// turbo-all

## Steps

1. Check and start Qwen models (Core & Light):
```bash
# Start Core (35B)
if docker ps --format '{{.Names}}' | grep -q '^qwen35b$'; then echo "✅ rag-core already running"; else docker rm -f qwen35b 2>/dev/null || true && docker run -d --name qwen35b --gpus all --ipc host --shm-size 96gb --restart unless-stopped -p 8004:8000 -v ~/.cache/huggingface:/root/.cache/huggingface -v /home/vvc/Codebase/dgx-spark-toolkit/scripts:/app/scripts -e MODEL_ID=Qwen/Qwen3.5-35B-A3B-FP8 -e SERVED_MODEL_NAME=qwen3.5-35b -e PORT=8000 -e GPU_MEMORY_UTILIZATION=0.78 hellohal2064/vllm-qwen3.5-gb10:latest --max-model-len 32768 --enable-prefix-caching --enable-chunked-prefill --speculative-model Qwen/Qwen3.5-35B-A3B-FP8 --num-speculative-tokens 3 --enable-auto-tool-choice --tool-call-parser qwen3_coder --trust-remote-code && echo "✅ rag-core started"; fi

# Start Light (4B) - Managed via docker-compose usually, but direct for speed:
if docker ps --format '{{.Names}}' | grep -q '^qwen3-4b$'; then echo "✅ rag-light already running"; else docker compose up -d vllm-4b && echo "✅ rag-light started"; fi
```

2. Start Docker Compose stack (RAG + Gateway + Milvus + Monitoring):
```bash
cd /home/vvc/Codebase/dgx-spark-toolkit && docker compose up -d 2>/dev/null || docker-compose up -d
```

3. Show running services:
```bash
echo "🚀 Active endpoints:"; echo "  • rag-core (35B):  http://localhost:8004/v1"; echo "  • rag-light (4B):  http://localhost:8003/v1"; echo "  • AI Gateway:   http://localhost:8090 (Aliases Active)"; bash scripts/rag-status.sh
```

4. Prime AI Gateway Fallbacks (Pre-flight Check):
```bash
echo "⏳ Priming AI Gateway fallbacks (checking primary models)..."
sleep 5
# Sending a fast ping to the main routing endpoints. If they fail (e.g. proxy 403), 
# LiteLLM will register the 'allowed_fails: 1' and put them on 'cooldown' immediately.
# Subsequent requests to these models will instantly route to the fallback without delay!
for model in "rag-core" "rag-light" "smartest-brain"; do
  echo "  - Pinging $model..."
  curl -m 10 -s http://localhost:8090/v1/chat/completions \
    -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"model\": \"$model\", \"messages\": [{\"role\": \"user\", \"content\": \"ping\"}], \"max_tokens\": 5}" > /dev/null || true
done
echo "✅ Fallback routing primed and cached for this session!"
```
