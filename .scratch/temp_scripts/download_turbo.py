import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
from huggingface_hub import snapshot_download

print("Downloading via HF Mirror...")
snapshot_download(
    repo_id="deepdml/faster-whisper-large-v3-turbo-ct2",
    cache_dir="/home/vvc/.cache/huggingface/hub",
    local_files_only=False
)
print("Done!")
