#!/bin/bash
# scripts/qwen-update.sh
# Manually trigger a pull and restart for the Qwen model

LOG_FILE="/var/log/qwen-update.log"

echo "[$(date)] Checking for updates for vllm/vllm-openai:latest..." | tee -a "$LOG_FILE"

# Pull latest image
docker pull vllm/vllm-openai:latest | tee -a "$LOG_FILE"

# Restart container
echo "[$(date)] Restarting qwen36b container..." | tee -a "$LOG_FILE"
docker restart qwen36b | tee -a "$LOG_FILE"

echo "[$(date)] Update process completed." | tee -a "$LOG_FILE"
