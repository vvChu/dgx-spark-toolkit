#!/bin/bash
# DGX Spark Toolkit — Start All Services
# Usage: bash scripts/start-all.sh
# This script starts all vLLM model containers and the Docker Compose stack.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🚀 DGX Spark Toolkit — Starting All Services"
echo "=============================================="

# --- 0. Create Docker Network (if needed) ---
echo ""
echo "📦 [0/2] Creating rag-network..."
docker network create rag-network 2>/dev/null || true
echo "   ✅ Network ready"

# --- 1. Docker Compose Stack ---
echo ""
echo "📦 [1/2] Docker Compose Stack (RAG + vLLM + Gateway + Milvus + Monitoring)..."
# Note: vLLM services (qwen35b, qwen3-9b) are now managed by docker-compose.yml
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
