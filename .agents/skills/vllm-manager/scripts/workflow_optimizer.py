"""
Workflow Self-Optimizer 6.0 (Auto-Evolving)
Scans .md and .py files in workflows, playbooks, and skills to fix outdated
references and auto-enforce LiteLLM Aliases.

Future-proof capability: It scans litellm_config.yaml
to auto-discover raw models and force them to use Aliases.
"""
import os
import re
import sys
import signal
import logging

# Hard timeout to prevent hangs during audit
def _timeout_handler(signum, frame):
    raise TimeoutError("Script timed out after 30s")

signal.signal(signal.SIGALRM, _timeout_handler)
signal.alarm(30)  # 30 second max

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# --- Golden State Configuration ---
GOLDEN_CONFIG = {
    "VLLM_PORT": "8004",
    "GPU_UTIL": "0.70",
}

# Directories to apply ALL rules (static + dynamic alias)
SCAN_DIRS = [
    "/home/vvc/Codebase/dgx-spark-toolkit/.agents/workflows/",
    "/home/vvc/Codebase/dgx-spark-toolkit/playbooks/",
]

# Directories to apply ONLY static deprecated-name rules (no dynamic aliasing)
# Skills contain valid reference commands that should not be aliased
STATIC_ONLY_DIRS = [
    "/home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/",
]

# File extensions to process
SCAN_EXTENSIONS = (".md", ".py")

LITELLM_CONFIG_PATH = "/home/vvc/Codebase/dgx-spark-toolkit/services/ai-gateway/litellm_config.yaml"

# Safe replacement patterns — word-boundary aware to avoid false matches
SAFE_MAPS = [
    (re.compile(r"localhost:(8001|8002)(/v1)"), f"localhost:8004\\2", "old vLLM port in API URLs"),
    (re.compile(r'"model":\s*"(?:qwen122b|qwen-122b)"'), '"model": "rag-core"', "old model name in JSON payload"),
    (re.compile(r"gpu-memory-utilization\s+0\.\d+"), "gpu-memory-utilization 0.70", "GPU memory utilization"),
    # Catch deprecated model aliases used in scripts and docs
    (re.compile(r'"model":\s*"(?:smartest-brain|smart-brain)"'), '"model": "rag-core"', "deprecated smart-brain alias"),
    (re.compile(r'"model":\s*"qwen3\.5-9b-rag"'), '"model": "rag-light"', "deprecated qwen3.5-9b-rag alias"),
    # Catch bare string references (not inside grep/search patterns)
    (re.compile(r'(?<!")smartest-brain(?!")'), 'rag-core', "deprecated smartest-brain reference"),
]

# Snapshot of static rules (before dynamic aliases are added)
# Used for skills/ directories where dynamic aliasing is too aggressive
STATIC_SAFE_MAPS = list(SAFE_MAPS)

# Files that should NEVER be modified by this script (prevents self-corruption)
SELF_SKIP_FILES = {"workflow_optimizer.py"}

# Lines to NEVER modify (safety guard)
SKIP_PATTERNS = re.compile(
    r"grep|Search|--model\s+Qwen|--model\s+/|image:|docker|Dockerfile|"
    r"Should not exist|OLD MODELS|SAFE_MAPS|SKIP_PATTERNS|workflow_optimizer",
    re.IGNORECASE
)

def build_dynamic_ai_gateway_aliases():
    """
    AUTO-UPGRADE MECHANISM:
    Reads litellm_config.yaml to dynamically learn which raw models (e.g. gemma-4-31b-it)
    are hidden behind Aliases (e.g. reasoning-gemma). 
    It automatically builds regex rules to replace raw models with Aliases.
    """
    seen_patterns = set()  # Track already-registered pattern strings
    
    try:
        with open(LITELLM_CONFIG_PATH, 'r') as f:
            lines = f.readlines()
            
        current_alias = None
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("- model_name:"):
                current_alias = stripped.split("model_name:")[1].strip()
            # If we find a raw model mapping to an alias
            elif stripped.startswith("model:") and current_alias:
                raw_model = stripped.split("model:")[1].strip().strip('"').strip("'")
                # Strip prefix like openai/ or gemini/
                short_model = raw_model.split("/")[-1]
                
                # Skip if alias == raw model name, or empty values
                if not current_alias or not short_model or current_alias == short_model:
                    continue
                
                pattern_str = f'"model":\\s*"{re.escape(short_model)}"'
                
                # Prevent duplicate rules (e.g. 10 keys same model)
                if pattern_str not in seen_patterns:
                    seen_patterns.add(pattern_str)
                    SAFE_MAPS.append((
                        re.compile(pattern_str),
                        f'"model": "{current_alias}"',
                        f"Auto-Alias mapping: {short_model} -> {current_alias}"
                    ))
    except Exception as e:
        logger.warning(f"  ⚠️ Could not build dynamic aliases: {e}")

def _scan_directory(scan_dir, rules):
    """Scan a directory tree and apply the given replacement rules."""
    total_changes = 0
    updated_files = []

    if not os.path.exists(scan_dir):
        logger.info(f"  ⏭️  Skipping missing dir: {scan_dir}")
        return total_changes, updated_files

    for root, _, files in os.walk(scan_dir):
        for filename in sorted(files):
            if not filename.endswith(SCAN_EXTENSIONS):
                continue
            # Never modify our own source code
            if filename in SELF_SKIP_FILES:
                continue

            file_path = os.path.join(root, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except Exception:
                continue

            new_lines = []
            file_changes = 0
            for line in lines:
                new_line = line
                if not SKIP_PATTERNS.search(line):
                    for pattern, replacement, desc in rules:
                        new_line, count = pattern.subn(replacement, new_line)
                        if count > 0 and new_line != line:
                            file_changes += count

                new_lines.append(new_line)

            if file_changes > 0:
                logger.info(f"  ✨ {filename}: {file_changes} fix(es) applied")
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)
                updated_files.append(filename)
                total_changes += file_changes

    return total_changes, updated_files

def optimize_workflows():
    logger.info("🔍 Learning dynamic aliases from AI Gateway...")
    build_dynamic_ai_gateway_aliases()
    static_rule_count = len(STATIC_SAFE_MAPS)
    dynamic_rule_count = len(SAFE_MAPS) - static_rule_count
    logger.info(f"  📦 Loaded {static_rule_count} static + {dynamic_rule_count} dynamic rules.")

    total_changes = 0
    all_updated = []

    # Full rules (static + dynamic) for workflows and playbooks
    for scan_dir in SCAN_DIRS:
        changes, updated = _scan_directory(scan_dir, SAFE_MAPS)
        total_changes += changes
        all_updated.extend(updated)

    # Static-only rules for skills (no dynamic aliasing)
    for scan_dir in STATIC_ONLY_DIRS:
        changes, updated = _scan_directory(scan_dir, STATIC_SAFE_MAPS)
        total_changes += changes
        all_updated.extend(updated)

    if total_changes == 0:
        logger.info("  ✅ All files match Golden State — no changes needed.")
    else:
        logger.info(f"  🚀 Applied {total_changes} fix(es) across {len(all_updated)} file(s).")

if __name__ == "__main__":
    try:
        optimize_workflows()
    except TimeoutError as e:
        logger.error(f"  ❌ {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"  ❌ Unexpected error: {e}")
        sys.exit(1)
    finally:
        signal.alarm(0)
