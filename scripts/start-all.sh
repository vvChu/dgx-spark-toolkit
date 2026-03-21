#!/bin/bash
# DGX Spark Toolkit — Start All Services
# Usage: bash scripts/start-all.sh
# This script starts all vLLM model containers and the Docker Compose stack.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🚀 DGX Spark Toolkit — Starting All Services"
echo "=============================================="

# --- 1. vLLM Qwen 3.5 35B (FP8 Optimized) ---
echo ""
echo "📦 [1/3] Qwen 3.5 35B-FP8 (port 8004)..."
if docker ps --format '{{.Names}}' | grep -q '^qwen35b$'; then
    echo "   ✅ Already running"
else
    echo "   Starting container..."
    docker rm -f qwen35b 2>/dev/null || true
    docker run -d \
      --name qwen35b \
      --gpus all \
      --ipc host \
      --shm-size 96gb \
      --restart unless-stopped \
      -p 8004:8000 \
      -v /home/vvc/.cache/huggingface/hub/models--Qwen--Qwen3.5-35B-A3B-FP8:/models/model \
      -v "$PROJECT_DIR/scripts:/app/scripts" \
      -e PORT=8000 \
      -e GPU_MEMORY_UTIL=0.55 \
      --entrypoint python3 \
      hellohal2064/vllm-qwen3.5-gb10:latest \
      -m vllm.entrypoints.openai.api_server \
      --model /models/model/snapshots/0b2752837483aa34b3db6e83e151b150c0e00e49 \
      --served-model-name qwen3.5-35b \
      --gpu-memory-utilization 0.55 \
      --max-num-seqs 2048 \
      --max-model-len 32768 \
      --enable-prefix-caching \
      --enable-chunked-prefill \
      --trust-remote-code
    echo "   ✅ Started"
fi

# --- 2. Docker Compose Stack ---
echo ""
echo "📦 [2/2] Docker Compose Stack (RAG + Gateway + Milvus + Monitoring)..."
cd "$PROJECT_DIR"
docker compose up -d
echo "   ✅ Stack started"

# --- Summary ---
echo ""
echo "=============================================="
echo "✅ All services started!"
echo ""
echo "Endpoints:"
echo "  • Qwen 3.5 35B:  http://localhost:8004/v1"
echo "  • RAG Service:    http://localhost:8005"
echo "  • AI Gateway:     http://localhost:8090"
echo "  • Prometheus:     http://localhost:9090"
echo "  • Grafana:        http://localhost:3000"
echo ""
echo "Quick test:"
echo "  curl http://localhost:8004/v1/models"
echo "=============================================="
