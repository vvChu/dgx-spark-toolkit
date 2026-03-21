---
name: start-all-128k
command: /start-all-128k
description: Extreme mode - Start everything (35B + RAG + 9B@128k)
type: workflow
category: custom
enabled: true
version: v3.0
---

// turbo-all

## Steps

1. Start Qwen 3.5 35B model:
```bash
if docker ps --format '{{.Names}}' | grep -q '^qwen35b$'; then echo "✅ qwen35b already running"; else docker rm -f qwen35b 2>/dev/null || true && docker run -d --name qwen35b --gpus all --ipc host --shm-size 96gb --restart unless-stopped -p 8004:8000 -v ~/.cache/huggingface:/root/.cache/huggingface -v /home/vvc/Codebase/dgx-spark-toolkit/scripts:/app/scripts -e MODEL_ID=Qwen/Qwen3.5-35B-A3B-FP8 -e SERVED_MODEL_NAME=qwen3.5-35b -e PORT=8000 -e GPU_MEMORY_UTILIZATION=0.78 hellohal2064/vllm-qwen3.5-gb10:latest --max-model-len 32768 --enable-prefix-caching --enable-chunked-prefill --speculative-model Qwen/Qwen3.5-35B-A3B-FP8 --num-speculative-tokens 3 --enable-auto-tool-choice --tool-call-parser qwen3_coder --trust-remote-code && echo "✅ qwen35b started"; fi
```

2. Start RAG backend and vLLM 9B in 128k mode:
```bash
cd /home/vvc/Codebase/dgx-spark-toolkit && ./switch-vllm.sh max && docker compose up -d
```

3. Prime AI Gateway fallbacks:
```bash
for model in "smartest-brain" "smart-brain" "qwen3.5-9b-rag"; do
  curl -m 10 -s http://localhost:8090/v1/chat/completions \
    -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"model\": \"$model\", \"messages\": [{\"role\": \"user\", \"content\": \"ping\"}], \"max_tokens\": 5}" > /dev/null || true
done
```
