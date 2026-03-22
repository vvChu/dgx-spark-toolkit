#!/bin/bash
# DGX Spark Toolkit — Stop All Services
# Usage: bash scripts/stop-all.sh

set -e
echo "🛑 DGX Spark Toolkit — Stopping All Services"
echo "=============================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Stop vLLM containers
echo "📦 Stopping vLLM containers..."
docker stop qwen35b 2>/dev/null || true
echo "   ✅ vLLM containers stopped"

# Stop Docker Compose
echo "📦 Stopping Docker Compose stack..."
cd "$PROJECT_DIR"
docker compose down 2>/dev/null || docker-compose down
echo "   ✅ Stack stopped"

echo ""
echo "=============================================="
echo "✅ All services stopped."
echo "   To restart: bash scripts/start-all.sh"
echo "=============================================="
