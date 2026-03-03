---
description: Review recent activity to identify repetitive patterns and propose new Skills.
---

// turbo-all

## Audit All Skills

This workflow scans all agent skills for outdated references, broken endpoints, and potential improvements.

1. List all registered skills:
```bash
echo "📋 Registered Skills:"; for d in /home/vvc/Codebase/dgx-spark-toolkit/.agent/skills/*/; do name=$(basename "$d"); desc=$(head -3 "$d/SKILL.md" 2>/dev/null | grep "description:" | sed 's/description: //'); echo "  • $name — $desc"; done
```

2. Verify all Python skill scripts can import shared module:
```bash
echo "🐍 Checking shared module imports..."; for script in /home/vvc/Codebase/dgx-spark-toolkit/.agent/skills/*/scripts/*.py; do if grep -q "from vllm_client" "$script" 2>/dev/null; then echo "  ✅ $(basename $(dirname $(dirname $script)))/$(basename $script) — uses shared module"; elif grep -q "VLLM\|vllm" "$script" 2>/dev/null; then echo "  ⚠️ $(basename $(dirname $(dirname $script)))/$(basename $script) — direct vLLM usage (not shared)"; fi; done
```

3. Show skill directory sizes:
```bash
echo "📊 Skill sizes:"; du -sh /home/vvc/Codebase/dgx-spark-toolkit/.agent/skills/*/ 2>/dev/null | sort -rh | head -15
```
