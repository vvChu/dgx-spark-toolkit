---
description: "Use when editing Docker Compose, Dockerfiles, Helm charts, or deployment configuration."
applyTo: "docker-compose.yml, **/Dockerfile, helm/**"
---
# Docker & Helm Conventions

## Docker Compose profiles
| Profile | Services | Usage |
|---|---|---|
| *(default)* | rag-service, ai-gateway, milvus, neo4j, postgres, redis, prometheus, grafana | `docker compose up` |
| `ingest` | rag-watcher (×1) | `docker compose --profile ingest up` |
| `vllm-light` | vllm-4b (9B AWQ) | `docker compose --profile vllm-light up` |
| `loadtest` | locust (:8089) | `docker compose --profile loadtest up` |

## Key volumes
- `model_cache:/app/models` — Hugging Face + Surya OCR cache. Set `HF_HOME=/app/models`
- `milvus_data`, `neo4j_data`, `postgres_data` — database persistence

## GPU reservations
- `vllm-35b`: 96GB memory limit, `gpu-memory-utilization=0.85`
- `vllm-4b`: 12GB memory limit, AWQ 4-bit quantization

## Network
All services on `rag-network` bridge. AI Gateway internal: `http://ai-gateway:4000/v1`

## Helm (`helm/dgx-spark-toolkit/`)
- Ingress: Nginx at `rag.dgxspark.local`
- HPA on rag-service (CPU-based autoscaling)
- Resource defaults: 4 CPU / 12GB memory
- Secrets in `templates/secrets.yaml` — never hardcode values in `values.yaml`
