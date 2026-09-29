# Infrastructure Manager — Tool Registry

Single Source of Truth (SSoT) cho toàn bộ công cụ, scripts, workflows và tài nguyên vận hành hạ tầng DGX Spark.

## Scripts

| Command | Description |
|---------|-------------|
| `bash scripts/start-all.sh` | Khởi động toàn bộ container vLLM + Docker Compose stack |
| `bash scripts/stop-all.sh` | Dừng an toàn toàn bộ hệ thống |
| `sudo bash scripts/setup-remote-access.sh` | Mở các cổng firewall cho truy cập từ xa qua Tailscale |
| `bash scripts/update-openwebui.sh [ver]` | Nâng cấp an toàn Open WebUI với WAL-safe SQLite snapshot & tự động rollback |
| `python3 scripts/chatops_daemon.py` | ChatOps Universal Gateway daemon (Telegram bot poller, REST :8095) |
| `python3 scripts/smart_watchdog.py` | Smart Watchdog Healer daemon (giám sát quorum và tự phục hồi quota) |

## Workflows (Chat Commands)

| Command | Description |
|---------|-------------|
| `/start-all` | Khởi động toàn bộ dịch vụ hạ tầng |
| `/stop-all` | Dừng toàn bộ dịch vụ hạ tầng |
| `/health` | Kiểm tra sức khỏe toàn diện các dịch vụ |
| `/menu` | Mở Telegram Interactive Touch Dashboard |
| `/status` | Kiểm tra CPU, RAM, NVMe, và trạng thái các container cốt lõi |
| `/gpu` | Giám sát chỉ số phần cứng GPU NVIDIA Blackwell GB10 và VRAM |
| `/stats` | Báo cáo thống kê đồng bộ Quota Pool, GPU và throughput |
| `/antigravity` | Kiểm tra trạng thái chi tiết các tài khoản và proxy Antigravity (:8045) |
| `/reenable_account <id>` | Kích hoạt quy trình 4-Stage Health Probe Gate để bật lại tài khoản quota sạch |
| `/upgrade_owu [ver]` | Nâng cấp an toàn Open WebUI lên phiên bản chỉ định hoặc mới nhất |
| `/restart <service>` | Khởi động lại container Docker nằm trong danh sách whitelist an toàn |
| `/rag_state` | Kiểm tra hàng đợi nạp tài liệu và trạng thái xử lý RAG |

## Service Endpoints

| Service | Local URL | Remote URL (Tailscale) | Ghi Chú |
|---------|-----------|------------------------|---------|
| Open WebUI | `http://localhost:3001` | `http://<TAILSCALE_IP>:3001` | Giao diện Chat chính |
| ChatOps Gateway | `http://localhost:8095` | `http://<TAILSCALE_IP>:8095` | REST API quản trị & webhook |
| AI Gateway | `http://localhost:8090` | `http://<TAILSCALE_IP>:8090` | LiteLLM Proxy đa mô hình |
| Antigravity Proxy | `http://localhost:8045` | `http://<TAILSCALE_IP>:8045` | Upstream Gemini Quota Pool |
| RAG Service | `http://localhost:8005` | `http://<TAILSCALE_IP>:8005` | FastAPI RAG backend |
| Qwen 35B vLLM | `http://localhost:8004` | `http://<TAILSCALE_IP>:8004` | Local model serving |
| Milvus Standalone | `http://localhost:19530` | — | Vector Database |
| Neo4j Browser | `http://localhost:7474` | — | Knowledge Graph Database |
| Prometheus | `http://localhost:9090` | — | Metrics collector |
| Grafana | `http://localhost:3000` | — | Dashboard giám sát |

## Systemd User Services

| Service Name | Command | Description |
|--------------|---------|-------------|
| `dgx-chatops` | `systemctl --user {status\|restart\|stop} dgx-chatops` | 24/7 Universal ChatOps Gateway |
| `antigravity-tools` | `systemctl --user {status\|restart\|stop} antigravity-tools` | Headless GUI & Antigravity Proxy (:8045) |

## Redis Database Split

| DB Index | Alias | Mục Đích |
|----------|-------|----------|
| `DB 0` | `litellm:cache` | Cache LiteLLM và state routing |
| `DB 1` | `ingest:queue` | Hàng đợi nạp tài liệu Celery/Redis |
| `DB 2` | `context:lake` | Context Lake & Semantic Cache tài liệu |
| `DB 3` | `semantic:l2` | SemanticCache L2 |
| `DB 4` | `hitl:state` | Human-In-The-Loop review sessions |
| `DB 5` | `watchdog:healer` | Trạng thái tự phục hồi tài khoản (`watchdog:healer:*`) |

## Key Config Files

| File | Purpose |
|------|---------|
| `.env` | Cấu hình biến môi trường tổng thể |
| `scripts/chatops_commands.yaml` | Registry lệnh ChatOps, regex whitelist và phân cấp rủi ro |
| `logs/chatops/audit.jsonl` | Append-only SHA-256 chained audit trail |
| `services/ai-gateway/litellm_config.yaml` | Định nghĩa mô hình Gateway & fallbacks |
| `~/.config/antigravity/gui_config.json` | Cấu hình Antigravity-Tools (`allow_lan_access`, model mapping) |
| `docker-compose.yml` | Điều phối toàn bộ Docker stack |
