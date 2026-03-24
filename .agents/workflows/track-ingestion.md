---
name: track-ingestion
command: /track-ingestion
description: Live tracking of RAG ingestion pipeline progress
type: workflow
category: custom
enabled: true
version: v4.0
---

Theo dõi tiến trình RAG Ingestion thời gian thực (Ctrl+C để thoát):

1. Show ingestion watcher logs (live):
```bash
docker compose -f /home/vvc/Codebase/dgx-spark-toolkit/docker-compose.yml logs -f --tail 100 rag-watcher
```
