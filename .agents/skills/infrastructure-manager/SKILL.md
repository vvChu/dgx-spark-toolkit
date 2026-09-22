---
name: infrastructure-manager
description: Interface for managing server infrastructure, dgx-chatops daemon, and safe Open WebUI upgrades using dgx-spark-toolkit resources.
---

# Infrastructure Manager

This skill leverages the existing `dgx-spark-toolkit` to manage infrastructure, deployment, and AI service configuration.

## Resource Locations

**Toolkit Root**: `/home/vvc/Codebase/dgx-spark-toolkit`

### Scripts (`scripts/`)
Contains shell and python scripts for direct execution.
*   **Start All Services**: `scripts/start-all.sh` (Launches vLLM containers + Docker Compose stack).
*   **Stop All Services**: `scripts/stop-all.sh` (Gracefully shuts down everything).
*   **Remote Access**: `scripts/setup-remote-access.sh`.
*   **Safe Open WebUI Upgrade**: `scripts/update-openwebui.sh` (6-stage WAL-safe SQLite snapshot, automated rollback).
*   **ChatOps Universal Daemon**: `scripts/chatops_daemon.py` (Telegram bot poller, REST `:8095`, chained audit log).

### ChatOps & Telegram Administration
*   **Systemd Service**: `systemctl --user {status|restart|stop} dgx-chatops`
*   **Logs**: `journalctl --user -u dgx-chatops -f`
*   **Audit Trail**: `logs/chatops/audit.jsonl` (Chained SHA-256 integrity)
*   **Touch Dashboard**: Gõ `/menu` trên Telegram để xem dashboard cảm ứng, kiểm tra GPU Blackwell, khởi động lại container, hoặc nâng cấp Open WebUI.

### Playbooks (`playbooks/`)
Contains step-by-step guides for setup and integration.
*   **LLM API Guide**: `playbooks/llm-api-guide.md` (vLLM OpenAI-compatible API usage).
*   **Remote Access**: `playbooks/remote-access.md`.

## Usage Guidelines
1.  **Tool Discovery**: Check `TOOL_REGISTRY.md` in this skill folder first.
2.  **Execution**:
    ```bash
    bash scripts/start-all.sh                # Start everything
    bash scripts/stop-all.sh                 # Stop everything
    bash scripts/update-openwebui.sh [ver]   # Safe upgrade Open WebUI (e.g. v0.11.4)
    systemctl --user status dgx-chatops      # Check ChatOps daemon status
    ```
3.  **Or use chat workflows**: `/start-all`, `/stop-all`, `/health`, `/menu`

