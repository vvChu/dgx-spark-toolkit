"""
Workflow Self-Optimizer — Scans workflow .md files and fixes outdated
references to match the current Golden State architecture.

Safety: Only modifies workflow files (not docker-compose, .env, etc.).
Uses word-boundary regex to avoid corrupting model names in other contexts.
"""
import os
import re
import signal
import logging

# Hard timeout to prevent hangs during audit
signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("Script timed out")))
signal.alarm(30)  # 30 second max

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# --- Golden State Configuration ---
GOLDEN_CONFIG = {
    "VLLM_PORT": "8004",
    "GATEWAY_PORT": "8090",
    "MODEL_ALIAS_CORE": "rag-core",
    "MODEL_ALIAS_LIGHT": "rag-light",
    "GPU_UTIL": "0.70",
    "MAX_OCR_CONCURRENCY": "1",
    "TIMEOUT": "300",
}

WORKFLOW_DIR = "/home/vvc/Codebase/dgx-spark-toolkit/.agents/workflows/"

# Safe replacement patterns — word-boundary aware to avoid false matches
# Format: (compiled_regex, replacement, description)
SAFE_MAPS = [
    # Old vLLM ports → current port (only in curl/API URLs, not random numbers)
    (re.compile(r"localhost:(8001|8002)(/v1)"), f"localhost:{GOLDEN_CONFIG['VLLM_PORT']}\\2",
     "old vLLM port in API URLs"),

    # Old model names used as API model param → alias (in JSON-like contexts)
    (re.compile(r'"model":\s*"(?:qwen122b|qwen-122b)"'), f'"model": "{GOLDEN_CONFIG["MODEL_ALIAS_CORE"]}"',
     "old model name in JSON payload"),

    # gpu-memory-utilization value
    (re.compile(r"gpu-memory-utilization\s+0\.\d+"), f"gpu-memory-utilization {GOLDEN_CONFIG['GPU_UTIL']}",
     "GPU memory utilization"),
]

# Lines to NEVER modify (safety guard)
SKIP_PATTERNS = re.compile(r"grep|Search|--model\s+Qwen|--model\s+/|image:|docker|Dockerfile", re.IGNORECASE)


def optimize_workflows():
    logger.info(f"🔍 Scanning workflows in {WORKFLOW_DIR}...")

    if not os.path.exists(WORKFLOW_DIR):
        logger.error(f"  ❌ Directory not found: {WORKFLOW_DIR}")
        return

    total_changes = 0
    updated_files = []

    for filename in sorted(os.listdir(WORKFLOW_DIR)):
        if not filename.endswith(".md"):
            continue

        file_path = os.path.join(WORKFLOW_DIR, filename)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except (OSError, IOError) as e:
            logger.warning(f"  ⚠️ Cannot read {filename}: {e}")
            continue

        new_lines = []
        file_changes = 0
        for line in lines:
            new_line = line

            # Skip lines that contain grep/search commands or docker references
            if not SKIP_PATTERNS.search(line):
                for pattern, replacement, desc in SAFE_MAPS:
                    new_line, count = pattern.subn(replacement, new_line)
                    if count > 0:
                        file_changes += count

            new_lines.append(new_line)

        if file_changes > 0:
            logger.info(f"  ✨ {filename}: {file_changes} fix(es) applied")
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            updated_files.append(filename)
            total_changes += file_changes

    if total_changes == 0:
        logger.info("  ✅ All workflows match Golden State — no changes needed.")
    else:
        logger.info(f"  🚀 Applied {total_changes} fix(es) across {len(updated_files)} file(s).")


if __name__ == "__main__":
    try:
        optimize_workflows()
    except TimeoutError:
        logger.error("  ❌ Script timed out after 30s")
    except Exception as e:
        logger.error(f"  ❌ Unexpected error: {e}")
    finally:
        signal.alarm(0)  # Cancel alarm
