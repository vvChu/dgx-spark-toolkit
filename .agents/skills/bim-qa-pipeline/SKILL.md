---
name: BIM QA Pipeline
command: /bim-qa-pipeline
description: Automated Quality Assurance and Testing standards.
type: skill
category: custom
enabled: true
version: v3.0
---

# BIM QA Pipeline

This skill ensures that code meets quality standards before being considered "Done".

## Standards
1.  **Linting**: Use `eslint` for both frontend and backend. No errors allowed.
2.  **Type Check**: TypeScript compiler (`tsc`) must pass.
3.  **Build**: The project must be buildable (`npm run build`).

## Tools
### Run Checks (`run-checks.sh`)
Use this script to verify the entire project in one go.

**Usage**:
`./.agent/skills/bim-qa-pipeline/resources/run-checks.sh <ActiveWorkspaceRoot>`

*   **Tip**: Run this before notifying the user of task completion.

## Failure Handling
*   If `lint` fails: Fix the style errors automatically if possible (`--fix`).
*   If `build` fails: Review the error log and fix imports/types.
