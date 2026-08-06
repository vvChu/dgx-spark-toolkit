---
name: rag-only
command: /rag-only
description: Start RAG backend services only (no LLM models)
type: workflow
category: custom
enabled: true
version: v4.0
---

// turbo-all

## Steps

1. Start RAG backend (compose auto-pulls dependencies like etcd, minio, litellm-db, redis):
```bash
cd /home/vvc/Codebase/dgx-spark-toolkit && docker compose up -d \
  rag-service ai-gateway milvus-standalone neo4j rag-frontend
```

2. Confirm status:
```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "rag-service|ai-gateway|milvus|neo4j|litellm|rag-frontend"
```
