---
name: vllm-32k
command: /vllm-32k
description: Start vLLM model containers only (35B + 4B), no RAG stack
type: workflow
category: custom
enabled: true
version: v4.0
---

// turbo-all

## Steps

1. Start model containers via compose:
```bash
cd /home/vvc/Codebase/dgx-spark-toolkit && docker compose up -d vllm-36b vllm-4b
```

2. Confirm status:
```bash
docker ps --filter name=qwen --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```
