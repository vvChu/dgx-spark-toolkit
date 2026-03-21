---
name: idop-app-scaffolder
description: Helper to scaffold consistent module structures for the IDOP platform.
---

# IDOP Module Scaffolding

This skill ensures that all new modules added to the IDOP ecosystem follow a consistent architecture.

## Architecture Standard

A standard IDOP module consists of:

### Frontend
*   Located in `src/modules/<module-name>`
*   Structure:
    *   `components/`: React components specific to this module.
    *   `hooks/`: Custom hooks.
    *   `store.ts`: Zustand store slice.
    *   `routes.tsx`: Route definitions.

### Backend
*   Located in `server/modules/<module-name>`
*   Structure:
    *   `controller.js`: Request handlers.
    *   `service.js`: Business logic.
    *   `routes.js`: Express router definition.

## Tools

### Scaffold Script
Use `resources/scaffold-module.sh` to generate the directory structure automatically.

**Usage**:
`./.agent/skills/idop-app-scaffolder/resources/scaffold-module.sh <module_name> <target_project_root>`

*   **Tip**: The Agent should always pass the absolute path of the workspace (e.g., `/home/vvc/Documents/Test idea/bim-planner`) as the second argument.

## Best Practices
1.  **Isolation**: Modules should be self-contained. Avoid importing deep into another module's directory.
2.  **Shared UI**: Use the core Design System components from `src/components/ui` instead of creating new ones.
