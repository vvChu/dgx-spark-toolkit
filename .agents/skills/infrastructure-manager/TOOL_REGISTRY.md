# Infrastructure Manager — Tool Registry

All available tools and resources for managing the DGX Spark infrastructure.

## Scripts

| Command | Description |
|---------|-------------|
| `bash scripts/start-all.sh` | Start vLLM containers + full Docker stack |
| `bash scripts/stop-all.sh` | Gracefully stop everything |
| `sudo bash scripts/setup-remote-access.sh` | Open firewall ports for remote access |
| `bash scripts/update-openwebui.sh [ver]` | Safe Open WebUI upgrade with WAL-safe snapshot & auto-rollback |
| `python3 scripts/chatops_daemon.py` | ChatOps Universal Gateway daemon |

## Workflows (Chat Commands)

| Command | Description |
|---------|-------------|
| `/start-all` | Start all services |
| `/stop-all` | Stop all services |
| `/health` | Check health of all services |
| `/setup-remote` | Configure remote access |
| `/menu` | Telegram Interactive Touch Dashboard |
| `/status` | Check system CPU, RAM, NVMe, and core containers |
| `/gpu` | Probe NVIDIA Blackwell GB10 GPU metrics and VRAM |
| `/upgrade_owu [ver]` | Safely upgrade Open WebUI to specified or latest version |
| `/restart <service>` | Restart whitelisted Docker container |
| `/rag_state` | Check RAG ingestion queue and processing state |

## Service Endpoints

| Service | Local URL | Remote URL (Tailscale) |
|---------|-----------|----------------------|
| Open WebUI | `http://localhost:3001` | `http://<TAILSCALE_IP>:3001` |
| ChatOps Gateway | `http://localhost:8095` | `http://<TAILSCALE_IP>:8095` |
| AI Gateway | `http://localhost:8090` | `http://<TAILSCALE_IP>:8090` |
| RAG Service | `http://localhost:8005` | `http://<TAILSCALE_IP>:8005` |
| Qwen 35B vLLM | `http://localhost:8004` | `http://<TAILSCALE_IP>:8004` |
| Milvus | `http://localhost:19530` | — |
| Prometheus | `http://localhost:9090` | — |
| Grafana | `http://localhost:3000` | — |

## Systemd Services

| Service Name | Command | Description |
|--------------|---------|-------------|
| `dgx-chatops` | `systemctl --user {status\|restart\|stop} dgx-chatops` | 24/7 Universal ChatOps Gateway |

## Key Config Files

| File | Purpose |
|------|---------|
| `.env` | Master environment config |
| `scripts/chatops_commands.yaml` | ChatOps command registry, regex whitelist & risk tiers |
| `logs/chatops/audit.jsonl` | Append-only SHA-256 chained audit trail |
| `services/ai-gateway/litellm_config.yaml` | Gateway model definitions + fallbacks |
| `docker-compose.yml` | Full stack orchestration |

## Auth

- **Gateway API Key**: `$LITELLM_MASTER_KEY` (set via `LITELLM_MASTER_KEY` in `.env`)
- **Proxy Key**: set via `GATEWAY_PROXY_KEY` in `.env`
