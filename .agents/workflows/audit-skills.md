---
name: audit-skills
command: /audit-skills
description: Scans all agent skills for outdated references, broken endpoints, and potential improvements. Includes self-optimization.
type: workflow
category: custom
enabled: true
version: v4.0
---

// turbo-all

## Audit All Skills v4.0

1. List all registered skills:
```bash
echo "📋 Registered Skills:"; for d in /home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/*/; do name=$(basename "$d"); desc=$(head -4 "$d/SKILL.md" 2>/dev/null | grep "description:" | sed 's/description: //'); echo "  • $name — $desc"; done
```

2. Verify shared module imports:
```bash
echo "🐍 Checking vllm_client imports..."; for script in /home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/*/scripts/*.py; do if grep -q "from vllm_client" "$script" 2>/dev/null; then echo "  ✅ $(basename $(dirname $(dirname $script)))/$(basename $script)"; fi; done
```

3. Search for outdated references:
```bash
echo "🔍 Checking outdated references..."
echo "--- OLD MODELS (Should not exist) ---"
grep -rnEi "qwen3.5-9b-rag|qwen3-8b|vllm-9b|smartest-brain|smart-brain" /home/vvc/Codebase/dgx-spark-toolkit/.agents/ --include="*.md" --include="*.py" --include="*.yaml" 2>/dev/null || echo "  ✅ No old model references found."
echo "--- CORRECT ALIASES ---"
grep -rnE "rag-core|rag-light" /home/vvc/Codebase/dgx-spark-toolkit/.agents/ --include="*.md" --include="*.py" || echo "  ℹ️ No alias references found."
```

4. Verify current config:
```bash
echo "🚀 Checking .env config..."
echo "--- OCR CONCURRENCY ---"
grep -n "MAX_OCR_CONCURRENCY" /home/vvc/Codebase/dgx-spark-toolkit/.env | head -n 3 || echo "  ⚠️ MAX_OCR_CONCURRENCY not set"
echo "--- EMBEDDING MODEL ---"
grep -n "EMBEDDING_MODEL" /home/vvc/Codebase/dgx-spark-toolkit/.env | head -n 3 || echo "  ⚠️ EMBEDDING_MODEL not set"
```

5. Self-Optimization:
```bash
echo "🤖 Running Self-Optimization..."
if [ -f "/home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/vllm-manager/scripts/workflow_optimizer.py" ]; then
    python3 /home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/vllm-manager/scripts/workflow_optimizer.py
else
    echo "  ⚠️ workflow_optimizer.py missing."
fi
```

6. Skill directory sizes:
```bash
echo "📊 Skill sizes:"; du -sh /home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/*/ 2>/dev/null | sort -rh | head -10
```
