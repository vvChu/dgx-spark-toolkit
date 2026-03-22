---
name: fix-frontmatter
description: Validates and fixes YAML frontmatter in all SKILL.md files under .agents/skills/.
---

# Fix Frontmatter Skill

Scans all `.agents/skills/*/SKILL.md` files and ensures valid YAML frontmatter.

## Required Frontmatter Fields
Every SKILL.md must have:
```yaml
---
name: <skill-name>        # Must match the parent directory name
description: <one-liner>  # Non-empty description
---
```

## Steps

### 1. Discover all SKILL.md files
```
Glob: .agents/skills/*/SKILL.md
```

### 2. Validate each file
For each SKILL.md:
- Check that the file starts with `---`
- Check that `name:` field exists and is non-empty
- Check that `description:` field exists and is non-empty
- Check that the frontmatter block is closed with `---`
- Verify `name` matches the parent directory name

### 3. Report
```
=== Frontmatter Validation ===
[PASS] skill-name — name: OK, description: OK
[FAIL] skill-name — missing description
...
Total: X passed, Y failed
```

### 4. Fix (if failures found)
For each failing SKILL.md:
- If `name` is missing, add it from the directory name
- If `description` is missing, add a placeholder: `description: TODO — add description`
- If frontmatter block is malformed, reconstruct it preserving existing valid fields

Only edit files that fail validation. Do not modify passing files.
