---
name: stop-rag
command: /stop-rag
description: Stop the RAG backend stack
type: workflow
category: custom
enabled: true
version: v3.0
---

// turbo-all

## Steps

1. Stop Docker Compose services:
```bash
cd /home/vvc/Codebase/dgx-spark-toolkit && docker compose stop ai-gateway milvus-standalone neo4j-graph rag-service 2>/dev/null || true && echo "✅ RAG stack stopped"
```
