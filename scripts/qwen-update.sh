#!/bin/bash
# scripts/qwen-update.sh
# Manually trigger a pull and restart for the Qwen model

LOG_FILE="/var/log/qwen-update.log"

echo "[$(date)] Checking for updates for hellohal2064/vllm-qwen3.5-gb10:latest..." | tee -a "$LOG_FILE"

# Pull latest image
docker pull hellohal2064/vllm-qwen3.5-gb10:latest | tee -a "$LOG_FILE"

# Restart container
echo "[$(date)] Restarting qwen35b container..." | tee -a "$LOG_FILE"
docker restart qwen35b | tee -a "$LOG_FILE"

echo "[$(date)] Update process completed." | tee -a "$LOG_FILE"
