---
name: vLLM Manager
command: /vllm-manager
description: Utilities and guidelines for managing vLLM model serving, health monitoring, benchmarking, and troubleshooting on DGX Spark.
type: skill
category: custom
enabled: true
version: v3.0
---

# vLLM Manager

This skill provides agents with the knowledge and tools to manage **vLLM model serving** on the DGX Spark server (128GB LPDDR5x unified memory, GB10 Grace Blackwell Superchip).

| Model | Alias | Port | Container | VRAM | Status |
|-------|-------|------|-----------|------|--------|
| Qwen3.5 35B | `rag-core` | 8004 | `qwen35b` | ~55GB | ✅ MoE + FlashInfer |
| Qwen3.5 4B | `rag-light` | 8003 | `qwen3-4b` | ~8GB | ✅ Fast Fallback |

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
curl -s http://localhost:8003/v1/models | jq   # Light (4B)

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
# Qwen 3.5 35B-FP8 (Optimized for GB10 — 180+ tokens/s)
docker run -d --name qwen35b --gpus all --ipc host --shm-size 64gb -p 8004:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  -v /home/vvc/Codebase/dgx-spark-toolkit/scripts:/app/scripts \
  -e MODEL_ID=Qwen/Qwen3.5-35B-A3B-FP8 \
  -e SERVED_MODEL_NAME=rag-core \
  -e PORT=8000 \
  -e GPU_MEMORY_UTILIZATION=0.78 \
  hellohal2064/vllm-qwen3.5-gb10:latest \
  --max-model-len 32768 --enable-prefix-caching --enable-chunked-prefill \
  --speculative-model Qwen/Qwen3.5-35B-A3B-FP8 --num-speculative-tokens 3 \
  --enable-auto-tool-choice --tool-call-parser qwen3_coder --trust-remote-code
```
