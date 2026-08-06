---
name: stop-rag
command: /stop-rag
description: Stop the RAG backend stack (keeps vLLM models running)
type: workflow
category: custom
enabled: true
version: v4.0
---

// turbo-all

## Steps

1. Stop RAG stack services (keeps vLLM models running):
```bash
cd /home/vvc/Codebase/dgx-spark-toolkit && docker compose stop \
  rag-service rag-watcher ai-gateway rag-frontend \
  milvus-standalone milvus-etcd milvus-minio \
  neo4j litellm-db litellm-redis \
  prometheus grafana \
  && echo "✅ RAG stack stopped (vLLM models still running)"
```
