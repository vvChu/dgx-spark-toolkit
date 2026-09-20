# Bản đồ Định hướng (Wayfinding Map): Tối ưu hóa Toàn diện Antigravity Tools & Gateway Cluster
**Mã bản đồ:** `MAP-SPARK-ANTIGRAVITY-OPT-20260920`  
**Trạng thái:** `Completed (Hoàn thành nghiệm thu)`  
**Hệ thống liên quan:** AI Gateway Cluster — Server Spark (`100.83.192.30:8045` & `:8090`)  
**Công cụ đích:** Antigravity Tools (Antigravity-Manager `v4.7.8`) & LiteLLM (`v1.83.3`)  

---

## 1. Điểm đích (Destination) — [ĐÃ ĐẠT 100%]
Đưa toàn bộ cụm hạ tầng AI Gateway (Antigravity Tools `:8045` + LiteLLM `:8090`) đạt trạng thái vận hành tối ưu 24/7 theo chuẩn Best Practices của phiên bản **`v4.7.8`**, cụ thể:
1. **Quản lý Quota**: Kích hoạt chế độ `Balance` (Cache hit 85%+, Failover 50ms), bật `7-Day Warmup Scheduler` và bảo vệ tài khoản khi cạn kiệt (`lock_on_zero_quota`).
2. **Suy luận & Ngữ cảnh**: Thiết lập quyền kiểm soát Thinking Budget về Gateway (`control_source`), loại bỏ bug ngân sách độc, cấu hình nén an toàn L1 (RTK Denoising) bảo toàn Prompt Caching.
3. **Lưu trữ & Hệ thống**: Thiết lập hạn mức lưu trữ SQLite (1.0 GB + 30% Sliding Window Eviction) và bật `loginctl enable-linger` cho user `vvc`, chạy headless hoàn toàn qua `xvfb-run -a` độc lập phiên XRDP.
4. **Kiểm thử nghiệm thu (E2E Verification)**: 100% các request Gemini 3.8 Flash High, Claude Opus Thinking đều đi đúng model, không bị 429 giả, không bị silent downgrade.

---

## 2. Ghi chú (Notes)
- **Hạ tầng**: NVIDIA DGX Spark (GB10 Blackwell, 128GB Unified Memory), Ubuntu 24.04 aarch64.
- **Tập tin cấu hình chính**:
  - Antigravity Tools GUI: `/home/vvc/.antigravity_tools/gui_config.json`
  - Antigravity Tools Service: `/home/vvc/.config/systemd/user/antigravity-tools.service`
  - LiteLLM Gateway: `/home/vvc/Codebase/dgx-spark-toolkit/services/ai-gateway/litellm_config.yaml`
  - Environment: `/home/vvc/Codebase/dgx-spark-toolkit/.env`
- **Kỹ năng áp dụng**: `/ccba-wayfinder`, `/boost` (Adversarial Review).

---

## 3. Quyết định đã chốt (Decisions so far)
- [x] **[DEC-01] Nâng cấp Antigravity Tools lên v4.7.8**: Đã cài package `v4.7.8` chính thức qua `dpkg -i` và liên kết symlink tại `/usr/bin/antigravity-tools` và `~/.local/bin/`.
- [x] **[DEC-02] Chuyển đổi sang Systemd User Service Headless với Xvfb**: Chạy qua `xvfb-run -a`, tự cấp phát virtual display độc lập trong RAM, loại bỏ hoàn toàn nguy cơ crash khi khởi động không có XRDP.
- [x] **[DEC-03] Minh bạch hóa Header & Timeout LiteLLM**: Cấu hình `add_response_headers: true`, `store_model_in_db: true`, nâng timeout `gemini38-flash-high-base` và `claude-opus-4-6-thinking` lên `90s`.
- [x] **[DEC-04] Đồng bộ Repository Source Code**: Nhánh `main` của `/home/vvc/Codebase/Antigravity-Manager` đã checkout tại tag `v4.7.8`.
- [x] **[DEC-05] Kích hoạt Linux Linger**: `loginctl enable-linger vvc` kích hoạt thành công (`Linger=yes`), giữ service chạy vĩnh viễn 24/7.
- [x] **[DEC-06] Quyết định Phản biện Kiến trúc (Adversarial Decisions)**:
  - *Từ chối Caveman Compression (L2/L3)* để bảo toàn tỷ lệ trúng Prompt Caching 85%+.
  - *Không thêm map `gemini-3.8-flash-high`* để tránh tước bỏ hậu tố `-high` của heuristic v4.7.8.
  - Sửa đúng schema `lock_on_zero_quota` vào `circuit_breaker` và `log_retention` vào `proxy`.

---

## 4. Danh sách Ticket & Kết quả Nghiệm thu

| Mã Ticket | Tên Ticket | Phân loại | Trạng thái | Ngày hoàn tất |
| :--- | :--- | :--- | :---: | :---: |
| **[TICK-01](tickets/TICK-01-scheduling-quota-breaker.md)** | [Cấu hình Scheduling Mode Balance & Quota Breaker](tickets/TICK-01-scheduling-quota-breaker.md) | `Task [AFK]` | **Completed** | 20/09/2026 |
| **[TICK-02](tickets/TICK-02-scheduled-warmup.md)** | [Kích hoạt 7-Day Smart Warmup Scheduler](tickets/TICK-02-scheduled-warmup.md) | `Task [AFK]` | **Completed** | 20/09/2026 |
| **[TICK-03](tickets/TICK-03-thinking-budget-context.md)** | [Tối ưu Thinking Budget & Nén Ngữ Cảnh L1](tickets/TICK-03-thinking-budget-context.md) | `Task [AFK]` | **Completed** | 20/09/2026 |
| **[TICK-04](tickets/TICK-04-storage-sliding-window.md)** | [Cấu hình Giới Hạn Lưu Trữ SQLite & Log Retention](tickets/TICK-04-storage-sliding-window.md) | `Task [AFK]` | **Completed** | 20/09/2026 |
| **[TICK-05](tickets/TICK-05-linux-linger-daemon.md)** | [Kích hoạt Linux Linger & Cố Định Daemon Headless qua Xvfb](tickets/TICK-05-linux-linger-daemon.md) | `Task [AFK]` | **Completed** | 20/09/2026 |
| **[TICK-06](tickets/TICK-06-e2e-verification.md)** | [Nghiệm thu Tích hợp End-to-End & Stress Test](tickets/TICK-06-e2e-verification.md) | `Task [AFK]` | **Completed** | 20/09/2026 |

---

## 5. Sương mù chiến trận / Chưa xác định rõ (Not yet specified)
- **FOG-01 (Proxy Pool Residential Binding)**: Khi số lượng tài khoản Google trong tương lai tăng $\ge 15$, sẽ nghiên cứu bổ sung pool residential proxy để gán IP riêng cho từng account.
- **FOG-02 (Tự động hóa đồng bộ client developer)**: Viết script tự động thiết lập `ANTHROPIC_BASE_URL` cho máy trạm dev.
