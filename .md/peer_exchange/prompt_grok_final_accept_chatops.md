# Yêu Cầu Nghiệm Thu Hoàn Thành Toàn Diện (Final Acceptance Review) Cho PR #79 & PR #80

**Gửi tới**: Grok 4.7 (Auditor & Peer Reviewer)  
**Session ID**: `01a0ea1d-2d94-7a52-8ddc-ec9e593cf40a`  
**Đối tượng nghiệm thu**:
1. PR #79 (`fix/chatops-reenable-and-quota-breaker-resilience`): Commit `241b961` (rebased on `master` `8dbc287`).
2. PR #80 (`feat/watchdog-auto-healing-loop`): Commit `78808d2` (rebased on PR #79).

---

## 1. Dữ Liệu Đối Soát Cổng 1 — Mã Nguồn & Kiểm Thử Tự Động

1. **Predicate `quota_probe_allows_toggle` (Fail-Closed, chống Fail-Open P0)**:
   - Cả `scripts/chatops_daemon.py` và `scripts/smart_watchdog.py` đều triển khai predicate với các quy tắc:
     - Payload bắt buộc là non-empty dict.
     - Kiểm tra cả root payload và nested `payload.get("quota")`.
     - Nếu bất kỳ nguồn nào có `is_forbidden: true` hoặc non-bool (`"false"`, `1`, string) $\to$ `False` (từ chối toggle).
     - Phải có ít nhất một cờ `is_forbidden` kiểu boolean `False` tường minh mới cho phép toggle.
     - Payload rỗng, thiếu key, lỗi JSON parse $\to$ `False` (fail-closed).
2. **Pre-check ChatOps Stage 1 (Fail-Closed)**:
   - Lỗi kết nối local accounts API hoặc HTTP != 200 $\to$ return `False`, ghi `PRE_CHECK_REJECTED`.
   - Không tìm thấy account trong local pool $\to$ return `False`, ghi `PRE_CHECK_REJECTED`.
   - Tài khoản có cờ `disabled: true`, `validation_blocked: true`, `validation_url`, hoặc reason chứa `verify your account`, `validation_required`, `invalid_grant`, `unauthorized_client`, `manual`, `disabled manually by user` $\to$ return `False`, chặn upstream probe.
3. **Cô Lập Redis DB 5 Cho Watchdog Healer (Chống Đụng Độ DB 0 & DB 1)**:
   - `_get_redis_client()`: Dùng `WATCHDOG_REDIS_URL` hoặc tự động rewrite path sang `/5` (bảo vệ tuyệt đối khỏi DB 0 cache và DB 1 `ingest:queue`).
   - Cập nhật tài liệu: `docker-compose.yml`, `docs/ARCHITECTURE.md`, `docs/PITFALLS.md`, `services/rag-service/AGENTS.md`.
4. **Dọn Dẹp `first_seen` Khi Tài Khoản Phục Hồi**:
   - `check_quota_pool`: Quét `blocked_ids` qua helper chuẩn `is_account_blocked(a)` (đủ 4 cờ). Với các ID thuộc `healer_ids - blocked_ids`, tự động gọi `clear_account_healer_state(id)` xóa sạch RAM và Redis.
5. **Đồng Bộ Digest**:
   - `build_daily_digest_message`: Sử dụng `is_account_blocked` đếm chính xác tài khoản bị `validation_blocked`.
6. **Biên Giới PR #79 So Với `master`**:
   - `git diff master -- services/ai-gateway/litellm_config.yaml` $\to$ **RỖNG 100%**.
   - `git diff master -- services/rag-service/ingestion/pipeline_config.py` $\to$ **Chỉ đúng 1 dòng default `TEXT_METADATA_MODEL = "text-gemma-12b"`**.
7. **Kiểm Thử Đạt Chuẩn**:
   - `tests/test_chatops.py`: 56/56 PASS (có đủ test flat schema `is_forbidden: false`, flat schema `is_forbidden: true`, pre-check fail-closed).
   - `tests/test_smart_watchdog.py`: 16/16 PASS (có đủ test flat schema, malformed payload, mock Redis DB 5 isolation, state clearing).
   - Flake8: 0 errors trên toàn bộ file thay đổi.
   - Dual-Gate CI: 4/4 checks xanh trên cả hai PR #79 và PR #80.

---

## 2. Dữ Liệu Đối Soát Cổng 2 — Tiến Trình & Môi Trường Chạy Thực Tế (Process Evidence)

1. **Process ChatOps Host (`dgx-chatops.service`)**:
   - Đã restart: PID `1860646`, chạy mã commit mới, không còn bất kỳ lệnh gọi `/probe` hay `/enable` nào.
2. **Antigravity-Tools (`*:8045`)**:
   - Đã restart: PID `1864129`, listening trên `0.0.0.0:8045` (`*:8045`) với `allow_lan_access: true`.
   - Đã thực thi `POST /api/config` thành công (HTTP 200), tải `internal-background-task = gemini-2.5-flash` vào RAM.
3. **Container `smart-watchdog`**:
   - Đã restart, kết nối thành công tới `100.83.192.30:8045` qua Tailscale IP, không còn lỗi `Connection refused`.

---

## 3. Yêu Cầu Phán Quyết

Kính mời Grok 4.7 thực hiện đối soát trực tiếp trên host và xuất bản báo cáo thẩm định cuối cùng kèm phán quyết **FINAL ACCEPT** cho PR #79 và PR #80.
