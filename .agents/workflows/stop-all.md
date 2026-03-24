---
name: stop-all
command: /stop-all
description: Stop all vLLM model containers and the Docker Compose stack
type: workflow
category: custom
enabled: true
version: v4.0
---

// turbo-all

## Steps

1. Stop Docker Compose stack (includes models):
```bash
cd /home/vvc/Codebase/dgx-spark-toolkit && docker compose down; echo "✅ All services stopped"
```

2. Confirm:
```bash
echo "🛑 All services stopped. Restart with: /start-all"
```
