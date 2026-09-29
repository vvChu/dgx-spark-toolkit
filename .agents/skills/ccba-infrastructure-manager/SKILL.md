---
name: ccba-infrastructure-manager
description: Quản trị hạ tầng máy chủ DGX Spark (Blackwell GB10), ChatOps Daemon, Smart Watchdog Healer, Redis DB 5 và dịch vụ Antigravity-Tools.
applies_to:
- Hạ tầng GPU
- Phần mềm
- Vận hành hệ thống
bundle: _software
tier: domain
command: /ccba-infrastructure-manager
metadata:
  version: "1.1.0"
  author: "CCBA Hub"
gpi:
  s: 3.0
  k: 2.0
  a: 3.0
  p: 1.0
triggers:
- dgx spark
- chatops
- smart watchdog
- antigravity tools
- infrastructure
- redis db 5
- socket binding
- account re-enable
---

# CCBA Infrastructure Manager

Kỹ năng này là Single Source of Truth (SSoT) cho việc quản lý, giám sát và vận hành hạ tầng máy chủ **NVIDIA DGX Spark** (Grace Blackwell GB10 128GB Unified Memory, ARM64 Ubuntu Linux), bao gồm DGX-ChatOps Universal Gateway, Smart Watchdog Healer, cấu hình mạng Socket Antigravity Proxy, và phân tách phân vùng dữ liệu Redis.

---

## 1. Mạng LAN & Ràng Buộc Socket Daemon (RULE-5.7)

### Hiện Tượng & Rủi Ro Cổng 8045
Headless GUI / Proxy tools (`antigravity-tools`) chỉ đọc cấu hình và bind socket lúc khởi động tiến trình. Nếu chỉ sửa tệp cấu hình `gui_config.json` trên đĩa mà không khởi động lại daemon đúng quy trình, tiến trình vẫn giữ socket `127.0.0.1:8045` trong RAM, khiến các Docker container trên cùng host kết nối qua Tailscale IP (`100.83.192.30:8045`) hoặc Docker gateway bị lỗi `Connection refused [Errno 111]`.

Hơn nữa, `systemctl --user restart antigravity-tools.service` không đảm bảo giải phóng và tái gán cổng ngay lập tức do shell `xvfb-run` cần thời gian dọn dẹp WebKit subprocesses, dẫn tới xung đột `EADDRINUSE`.

### Quy Trình 4 Bước Nghiêm Ngặt Khởi Động Socket
BẮT BUỘC thực thi tuần tự 4 bước sau với user `vvc` (`XDG_RUNTIME_DIR=/run/user/1000`):

```bash
# Bước 1: Dừng dịch vụ triệt để
systemctl --user stop antigravity-tools.service

# Bước 2: Chờ giải phóng socket với timeout 20s
TIMEOUT=20
while ss -tlnp | grep -q ":8045 "; do
    sleep 1
    TIMEOUT=$((TIMEOUT - 1))
    if [ $TIMEOUT -le 0 ]; then
        echo "ERROR: Port 8045 not released after 20s! Checking remaining PIDs..." >&2
        fuser -k 8045/tcp || true
        break
    fi
done

# Bước 3: Khởi động lại dịch vụ
systemctl --user start antigravity-tools.service

# Bước 4: Nghiệm thu listener và cây tiến trình
MAIN_PID=$(systemctl --user show -p MainPID --value antigravity-tools.service)
echo "MainPID: $MAIN_PID"

# Xác minh listener mở trên toàn bộ interfaces (0.0.0.0:8045 hoặc *:8045)
ss -tlnp | grep ":8045 " | grep -E "0\.0\.0\.0:8045|\*:8045" || {
    echo "ERROR: Socket not listening on 0.0.0.0:8045!" >&2
    exit 1
}

# Xác minh PID đang listen là MainPID hoặc tiến trình con cháu trong cây cgroup
LISTEN_PID=$(ss -tlnp | grep ":8045 " | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | head -n 1)
if [ -n "$LISTEN_PID" ]; then
    if [ "$LISTEN_PID" -eq "$MAIN_PID" ] || grep -q "$MAIN_PID" /proc/"$LISTEN_PID"/status 2>/dev/null || pgrep -P "$MAIN_PID" | grep -q "$LISTEN_PID"; then
        echo "SUCCESS: Port 8045 successfully bound to service process (PID $LISTEN_PID, descendant of MainPID $MAIN_PID)."
    else
        echo "WARNING: Listen PID $LISTEN_PID is not a descendant of MainPID $MAIN_PID. Verify zombie processes!" >&2
    fi
fi
```

> [!CAUTION]
> **Rào Chắn An Ninh Tường Lửa (Perimeter Firewall)**:
> Cờ `"allow_lan_access": true` mở socket listen `0.0.0.0:8045` trên mọi network interface của host. Quản trị viên BẮT BUỘC cấu hình iptables / ufw giới hạn chỉ cho phép interface VPN nội bộ `tailscale0` và Docker bridge `docker0` truy cập cổng 8045; nghiêm cấm để lộ cổng 8045 ra public interface.

---

## 2. Tối Ưu Hóa Model Cho Tác Vụ Nền (Proxy Auto-Titling)

Trong tệp cấu hình `~/.config/antigravity/gui_config.json`:
* Cấu hình `"internal-background-task": "gemini-3.8-flash-high"` ép 16,000 tokens thinking budget (`RULE-1.6`), làm cạn kiệt hạn mức quota và gây lỗi `503 Service Unavailable` cho các tác vụ nền định kỳ như tự sinh tiêu đề hội thoại (auto-titling).
* **Quy chuẩn bắt buộc**: Cấu hình `"internal-background-task": "gemini-2.5-flash"` (loại bỏ hậu tố `-high`).
* Việc này loại bỏ trần 16k token suy luận không cần thiết cho tác vụ đặt tên ngắn, giúp bảo toàn hạn mức tài khoản cho các pipeline nghiệp vụ và suy luận pháp lý chính quy.

---

## 3. Watchdog Auto-Healing & Phân Vùng Redis DB 5 (RULE-1.15)

### Bảng Phân Bổ Redis Database Toàn Hệ Thống
Để ngăn chặn hoàn toàn việc ô nhiễm dữ liệu và race condition giữa các services:

| DB Index | Tên Phân Vùng | Mục Đích Sử Dụng |
|---|---|---|
| **DB 0** | `litellm:cache` | Bộ nhớ đệm LiteLLM Proxy Gateway & trạng thái định tuyến |
| **DB 1** | `ingest:queue` | Hàng đợi nạp tài liệu Celery/Redis (`ingest:queue`, ingestion pipeline) |
| **DB 2** | `context:lake` | Context Lake & Semantic Cache tài liệu pháp luật |
| **DB 3** | `semantic:l2` | SemanticCache L2 (chuẩn khớp [PITFALLS.md](file:///home/vvc/Codebase/dgx-spark-toolkit/docs/PITFALLS.md)) |
| **DB 4** | `hitl:state` | Human-In-The-Loop review & verification sessions |
| **DB 5** | `watchdog:healer` | Trạng thái tự phục hồi tài khoản (`watchdog:healer:*`) |

### Bất Biến Cấu Hình `WATCHDOG_REDIS_URL`
1. Nếu biến môi trường `WATCHDOG_REDIS_URL` đã được thiết lập (kể cả trỏ vào `/15` hay `/0`), mã nguồn **sử dụng NGUYÊN VĂN URL đó**, không tự ý thay đổi.
2. Cơ chế tự động thay thế path sang `/5` **CHỈ kích hoạt khi `WATCHDOG_REDIS_URL` TRỐNG** và hệ thống phải fallback đọc từ `REDIS_URL`.
3. **CẤM TUYỆT ĐỐI**: Cấu hình biến `WATCHDOG_REDIS_URL` trỏ vào DB 0 (sẽ làm ô nhiễm bộ nhớ cache của LiteLLM).

### Quy Trình Tự Động Phục Hồi An Toàn (Healer Lifecycle)
Trong mỗi chu kỳ kiểm tra của Smart Watchdog (`scripts/smart_watchdog.py`):
1. **Lấy Snapshot**: Gọi `GET /api/accounts` để lấy danh sách tài khoản hiện tại.
   * **Tiêu chí hoàn thành:** Nhận snapshot JSON danh sách tài khoản từ endpoint quản trị.
2. **Dọn dẹp State cũ**: Dùng `SCAN` duyệt qua các khóa `watchdog:healer:first_seen:*`, nếu tài khoản tương ứng không còn bị chặn (`is_account_blocked` trả về `False`), lập tức xóa khóa `first_seen` và bộ đếm số lần thử của ID đó.
   * **Tiêu chí hoàn thành:** Redis DB 5 không còn chứa state của các tài khoản đã phục hồi sạch cờ.
3. **Phục hồi Đơn Lẻ (Single Candidate Auto-Heal)**:
   - Mỗi chu kỳ chỉ xử lý tối đa **1 tài khoản** hợp lệ để chống nghẽn mạng (fan-out / starvation).
   - Kiểm tra điều kiện: Thời gian khóa $\ge 3600\text{s}$, cách lần thử trước $\ge 3600\text{s}$, và số lần thử không vượt quá **3 lần / 24 giờ**.
   - **Quorum Guard**: Tạm dừng toàn bộ hoạt động auto-heal nếu tỷ lệ lỗi $\ge 50\%$ (`failed_ratio >= 0.5`) hoặc số tài khoản hoạt động $\le 2$ (`active_count <= 2`).
   * **Tiêu chí hoàn thành:** Chỉ có tối đa 1 ứng viên đạt đủ điều kiện được đưa vào quy trình thăm dò và kích hoạt.
4. **Khóa Phân Tán Inflight (Khuyến nghị Kiến trúc)**:
   - Áp dụng khóa `SET watchdog:healer:inflight:<account_id> 1 NX EX 90` trên DB 5 nhằm tránh tình trạng container watchdog và lệnh ChatOps thủ công cùng lúc kích hoạt probe/toggle trên cùng 1 tài khoản.
   - **Chỉ dẫn cho Agent**: Cấm gửi lại lệnh `POST /api/accounts/{id}/toggle-proxy` sau khi timeout nếu chưa đọc lại cờ `proxy_disabled`, nhằm phòng ngừa việc lật ngược trạng thái (toggle) do endpoint xử lý bất đối xứng.
   * **Tiêu chí hoàn thành:** Ngăn chặn hoàn toàn hiện tượng race condition giữa ChatOps và Watchdog.

---

## 4. Quy Trình 4-Stage Health Probe Gate

Hệ thống ChatOps và Smart Watchdog áp dụng quy trình kiểm soát 4 giai đoạn nghiêm ngặt trước khi bật lại tài khoản:

```
[Stage 1: Pre-Classification]
  ├── Challenge / Manual (validation_blocked, invalid_grant) ──► BÁO LỖI & DỪNG
  └── Quota-Exhausted Candidate ──► Chuyển sang Stage 2
                                        │
                                        ▼
[Stage 2: Quota Probe Gate] (GET /api/accounts/{id}/quota)
  ├── HTTP non-200 / Malformed JSON / Flag True ──► PROBE_FAILED & DỪNG
  └── Dual-Level Predicate PASS (RULE-1.17) ──► Chuyển sang Stage 3
                                        │
                                        ▼
[Stage 3: Proxy Activation] (POST /api/accounts/{id}/toggle-proxy {"enable": true})
  ├── HTTP 200 OK ──► Chuyển sang Stage 4
  └── Timeout / HTTP Error ──► ENABLE_FAILED & DỪNG
                                        │
                                        ▼
[Stage 4: Audit & Telemetry]
  └── Ghi log băm xích SHA-256 (SUCCESS / PRE_CHECK_REJECTED / PROBE_FAILED / ENABLE_FAILED / ERROR)
```

---

## 5. Thống Nhất Chỉ Số Quota Pool 4 Cờ (`is_account_blocked`)

Để đảm bảo các lệnh ChatOps `/stats`, `/antigravity`, Watchdog Quorum, và Telegram Daily Digest thống kê chính xác tuyệt đối:
* Hàm `is_account_blocked(account: dict)` kiểm tra truthiness của **đủ 4 cờ**:
  1. `account.get("proxy_disabled")`
  2. `account.get("disabled")`
  3. `account.get("validation_blocked")`
  4. `account.get("quota", {}).get("is_forbidden")`
* **Lưu ý Schema**: Cờ lồng `quota.is_forbidden` là cấu trúc đối tượng tài khoản lấy từ `GET /api/accounts`. Schema phẳng (`is_forbidden` ở root) chỉ xuất hiện trong body kết quả của `GET /api/accounts/{id}/quota`.

---

## 6. Bảng Lệnh Quản Trị ChatOps Chuẩn Hóa

Tra cứu chi tiết toàn bộ lệnh, endpoints và tệp cấu hình tại:
👉 **[TOOL_REGISTRY.md](TOOL_REGISTRY.md)**

Các lệnh chính thức khớp 100% với `scripts/chatops_commands.yaml`:
* `/reenable_account <id>`: Kích hoạt quy trình 4-Stage Health Probe Gate để bật lại tài khoản bị khóa quota.
* `/antigravity`: Kiểm tra chi tiết trạng thái Quota Pool và danh sách tài khoản proxy.
* `/stats`: Báo cáo thống kê đồng bộ Quota Pool, GPU Blackwell và Gateway throughput.
* `/menu`: Mở bảng điều khiển tương tác cảm ứng Telegram.

---

## Bất Biến Vận Hành & Khóa Cứng Hoàn Tất (ADR-0058)
* **Tiêu chí hoàn thành tất định:** Mọi thay đổi mã nguồn, kỹ năng hoặc tài liệu bắt buộc phải vượt qua bộ kiểm thử tự động.
* **Hard Completion Lock:** Nghiêm cấm tuyên bố hoàn thành task hoặc yêu cầu nghiệm thu nếu lệnh xác minh chưa vượt qua:
  ```bash
  python -m ccba_harness verify-patch
  ```
* **Zero Tolerance Exit Code:** Lệnh kiểm thử phải thoát với mã exit code 0; tuyệt đối không bỏ qua các lỗi linter hay hồi quy.

## Kỷ Luật Rà Soát Hai Vòng (Double-Pass Adversarial Review)
* **Vòng 1 (Code-First Research):** Luôn đọc implementation thực tế và kiểm tra data flow end-to-end trước khi sửa đổi. Không suy đoán hành vi từ tên hàm hay docstring.
* **Vòng 2 (Self-Adversarial Review):** Tự đặt câu hỏi: *Đề xuất này có thể SAI ở đâu?* Kiểm chứng tối thiểu 3 giả định cốt lõi bằng dữ liệu và kiểm thử thực tế trước khi bàn giao.
* **Bảo tồn Invariants:** Không bao giờ xóa hoặc nới lỏng (weaken) các bài test hiện có để làm cho bài test vượt qua.
