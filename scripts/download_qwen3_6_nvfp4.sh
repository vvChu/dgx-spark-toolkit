#!/bin/bash
# scripts/download_qwen3_6_nvfp4.sh
# Download the NVFP4 quantized Qwen 3.6 model to the local cache directory

MODEL_ID="sakamakismile/Huihui-Qwen3.6-35B-A3B-abliterated-NVFP4"
TARGET_DIR="/home/vvc/.cache/huggingface/hub/models--sakamakismile--Huihui-Qwen3.6-35B-A3B-abliterated-NVFP4"

echo "[$(date)] Starting download of $MODEL_ID..."
mkdir -p "$TARGET_DIR"

# Require huggingface_hub to be installed
if ! command -v huggingface-cli &> /dev/null; then
    echo "huggingface-cli could not be found. Installing..."
    pip install -U "huggingface_hub[cli]"
fi

# Use symlinks=False to avoid symlink issues inside Docker later if directly mounted
huggingface-cli download $MODEL_ID --local-dir "$TARGET_DIR" --local-dir-use-symlinks False

echo "[$(date)] Download complete! Model saved to $TARGET_DIR"
