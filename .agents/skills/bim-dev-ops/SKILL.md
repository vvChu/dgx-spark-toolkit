---
name: BIM Planner DevOps
command: /bim-planner-devops
description: Utilities and guidelines for developing and operating the BIM Planner application.
type: skill
category: custom
enabled: true
version: v3.0
---

# BIM Planner Development & Operations

This skill helps manage the `bim-planner` full-stack application. It includes utilities for running the environment and guidelines for code consistency.

## Environment Setup

The application consists of a React Frontend (Vite) and a Node.js Backend.

**Project Root**: `/home/vvc/Documents/Test idea/bim-planner`

### Running the Application (Unified)

To avoid managing two separate terminals, use the `start-dev.sh` script located in `resources/`.

1.  **Command**: `./.agent/skills/bim-dev-ops/resources/start-dev.sh <ActiveWorkspaceRoot>`
    *   *Note*: The agent must pass the absolute path of the workspace as the first argument.
2.  **Function**:
    *   Starts the Node.js API server (`server/index.js`) on port 3000.
    *   Starts the Vite frontend dev server on port 5173.
    *   Streams logs from both to the current console.

## Codebase Guidelines

### Backend (`server/`)
*   **Entry Point**: `index.js`. Keep this file clean. Move complex logic to dedicated route files or controllers if the app grows.
*   **Database**: Currently uses in-memory/file-based. If integrating a real DB, create a `db/` folder.

### Frontend (`src/`)
*   **State Management**: Use `zustand`. Store generic stores in `src/store/`.
*   **Styling**: Use Tailwind CSS (via `index.css`) or standard CSS modules. Avoid inline styles for major components.
*   **Components**:
    *   `src/components/`: Reusable UI components.
    *   `src/pages/`: Page-level components matched to routes.

## Deployment (Draft)
*   **Build**: Run `npm run build` in the root specific directory to build the frontend.
*   **Serve**: The backend should serve the usage of `dist/` folder in production.
