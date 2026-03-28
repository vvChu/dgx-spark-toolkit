---
name: stop-vllm
command: /stop-vllm
description: Stop all vLLM model containers (35B and 9B)
type: workflow
category: custom
enabled: true
version: v4.0
---

// turbo-all

## Steps

1. Stop model containers:
```bash
cd /home/vvc/Codebase/dgx-spark-toolkit && docker compose stop vllm-35b vllm-4b && echo "✅ Model containers stopped (qwen35b, qwen3-9b)"
```
