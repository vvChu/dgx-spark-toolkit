---
name: vllm-128k
command: /vllm-128k
description: Start vLLM 9B model only with 128k context (120 tokens/s)
type: workflow
category: custom
enabled: true
version: v3.0
---

// turbo-all

## Steps

1. Configure 128k context and restart service:
```bash
cd /home/vvc/Codebase/dgx-spark-toolkit && ./switch-vllm.sh max
```

2. Confirm status:
```bash
docker ps --filter name=vllm-9b
```
