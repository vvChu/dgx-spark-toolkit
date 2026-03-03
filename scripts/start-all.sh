#!/bin/bash
# DGX Spark Toolkit — Start All Services
# Usage: bash scripts/start-all.sh
# This script starts all vLLM model containers and the Docker Compose stack.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🚀 DGX Spark Toolkit — Starting All Services"
echo "=============================================="

# --- 1. vLLM Qwen 3.5 35B ---
echo ""
echo "📦 [1/3] Qwen 3.5 35B (port 8001)..."
if docker ps --format '{{.Names}}' | grep -q '^qwen35-vllm$'; then
    echo "   ✅ Already running"
else
    echo "   Starting container..."
    docker rm -f qwen35-vllm 2>/dev/null || true
    docker run -d --name qwen35-vllm \
      --gpus all --ipc host --shm-size 64gb -p 8001:8000 \
      -v ~/.cache/huggingface:/root/.cache/huggingface \
      vllm/vllm-openai:cu130-nightly \
      --model Qwen/Qwen3.5-35B-A3B \
      --served-model-name qwen3.5-35b \
      --max-model-len 131072 \
      --gpu-memory-utilization 0.40 \
      --reasoning-parser qwen3 \
      --enable-auto-tool-choice \
      --tool-call-parser qwen3_coder \
      --enable-prefix-caching \
      --kv-cache-dtype auto
    echo "   ✅ Started"
fi

# --- 2. vLLM Qwen 3.5 122B (OPTIONAL — currently unstable) ---
echo ""
echo "📦 [2/3] Qwen 3.5 122B (port 8003)..."
if docker ps --format '{{.Names}}' | grep -q '^qwen122b$'; then
    echo "   ✅ Already running"
elif [ "${ENABLE_122B:-0}" != "1" ]; then
    echo "   ⚠️  SKIPPED — Qwen 122B is currently unstable on GB10/cu130-nightly (CUDA errors)."
    echo "   To force-start, run: ENABLE_122B=1 bash scripts/start-all.sh"
else
    MODEL_DIR="$PROJECT_DIR/qwen122b-fixed"
    if [ -d "$MODEL_DIR" ] && [ -f "$MODEL_DIR/config.json" ]; then
        echo "   ⚠️  Starting 122B (ENABLE_122B=1 set — may be unstable)..."
        docker rm -f qwen122b 2>/dev/null || true
        docker run -d --name qwen122b \
          --gpus all --ipc host --shm-size 128gb -p 8003:8000 \
          -v "$MODEL_DIR":/model \
          vllm/vllm-openai:cu130-nightly \
          --model /model \
          --served-model-name qwen3.5-122b \
          --max-model-len 32768 \
          --gpu-memory-utilization 0.82 \
          --quantization compressed-tensors \
          --enforce-eager \
          --enable-prefix-caching \
          --kv-cache-dtype auto
        echo "   ✅ Started (monitor with: docker logs -f qwen122b)"
    else
        echo "   ⚠️  Model directory not found: $MODEL_DIR"
    fi
fi

# --- 3. Docker Compose Stack ---
echo ""
echo "📦 [3/3] Docker Compose Stack (RAG + Gateway + Milvus + Monitoring)..."
cd "$PROJECT_DIR"
docker compose up -d 2>/dev/null || docker-compose up -d
echo "   ✅ Stack started"

# --- Summary ---
echo ""
echo "=============================================="
echo "✅ All services started!"
echo ""
echo "Endpoints:"
echo "  • Qwen 3.5 35B:  http://localhost:8001/v1"
echo "  • Qwen 3.5 122B: http://localhost:8003/v1"
echo "  • RAG Service:    http://localhost:8000"
echo "  • AI Gateway:     http://localhost:8090"
echo "  • Prometheus:     http://localhost:9090"
echo "  • Grafana:        http://localhost:3000"
echo ""
echo "Quick test:"
echo "  curl http://localhost:8001/v1/models"
echo "=============================================="
