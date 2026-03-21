import os
import re
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Golden State Configuration ---
GOLDEN_CONFIG = {
    "VLLM_PORT": "8004",
    "GATEWAY_PORT": "8090",
    "MODEL_NAME": "rag-core",
    "GPU_UTIL": "0.50",
    "CONCURRENCY": "4",
    "TIMEOUT": "300"
}

WORKFLOW_DIR = "/home/vvc/Codebase/dgx-spark-toolkit/.agents/workflows/"

# Patterns to find and replace
MAPS = [
    (r"8001|8002", GOLDEN_CONFIG["VLLM_PORT"]),
    (r"qwen3\.5-35b|qwen122b|qwen-122b|qwen3-vl|qwen2\.5", GOLDEN_CONFIG["MODEL_NAME"]),
    (r"gpu-memory-utilization\s+0\.[0-9]+", f"gpu-memory-utilization {GOLDEN_CONFIG['GPU_UTIL']}"),
    (r"MAX_OCR_CONCURRENCY\"\s+grep -v \"[0-9]+\"", f"MAX_OCR_CONCURRENCY\" | grep -v \"{GOLDEN_CONFIG['CONCURRENCY']}\""),
    (r"VLLM_VISION_TIMEOUT\"\s+grep -v \"[0-9]+\"", f"VLLM_VISION_TIMEOUT\" | grep -v \"{GOLDEN_CONFIG['TIMEOUT']}\""),
]

def optimize_workflows():
    logger.info(f"🔍 Starting Workflow Self-Optimization in {WORKFLOW_DIR}...")
    
    if not os.path.exists(WORKFLOW_DIR):
        logger.error(f"Directory not found: {WORKFLOW_DIR}")
        return

    updated_count = 0
    for filename in os.listdir(WORKFLOW_DIR):
        if not filename.endswith(".md"):
            continue
            
        file_path = os.path.join(WORKFLOW_DIR, filename)
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        new_lines = []
        changed = False
        for line in lines:
            new_line = line
            # Skip replacing in grep/search command lines to preserve audit logic
            if "grep" not in line and "Search" not in line:
                for pattern, replacement in MAPS:
                    new_line = re.sub(pattern, replacement, new_line)
            
            if new_line != line:
                changed = True
            new_lines.append(new_line)
            
        if changed:
            logger.info(f"  ✨ Updating {filename} with latest architectural standards...")
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            updated_count += 1
            
    if updated_count == 0:
        logger.info("  ✅ All workflows are already up to date with the Golden State.")
    else:
        logger.info(f"  🚀 Optimized {updated_count} workflow files.")

if __name__ == "__main__":
    optimize_workflows()
