#!/bin/bash

# Configuration Switcher for vLLM-Light (Qwen-8B) on Blackwell
# Usage: ./switch-vllm.sh [prod|max]

MODE=$1
ENV_FILE=".env"

if [ "$MODE" == "prod" ]; then
    echo "Switching to PRODUCTION mode (24k context, optimized for speed)..."
    sed -i 's/VLLM_LIGHT_GPU_UTIL=.*/VLLM_LIGHT_GPU_UTIL=0.15/' $ENV_FILE
    sed -i 's/VLLM_LIGHT_MAX_LEN=.*/VLLM_LIGHT_MAX_LEN=24576/' $ENV_FILE
elif [ "$MODE" == "max" ]; then
    echo "Switching to EXTREME mode (32k context, higher VRAM)..."
    sed -i 's/VLLM_LIGHT_GPU_UTIL=.*/VLLM_LIGHT_GPU_UTIL=0.20/' $ENV_FILE
    sed -i 's/VLLM_LIGHT_MAX_LEN=.*/VLLM_LIGHT_MAX_LEN=32768/' $ENV_FILE
else
    echo "Usage: $0 [prod|max]"
    echo "  prod: 32k context, optimized for speed"
    echo "  max: 128k context, optimized for long docs"
    exit 1
fi

echo "Restarting vllm-4b service..."
docker compose up -d vllm-4b

echo "Switching complete. Monitor logs with: docker logs -f qwen3-4b"
