---
name: stop-vllm
command: /stop-vllm
description: Stop all model containers (9B and 35B)
type: workflow
category: custom
enabled: true
version: v3.0
---

// turbo-all

## Steps

1. Stop model containers:
```bash
docker stop vllm-9b qwen35b 2>/dev/null && echo "✅ Model containers stopped"
```
