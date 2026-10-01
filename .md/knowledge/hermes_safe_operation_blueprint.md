# 🛡️ Thiết Lập An Toàn Vận Hành Hermes Agent Trên DGX Spark
## Architectural Blueprint & Threat Modeling (Đã Thẩm Định Bởi Grok 4.7)

**Tài liệu tham chiếu**: `dgx-spark-toolkit` (Spoke Workspace)  
**Thời điểm lập**: 2026-10-01 ICT  
**Trạng thái**: **APPROVE_WITH_CONDITIONS** (Đã tích hợp phản biện từ Grok 4.7 xhigh)  
**Nhánh Git**: `feat/hermes-safe-operation-setup`  
**Liên kết liên quan**: PR #76, Ticket #67 (Linux POSIX ACLs), Grok 4.7 Review ([grok_review_hermes_safe_setup.md](file:///home/vvc/Codebase/dgx-spark-toolkit/.md/peer_exchange/grok_review_hermes_safe_setup.md))

---

## 1. Bối Cảnh Thực Tế & Hiện Trạng Đo Đạc Trực Tiếp

Qua đối soát trực tiếp trên máy chủ DGX Spark (NVIDIA GB10 Blackwell 128GB Unified Memory):
- **Tiến trình đang chạy**: Tiến trình PID 2638 (`hermes gateway run`) đang chạy dưới tư cách user `vvc` (UID 1000).
- **Hạ tầng máy chủ**: Host đang vận hành **23 Docker containers production** (`qwen36b`, `ai-gateway`, `rag-service`, `milvus`, `neo4j`, `postgres`, `open-webui`, `portainer`...). User `vvc` thuộc group `docker` (toàn quyền truy cập socket Docker).
- **Cấu hình Hermes hiện tại (`~/.hermes/config.yaml`)**:
  - `terminal.backend: local` $\rightarrow$ LLM thực thi trực tiếp mọi lệnh shell trên máy chủ host.
  - CWD thực tế của tiến trình Hermes đang là `~/.hermes` (chứa tệp cấu hình và keys).
  - `tool_loop_guardrails.hard_stop_enabled: false` $\rightarrow$ Chưa bật ngắt cứng khi tool bị lặp vô tận trên interactive sessions.
- **Tình trạng phân quyền secrets**:
  - `~/.hermes/.env` và `auth.json` đã có quyền `chmod 600`.
  - `~/.hermes/config.yaml` chứa virtual key inline đang có quyền `rw-rw-r--` $\rightarrow$ Cần `chmod 600`.
  - `TELEGRAM_ALLOWED_USERS=5645114631` (Đã khóa cứng ID Admin Vv C).

---

## 2. Kết Quả Thẩm Định Độc Lập Từ Grok 4.7 xhigh

Grok 4.7 đã ban hành phán quyết **CHẤP THUẬN CÓ ĐIỀU KIỆN (Approve with Conditions)** kèm 4 điều kiện cốt lõi:

| # | Điều Kiện Thẩm Định | Giải Pháp Điều Chỉnh |
|---|--------------------|----------------------|
| **1** | **Kiểm soát Non-CLI Toolset** | Xác nhận `code_execution`, `terminal`, `file` bị loại khỏi toolset Telegram, chỉ giữ các tool giao tiếp an toàn. |
| **2** | **Docker Sandbox Network Isolation** | Tạo mạng riêng `hermes-sandbox-net` chỉ kết nối với `ai-gateway`. Không forward secret tokens vào container sandbox (`docker_forward_env` chỉ chứa `OPENAI_BASE_URL`). |
| **3** | **Cân bằng Ngưỡng Circuit Breakers** | Ngưỡng `3/4/3` quá nhạy (dễ ngắt nhầm khi `pip install` hoặc debug test). Điều chỉnh thành: `exact_failure: 4`, `same_tool_failure: 6`, `idempotent_no_progress: 4`. |
| **4** | **Bảo vệ Secrets & Ghim Thư Mục CWD** | `chmod 600 ~/.hermes/config.yaml`. Tạo thư mục `/home/vvc/hermes_workspace` (`chmod 750`) trước khi ghim `terminal.cwd`. |

**Khuyến nghị bổ sung từ Grok**:
- Thêm `max_tokens: 16384` vào entry `local-coder` trên LiteLLM Gateway để chặn đứng runaway reasoning loops ở tầng inference của vLLM.
- Giảm `timeout` của `local-coder` từ 900s xuống 600s.

---

## 3. Lộ Trình Triển Khai 2 Giai Đoạn (2-Phase Hardening)

### Giai Đoạn 1: Siết Chặt Cấu Hình Ngay Lập Tức (Zero-Regression)
1. **Khởi tạo Workspace Độc Lập**:
   ```bash
   mkdir -p /home/vvc/hermes_workspace && chmod 750 /home/vvc/hermes_workspace
   ```
2. **Cập nhật `~/.hermes/config.yaml`**:
   - `terminal.cwd: "/home/vvc/hermes_workspace"`
   - `tool_loop_guardrails.hard_stop_enabled: true`
   - `tool_loop_guardrails.hard_stop_after`: `exact_failure: 4`, `same_tool_failure: 6`, `idempotent_no_progress: 4`
   - `model.default: "local-coder"`
3. **Phân quyền và bảo mật Secrets**:
   - `chmod 600 ~/.hermes/config.yaml ~/.hermes/.env ~/.hermes/auth.json`
   - Bổ sung `TELEGRAM_ALLOW_BOTS=none` vào `~/.hermes/.env`.
4. **Cấu hình LiteLLM Gateway (`litellm_config.yaml`)**:
   - Bổ sung `max_tokens: 16384` và `timeout: 600` cho entry `local-coder`.
5. **Khởi động lại Hermes Gateway & Giám sát 48h**.

### Giai Đoạn 2: Kích Hoạt Ranh Giới Cách Ly Hệ Điều Hành
1. **Thiết lập Docker Network Sandbox**:
   - `docker network create hermes-sandbox-net`
   - `docker network connect hermes-sandbox-net ai-gateway`
2. **Chuyển `terminal.backend: docker`**:
   - Mount `/workspace` từ `/home/vvc/hermes_workspace`.
   - Giới hạn 4 vCPU, 8GB RAM.
   - Chỉ forward `OPENAI_BASE_URL` vào container.
3. **Lộ trình dài hạn với Ticket #67**:
   - Tạo user `hermes-runner` tước quyền Docker socket, áp dụng POSIX ACLs.
