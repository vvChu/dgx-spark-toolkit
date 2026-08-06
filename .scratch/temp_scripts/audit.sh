#!/bin/bash
echo "📋 Registered Skills:"
for d in /home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/*/; do 
  name=$(basename "$d")
  desc=$(head -4 "$d/SKILL.md" 2>/dev/null | grep "description:" | sed 's/description: //')
  echo "  • $name — $desc"
done

echo -e "\n🐍 Checking vllm_client imports..."
for script in /home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/*/scripts/*.py; do 
  if grep -q "from vllm_client" "$script" 2>/dev/null; then 
    echo "  ✅ $(basename $(dirname $(dirname $script)))/$(basename $script)"
  fi
done

echo -e "\n🔍 Checking outdated references..."
echo "--- OLD MODELS (Should not exist) ---"
grep -rnEi "qwen3.5-9b-rag|qwen3-8b|vllm-9b|smartest-brain|smart-brain" /home/vvc/Codebase/dgx-spark-toolkit/.agents/ --include="*.md" --include="*.py" --include="*.yaml" 2>/dev/null || echo "  ✅ No old model references found."

echo "--- CORRECT ALIASES ---"
grep -rnE "rag-core|rag-light" /home/vvc/Codebase/dgx-spark-toolkit/.agents/ --include="*.md" --include="*.py" || echo "  ℹ️ No alias references found."

echo -e "\n🚀 Checking .env config..."
echo "--- OCR CONCURRENCY ---"
grep -n "MAX_OCR_CONCURRENCY" /home/vvc/Codebase/dgx-spark-toolkit/.env | head -n 3 || echo "  ⚠️ MAX_OCR_CONCURRENCY not set"
echo "--- EMBEDDING MODEL ---"
grep -n "EMBEDDING_MODEL" /home/vvc/Codebase/dgx-spark-toolkit/.env | head -n 3 || echo "  ⚠️ EMBEDDING_MODEL not set"

echo -e "\n🤖 Running Self-Optimization..."
if [ -f "/home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/vllm-manager/scripts/workflow_optimizer.py" ]; then
    cd /home/vvc && timeout 15 /usr/bin/python3 -u /home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/vllm-manager/scripts/workflow_optimizer.py
else
    echo "  ⚠️ workflow_optimizer.py missing."
fi

echo -e "\n📊 Skill sizes:"
du -sh /home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/*/ 2>/dev/null | sort -rh | head -10
