---
name: vllm-32k
command: /vllm-32k
description: Start vLLM 9B model only with 32k context (640 tokens/s)
type: workflow
category: custom
enabled: true
version: v3.0
---

// turbo-all

## Steps

1. Configure 32k context and restart service:
```bash
cd /home/vvc/Codebase/dgx-spark-toolkit && ./switch-vllm.sh prod
```

2. Confirm status:
```bash
docker ps --filter name=vllm-9b
```
