# Infrastructure Manager — Tool Registry

All available tools and resources for managing the DGX Spark infrastructure.

## Scripts

| Command | Description |
|---------|-------------|
| `bash scripts/start-all.sh` | Start vLLM containers + full Docker stack |
| `bash scripts/stop-all.sh` | Gracefully stop everything |
| `sudo bash scripts/setup-remote-access.sh` | Open firewall ports for remote access |

## Workflows (Chat Commands)

| Command | Description |
|---------|-------------|
| `/start-all` | Start all services |
| `/stop-all` | Stop all services |
| `/health` | Check health of all services |
| `/setup-remote` | Configure remote access |

## Service Endpoints

| Service | Local URL | Remote URL (Tailscale) |
|---------|-----------|----------------------|
| AI Gateway | `http://localhost:8090` | `http://<TAILSCALE_IP>:8090` |
| RAG Service | `http://localhost:8005` | `http://<TAILSCALE_IP>:8005` |
| Qwen 35B vLLM | `http://localhost:8004` | `http://<TAILSCALE_IP>:8004` |
| Milvus | `http://localhost:19530` | — |
| Prometheus | `http://localhost:9090` | — |
| Grafana | `http://localhost:3000` | — |

## Key Config Files

| File | Purpose |
|------|---------|
| `.env` | Master environment config |
| `services/ai-gateway/litellm_config.yaml` | Gateway model definitions + fallbacks |
| `docker-compose.yml` | Full stack orchestration |

## Auth

- **Gateway API Key**: `$LITELLM_MASTER_KEY` (set via `LITELLM_MASTER_KEY` in `.env`)
- **Proxy Key**: set via `GATEWAY_PROXY_KEY` in `.env`
