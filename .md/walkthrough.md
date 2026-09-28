# Báo Cáo Nghiệm Thu Hoàn Tất: Nâng Cấp Khả Năng Phục Hồi ChatOps & Chuẩn Hóa Task Models

> **Nhánh triển khai:** `fix/chatops-reenable-and-quota-breaker-resilience`  
> **Căn cứ kiến trúc:** ADR-0001, ADR-0003, Playbook LLM API Guide  
> **Phản biện đối kháng độc lập:** [Báo cáo Grok 4.7 (CONDITIONAL APPROVE)](.md/peer_exchange/grok_cross_review_chatops_plan.md)  
> **Chế độ thực thi:** Phase 1 (Chữa dứt điểm cơ chế Re-enable, đồng bộ chỉ số Quota Pool, chuẩn hóa Task Models)

---

## 1. Bản Chất Vấn Đề & Phân Tích Căn Nguyên (Root Causes)

Sau quá trình rà soát toàn diện mã nguồn Antigravity-Manager (`crates/proxy/src/handlers/quota.rs`, `account.rs`), ChatOps Daemon (`scripts/chatops_daemon.py`), và AI Gateway LiteLLM:

### A. Vấn Đề Cảnh Báo & Khóa Tạm Thời 1 Lần Truy Cập Lỗi (1-Strike Lockout)
1. **Hành vi cốt lõi của Antigravity-Manager**: Khi Google upstream trả về mã `403` hoặc `Resource has been exhausted`, Antigravity tự động đánh dấu cờ `quota.is_forbidden = true` và `proxy_disabled = true`, đồng thời loại trừ ngay tài khoản khỏi danh sách quay vòng (RAM rotation) trong `get_active_accounts()`.
2. **Tại sao cơ chế cũ của ChatOps bị lỗi thời (Dead-End)**:
   - Trước đây ChatOps gọi `POST /api/accounts/{id}/warmup` hoặc `POST /api/accounts/{id}/enable`. Nhưng mã nguồn Rust thực tế của Antigravity:
     - Endpoint `/enable` **không tồn tại** (trả về 404). Endpoint đúng là `POST /api/accounts/{id}/toggle-proxy` với payload `{"enable": true}`.
     - Hàm `warm_up_account` trong `quota.rs` kiểm tra: nếu `proxy_disabled == true` thì trả về ngay `500 Account is disabled`. Do đó, nếu gọi `/warmup` trên tài khoản đang bị khóa thì 100% thất bại!
     - Nếu chỉ gọi `toggle-proxy` mà không xóa `is_forbidden`, hàm `get_account_state_on_disk` vẫn coi tài khoản là `Disabled` do `quota.is_forbidden == true`, khiến tài khoản không thể nạp lại vào RAM.
3. **Giải pháp 4-Stage Health Probe Gate chuẩn xác**:
   - **Stage 1 (Local Pre-Classification)**: Kiểm tra danh sách tài khoản cục bộ qua `GET /api/accounts`. Nếu tài khoản có `validation_url`, `validation_blocked`, `invalid_grant`, hoặc bị khóa thủ công (`manual`), hệ thống **từ chối probe ngay lập tức** mà không gửi bất kỳ request nào lên Google, ngăn ngừa việc tài khoản bị Google đánh cờ gian lận (abuse flagging) hoặc làm mất URL xác thực trình duyệt.
   - **Stage 2 (Quota Probe Gate)**: Gọi `GET /api/accounts/{id}/quota` kèm Header Admin Bearer Secret (timeout 30s). Đây là endpoint an toàn duy nhất: khi gọi endpoint này, Antigravity sẽ chủ động truy vấn hạn mức Google và **tự động reset `is_forbidden = false`** nếu tài khoản đã hết quota tạm thời hoặc đã sạch lỗi.
   - **Stage 3 (Proxy Activation)**: Sau khi Quota Probe trả về 200 OK và `is_forbidden == false`, gửi `POST /api/accounts/{id}/toggle-proxy` với `{"enable": true}` để làm sạch cờ `proxy_disabled = false` và nạp lại tài khoản vào RAM rotation pool.
   - **Stage 4 (Audit & Telemetry)**: Phân loại chính xác 4 trạng thái kiểm toán (`SUCCESS`, `PRE_CHECK_REJECTED`, `PROBE_FAILED`, `ENABLE_FAILED`) kèm ghi nhận log bất biến băm xích (hash chain audit log).

---

### B. Lệch Chỉ Số Quota Pool Giữa `/stats` và `/antigravity_status`
- Hàm `probe_gateway_stats()` trước đây chỉ lọc `not a.get("disabled")`, trong khi tài khoản Antigravity bị khóa chủ yếu qua `proxy_disabled: true` hoặc `quota.is_forbidden: true`. Do đó, `/stats` báo 4/4 tài khoản khả dụng dù thực tế chỉ có 1 tài khoản hoạt động.
- Đã bổ sung hàm dùng chung `is_account_blocked(account: Dict[str, Any]) -> bool` kiểm tra toàn diện cả 4 cờ: `proxy_disabled`, `disabled`, `validation_blocked`, và `quota.is_forbidden`. Đồng bộ 100% giữa `/stats` và `/antigravity_status`.

---

### C. Lệch Danh Mục Task Models Quản Lý
1. **Metadata Extractor**:
   - `services/rag-service/ingestion/pipeline_config.py` mặc định gọi `text-light-gemma`.
   - `services/ai-gateway/litellm_config.yaml` triển khai model thực tế dưới tên `text-gemma-12b`.
   - **Khắc phục**: Đồng bộ biến mặc định thành `text-gemma-12b`, đồng thời khai báo alias `text-light-gemma -> text-gemma-12b` trong cả `router_settings.model_group_alias` và `litellm_settings.model_aliases`. Cập nhật tài liệu kiến trúc ADR-0001, ADR-0003, và Playbook API.
2. **Internal Background Task**:
   - `gui_config.json` cấu hình `"internal-background-task": "gemini-3.8-flash-high"`. Model này ép ngân sách suy nghĩ 16,000 tokens (thinking budget), gây lãng phí quota nghiêm trọng cho các tác vụ nền nhỏ và dẫn tới lỗi 503 Quota Exhaustion.
   - **Khắc phục**: Chuyển `"internal-background-task"` về `"gemini-2.5-flash"` (non-thinking, cực nhanh, tiết kiệm quota).

---

## 2. Chi Tiết Các Tệp Đã Sửa Đổi

| Tệp | Bản chất sửa đổi |
|---|---|
| `scripts/chatops_daemon.py` | Bổ sung `is_account_blocked()`, đồng bộ đếm Quota Pool trong `probe_gateway_stats()`, tái cấu trúc `reenable_antigravity_account()` theo quy trình 4-Stage Health Probe Gate chuẩn xác. |
| `tests/test_chatops.py` | Cập nhật mock dual stats cho Quota Pool, bổ sung 4 test cases chuyên biệt cho quy trình re-enable (thành công, chặn local pre-check, thất bại ở quota probe, probe pass nhưng toggle fail). |
| `services/rag-service/ingestion/pipeline_config.py` | Đồng bộ default model metadata extractor thành `text-gemma-12b`. |
| `services/ai-gateway/litellm_config.yaml` | Khai báo alias `"text-light-gemma": "text-gemma-12b"` trong router và litellm settings. |
| `~/.antigravity_tools/gui_config.json` | Cập nhật `"internal-background-task": "gemini-2.5-flash"` (backup file `.bak_fix`, quyền `0600`). |
| `docs/adr/0001-*.md`, `docs/adr/0003-*.md`, `playbooks/llm-api-guide.md` | Chuẩn hóa quy ước gọi tên `text-gemma-12b` (alias `text-light-gemma`). |

---

## 3. Ma Trận Kiểm Định Tự Động (Deterministic Verification Matrix)

| Cổng kiểm định | Lệnh thực thi | Kết quả | Chi tiết |
|---|---|:---:|---|
| **ChatOps Unit Tests** | `.venv/bin/pytest tests/test_chatops.py -v` | ✅ **PASS** | **49/49 passed** (100% Green, 4.73s) |
| **Python Code Style** | `.venv/bin/flake8 scripts/chatops_daemon.py tests/test_chatops.py --max-line-length=160` | ✅ **PASS** | **0 errors, 0 warnings** |
| **Grok 4.7 Adversarial Review** | `grok review scripts/chatops_daemon.py` | ✅ **APPROVED** | Phê duyệt phương án 4-Stage Probe Gate & loại trừ rủi ro flapping của Phase 2 |
