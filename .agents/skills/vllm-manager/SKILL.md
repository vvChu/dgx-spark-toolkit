---
name: vllm-manager
description: Utilities and guidelines for managing vLLM model serving, health monitoring, benchmarking, and troubleshooting on DGX Spark.
---

# vLLM Manager

This skill provides agents with the knowledge and tools to manage **vLLM model serving** on the DGX Spark server (128GB LPDDR5x unified memory, GB10 Grace Blackwell Superchip).

| Model | Alias | Port | Container | VRAM | Status |
|-------|-------|------|-----------|------|--------|
| Qwen3.5 35B | `rag-core` | 8004 | `qwen35b` | ~35GB (50G limit) | ✅ MoE + FlashInfer + Tool Calling |
| Qwen3.5 9B AWQ | `rag-light` | 8003 | `qwen3-9b` | ~10GB | ✅ Fast Fallback (AWQ 4-bit) |

> **Tip**: ALWAYS use functional aliases (**rag-core**, **rag-light**) instead of hardcoded model names in your code and requests.

## AI Gateway (Recommended)

All skills and services should use the gateway instead of direct vLLM ports:

```bash
# Via Gateway (Functional Aliases)
curl -X POST http://localhost:8090/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"rag-core","messages":[{"role":"user","content":"ping"}],"max_tokens":5}'
```

## Health Check

### Quick Status
```bash
# Check all vLLM containers
docker ps -a --filter "name=qwen" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Check model readiness (direct)
curl -s http://localhost:8004/v1/models | jq   # Core (35B)
curl -s http://localhost:8003/v1/models | jq   # Light (9B)

# Check via AI Gateway (Functional Aliases)
curl -s http://localhost:8090/v1/models -H "Authorization: Bearer $LITELLM_MASTER_KEY" | jq

# Diagnostic Script (Best way)
bash scripts/rag-status.sh
```

### Metrics Endpoint
vLLM exposes Prometheus metrics at `/metrics`:
```bash
curl -s http://localhost:8004/metrics | head -30
```

Key metrics:
- `vllm:num_requests_running` — Active inference requests
- `vllm:num_requests_waiting` — Queued requests
- `vllm:gpu_cache_usage_perc` — KV cache utilization (%)
- `vllm:avg_generation_throughput_toks_per_s` — Tokens/sec throughput

## Troubleshooting

### Container Crashed / Exited
```bash
# Check crash logs
docker logs qwen35b --tail 50

# Restart the 35B container
docker restart qwen35b
```

### Out of Memory
If VRAM is exhausted or fragmented:
```bash
docker restart qwen35b   # Restart 35B to clear cache
nvidia-smi               # Verify free memory
```

### Model Not Responding
```bash
# Quick test via gateway (recommended)
curl -X POST http://localhost:8090/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"rag-core","messages":[{"role":"user","content":"ping"}],"max_tokens":5}'
```

## Benchmarking

```bash
python3 benchmark_qwen35b.py
```

## Container Launch Commands (Reference)

```bash
# Qwen 3.5 35B (Optimized for GB10 — via docker-compose)
# Managed by docker-compose.yml service: vllm-35b
# Key params: gpu-memory-utilization=0.50, max-model-len=24576, kv-cache-dtype=fp8
docker compose up -d vllm-35b

# Direct run (reference only):
docker run -d --name qwen35b --gpus all -p 8004:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  -e SERVED_MODEL_NAME=rag-core \
  -e PORT=8000 \
  hellohal2064/vllm-qwen3.5-gb10:blackwell-sm121 \
  --model /models/model --served-model-name qwen3.5-35b \
  --gpu-memory-utilization 0.50 --max-model-len 24576 \
  --kv-cache-dtype fp8 --enable-prefix-caching --enable-chunked-prefill \
  --trust-remote-code
```
