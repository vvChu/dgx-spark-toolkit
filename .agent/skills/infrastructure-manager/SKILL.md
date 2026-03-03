---
name: Infrastructure Manager
description: Interface for managing server infrastructure using dgx-spark-toolkit resources.
---

# Infrastructure Manager

This skill leverages the existing `dgx-spark-toolkit` to manage infrastructure, deployment, and AI service configuration.

## Resource Locations

**Toolkit Root**: `/home/vvc/Codebase/dgx-spark-toolkit`

### Scripts (`scripts/`)
Contains shell scripts for direct execution.
*   **Start All Services**: `scripts/start-all.sh` (Launches vLLM containers + Docker Compose stack).
*   **Stop All Services**: `scripts/stop-all.sh` (Gracefully shuts down everything).
*   **Remote Access**: `scripts/setup-remote-access.sh`.

### Playbooks (`playbooks/`)
Contains step-by-step guides for setup and integration.
*   **LLM API Guide**: `playbooks/llm-api-guide.md` (vLLM OpenAI-compatible API usage).
*   **Remote Access**: `playbooks/remote-access.md`.

## Usage Guidelines
1.  **Tool Discovery**: Check `TOOL_REGISTRY.md` in this skill folder first.
2.  **Execution**:
    ```bash
    bash scripts/start-all.sh   # Start everything
    bash scripts/stop-all.sh    # Stop everything
    ```
3.  **Or use chat workflows**: `/start-all`, `/stop-all`, `/health`
