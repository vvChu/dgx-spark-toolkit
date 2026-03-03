---
name: vLLM Manager
description: Utilities and guidelines for managing vLLM model serving, health monitoring, benchmarking, and troubleshooting on DGX Spark.
---

# vLLM Manager

This skill provides agents with the knowledge and tools to manage **vLLM model serving** on the DGX Spark server (128GB LPDDR5x unified memory, GB10 Grace Blackwell Superchip).

## Active Models

| Model | Port | Container | Quantization | VRAM | Status |
|-------|------|-----------|-------------|------|--------|
| Qwen 3.5 35B-A3B | 8001 | `qwen35-vllm` | NVFP4 | ~20GB | ✅ Stable |
| Qwen 3.5 122B-A10B | 8003 | `qwen122b` | NVFP4 | ~70GB | ⚠️ Unstable (CUDA errors on cu130-nightly/GB10) |

> **Tip**: For most tasks, prefer routing through the **AI Gateway** (port 8090) which provides automatic fallback to cloud models (claude, gemini, gpt) if local vLLM is busy.

## AI Gateway (Recommended)

All skills and services should use the gateway instead of direct vLLM ports:

```bash
# Via Gateway — supports 25 models + cloud fallbacks
curl -X POST http://localhost:8090/v1/chat/completions \
  -H "Authorization: Bearer sk-spark-secure-key-2026" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3.5-35b","messages":[{"role":"user","content":"ping"}],"max_tokens":5}'
```

## Health Check

### Quick Status
```bash
# Check all vLLM containers
docker ps --filter "name=qwen" --format "{{.Names}}\t{{.Status}}\t{{.Ports}}"

# Check model readiness (direct)
curl -s http://localhost:8001/v1/models | python3 -m json.tool

# Check via AI Gateway (preferred)
curl -s http://localhost:8090/v1/models -H "Authorization: Bearer sk-spark-secure-key-2026"

# GPU VRAM utilization
nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv
```

### Metrics Endpoint
vLLM exposes Prometheus metrics at `/metrics`:
```bash
curl -s http://localhost:8001/metrics | head -30
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
docker logs qwen35-vllm --tail 50

# Restart the 35B container
docker restart qwen35-vllm
```

### Out of Memory
If VRAM is exhausted:
```bash
docker stop qwen122b   # Stop 122B first (uses ~70GB)
nvidia-smi             # Verify freed memory
```

### Model Not Responding
```bash
# Quick test via gateway (recommended)
curl -X POST http://localhost:8090/v1/chat/completions \
  -H "Authorization: Bearer sk-spark-secure-key-2026" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3.5-35b","messages":[{"role":"user","content":"ping"}],"max_tokens":5}'
```

## Benchmarking

```bash
python3 benchmark_qwen35b.py
```

## Container Launch Commands (Reference)

```bash
# Qwen 3.5 35B — use scripts/start-all.sh instead
docker run -d --name qwen35-vllm --gpus all --ipc host --shm-size 64gb -p 8001:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  vllm/vllm-openai:cu130-nightly \
  --model Qwen/Qwen3.5-35B-A3B --served-model-name qwen3.5-35b \
  --max-model-len 131072 --gpu-memory-utilization 0.40 \
  --reasoning-parser qwen3 --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder --enable-prefix-caching

# Qwen 3.5 122B — ⚠️ UNSTABLE. Use: ENABLE_122B=1 bash scripts/start-all.sh
# Known issues: CUDA errors on GB10/cu130-nightly
```
