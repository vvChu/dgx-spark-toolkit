---
name: audit-skills
command: /audit-skills
description: Scans all agent skills for outdated references, broken endpoints, and potential improvements. Includes self-optimization.
type: workflow
category: custom
enabled: true
version: v3.0
---

// turbo-all

## Audit All Skills v3.1 (rag-core + rag-light + Parallel Optimization)
This workflow scans all agent skills for outdated references and self-optimizes to match current architecture (rag-core / rag-light).

1. List all registered skills:
```bash
echo "📋 Registered Skills (v3.1):"; for d in /home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/*/; do name=$(basename "$d"); desc=$(head -4 "$d/SKILL.md" 2>/dev/null | grep "description:" | sed 's/description: //'); echo "  • $name — $desc"; done
```

2. Verify shared module imports:
```bash
echo "🐍 Checking vllm_client imports..."; for script in /home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/*/scripts/*.py; do if grep -q "from vllm_client" "$script" 2>/dev/null; then echo "  ✅ $(basename $(dirname $(dirname $script)))/$(basename $script)"; fi; done
```

3. Search for outdated references (Post-Alias Optimization):
```bash
echo "🔍 Checking outdated references...";
echo "--- OLD MODELS (Should not exist) ---"
grep -rnEi "qwen3.5-9b-rag|qwen3.5-35b|qwen3-8b" /home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/ 2>/dev/null || echo "  ✅ No old model references found."
echo "--- CORRECT ALIASES ---"
grep -rnE "rag-core|rag-light" /home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/ || echo "  ✅ Aliases rag-core/rag-light active."
```

4. Verify Performance Optimization:
```bash
echo "🚀 Checking concurrency & timeouts...";
echo "--- OCR CONCURRENCY (Should be 4) ---"
grep -rn "MAX_OCR_CONCURRENCY=4" /home/vvc/Codebase/dgx-spark-toolkit/ | head -n 5 || echo "  ⚠️ MAX_OCR_CONCURRENCY not set to 4"
echo "--- TIMEOUT (Should be 300s) ---"
grep -rn "VLLM_VISION_TIMEOUT=300" /home/vvc/Codebase/dgx-spark-toolkit/ | head -n 5 || echo "  ⚠️ Timeout not optimized"
```

5. Audit RAG Data Quality:
```bash
echo "📊 Live RAG Quality Check...";
docker exec -it dgx-spark-toolkit-rag-watcher-1 python3 -c "print('Watcher healthy')" || echo "  ⚠️ rag-watcher not available or quality check failed."
```

6. Self-Optimization v3.1:
```bash
echo "🤖 Running Self-Optimization v3.1...";
# Note: Ensure workflow_optimizer.py exists and is updated
if [ -f "/home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/vllm-manager/scripts/workflow_optimizer.py" ]; then
    python3 /home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/vllm-manager/scripts/workflow_optimizer.py
else
    echo "  ⚠️ workflow_optimizer.py missing."
fi
```

7. Skill directory sizes:
```bash
echo "📊 Skill sizes:"; du -sh /home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/*/ 2>/dev/null | sort -rh | head -10
```
