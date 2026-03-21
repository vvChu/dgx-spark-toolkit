---
name: rag-only
command: /rag-only
description: Start RAG backend services only (no LLM models)
type: workflow
category: custom
enabled: true
version: v3.0
---

// turbo-all

## Steps

1. Start support services:
```bash
cd /home/vvc/Codebase/dgx-spark-toolkit && docker compose up -d ai-gateway milvus-standalone neo4j-graph rag-service
```

2. Confirm status:
```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "ai-gateway|milvus|neo4j|rag-service"
```
