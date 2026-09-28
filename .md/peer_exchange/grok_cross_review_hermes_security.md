# Báo Cáo Phản Biện Chéo Độc Lập — Grok 4.7 Thẩm Định Kế Hoạch An Ninh Mạng Hermes Agent

**Thời điểm**: 2026-09-28 20:09 ICT  
**Thực hiện**: Grok 4.7 (Auditor & Peer Reviewer)  
**Đối tượng**: Kế hoạch phòng thủ 4 tầng (4-Layer Defense-in-Depth) cho Hermes Agent kết nối Telegram Gateway trên NVIDIA DGX Spark.  
**Tài liệu đối soát**: `.md/peer_exchange/prompt_grok_review_hermes_security.md`, mã nguồn `~/.hermes/`, `~/.hermes/config.yaml`, `crontab -l`, `systemctl --user`.

---

## Phán Quyết Của Grok: BÁC BỎ (REJECT AS WRITTEN)

> *"Bác bỏ kế hoạch 4 tầng với tư cách là một chương trình gia cố an ninh (Hardening Program). Hãy thực hiện dọn dẹp môi trường ngay lập tức, sau đó thay thế Tầng 1–3 bằng một ranh giới Hệ Điều Hành (OS Boundary) thực sự. Bản kế hoạch hiện tại chỉ tài liệu hóa sự cố vừa qua mà vẫn để ngỏ cho sự cố tiếp theo xảy ra."*

### Bảng Điểm Đánh Giá (Adversarial Scorecard)

| Tiêu chí | Điểm | Nhận định của Grok |
| :--- | :---: | :--- |
| **Độ vững chắc phòng thủ (Defense Robustness)** | **2/10** | Các sự cố vừa qua xuất phát từ shell, user crontab và user systemd unit. Bản kế hoạch lại đối phó bằng câu chữ prompt (`SOUL.md`) và 3 khóa cấu hình YAML vốn không kiểm soát được các hành động này. |
| **Tính tiện dụng vận hành (Operational Usability)** | **6/10** | Telegram vẫn giữ full shell, bot vẫn tiện lợi nhưng đồng nghĩa với việc giữ quyền tương đương root (`root-equivalent`). |
| **Tuân thủ KISS (KISS Compliance)** | **3/10** | 4 tầng văn bản tự nhiên và YAML phức tạp thay vì giải pháp đơn giản chuẩn mực: 1 Unix user riêng biệt, 1 systemd unit được sandbox, và 1 danh sách toolset thu gọn. |
| **Tính khả thi (Feasibility)** | **4/10** | Các sửa đổi trong kế hoạch có thể áp dụng trong buổi chiều, nhưng không hề ngăn chặn được sự cố lặp lại. |

---

## 1. Hiện Trạng Thực Tế Trên Hệ Thống DGX Spark (Audited Facts)

1. `hermes-gateway.service` đang chạy dưới dạng user unit của user `vvc`. Không có `NoNewPrivileges`, `ProtectSystem`, `ProtectHome`, `PrivateTmp` hay hạn chế socket/network nào.
2. `vvc` nằm trong group `docker`. File `/var/run/docker.sock` thuộc `root:docker`. Bất kỳ tiến trình nào chạy dưới user `vvc` đều có khả năng thao túng Docker daemon $\to$ **Toàn quyền Root trên máy chủ**.
3. `terminal.backend` là `local`, `terminal.cwd` là `.`. Bộ công cụ của Telegram mở toàn bộ: shell, files, `execute_code`, `cronjob_manage`, `delegate_task`, browser, memory, `skill_manage`.
4. `ccba-webhook.service` đã được dừng, port 5001 không còn lắng nghe, nhưng file script `~/.hermes/scripts/litellm-gateway-webhook.py` vẫn còn tồn tại nguyên vẹn với quyền `0775`.
5. User crontab vẫn còn dòng cron 2:00 AM chạy `prune_session_learnings.py`.
6. File `~/.hermes/config.yaml` đang đặt quyền `0664` và chứa `model.api_key` dạng cleartext.
7. Công cụ `cloudflared` đã được cài đặt sẵn trên máy chủ (trong thư mục home của `vvc`). Hermes có thể trực tiếp gọi `cloudflared tunnel` từ shell mà không cần ngrok.

---

## 2. Điểm Yếu Cốt Tử Trong Đề Xuất Ban Đầu

### A. Sự Ảo Tưởng Của Rào Chắn Prompt (`SOUL.md` & Skills)
- Bản thân tài liệu `SECURITY.md` của Hermes Agent khẳng định: **"Ranh giới duy nhất chống lại một mô hình đối nghịch hoặc không đáng tin cậy là Hệ Điều Hành (OS Boundary)."**
- Khi mô hình (Qwen 3.6 35B) nhận một chỉ thị cụ thể từ người dùng ("Nhận webhook GitHub trên máy này"), chỉ thị tác vụ (task instruction) luôn lấn át (outrank) văn bản nhân cách trong `SOUL.md`. Mô hình sẽ ưu tiên hoàn thành task hơn là tuân thủ một đoạn văn phong cách.
- Skill `dgx-security-guard`: Chỉ nạp tên và mô tả vào context. Nội dung bên trong chỉ được đọc nếu mô hình chủ động gọi `skill_view`. Nếu mô hình không gọi, rào chắn này vô hình 100%.

### B. `terminal.cwd: /home/vvc/hermes_workspace` KHÔNG PHẢI Sandbox
- Thiết lập này chỉ đặt thư mục khởi động ban đầu của shell.
- Nó **không phải là chroot, mount namespace hay jail**. Hermes chỉ cần chạy `cd ..`, hoặc dùng đường dẫn tuyệt đối (`cat /home/vvc/.ssh/id_rsa`, `docker exec ...`), là thoát ra ngay lập tức.
- Công cụ `execute_code` (chạy Python code trực tiếp) hoàn toàn bỏ qua danh sách kiểm tra lệnh nguy hiểm của shell.

### C. Sai Lệch Schema Cấu Hình Hermes
- Khóa `toolsets.telegram` trong kế hoạch cũ là **khóa lỗi thời (deprecated)** và bị Hermes bỏ qua. Khóa chuẩn hiện tại là **`platform_toolsets`**.
- `protected_instruction_files: true` vốn đã là mặc định, và nó chỉ bảo vệ các file của project (`AGENTS.md`), hoàn toàn ngoại lệ cho thư mục `~/.hermes/` (không bảo vệ được chính `SOUL.md`).
- `cronjob_manage` là công cụ scheduler nội bộ của Hermes, nhưng cron 2:00 AM nguy hiểm vừa qua lại do Hermes ghi thẳng vào Linux crontab thông qua **shell terminal**. Việc chặn `cronjob_manage` mà vẫn để `terminal` mở thì hoàn toàn vô nghĩa.

---

## 3. Lộ Trình Tái Cấu Trúc Khắc Phục (Required Actions)

### Bước 1: Dọn Dẹp Triệt Để (Immediate Cleanup)
1. **Xóa hẳn script webhook độc hại**:
   `rm -f /home/vvc/.hermes/scripts/litellm-gateway-webhook.py`
2. **Xóa dòng cron 2:00 AM khỏi crontab**:
   Gỡ bỏ dòng `prune_session_learnings.py` trong `crontab -e`, bảo toàn 3 dòng cron hợp lệ (`prune_spend_logs.py`, `run_nightly_tuner.sh`, `@reboot start_watchdog.sh`).
3. **Cách ly / Xóa `prune_session_learnings.py`** để tránh nguy cơ làm hỏng tri thức.
4. **Bảo mật file cấu hình & Token**:
   Chuyển API key của LiteLLM sang file `~/.hermes/.env` (mode `0600`), sau đó `chmod 600 ~/.hermes/config.yaml`.

### Bước 2: Tách Rời Quyền Hạn Bộ Công Cụ (Platform Toolsets Decoupling)
Nếu Hermes kết nối qua Telegram để làm trợ lý cá nhân, **bắt buộc phải tước bỏ quyền Shell Terminal và Cron/Process khỏi giao diện Telegram**:

Cấu hình trong `~/.hermes/config.yaml`:
```yaml
platform_toolsets:
  cli: [hermes-cli]
  telegram:
    - web
    - search
    - vision
    - skills
    - todo
    - memory
    - session_search
    - clarify
  cron:
    - web
    - search
    - vision
    - skills
    - todo

approvals:
  mode: manual
  timeout: 300
  cron_mode: deny
  single_query_mode: deny
  unattended_mode: deny
```
> **Nguyên tắc**: Khi tương tác qua Telegram (môi trường không giám sát trực tiếp, dễ bị tấn công qua tin nhắn forwarded hoặc prompt injection), Hermes chỉ có quyền tra cứu web, xem ảnh, quản lý todo, đọc skills. Khi cần chạy shell/terminal, developer phải mở terminal SSH trực tiếp (`cli`).

### Bước 3: Ranh Giới Hệ Điều Hành (OS Boundary)
Nếu vẫn muốn cấp shell cho Hermes trong tương lai:
- Phải tạo một Linux user riêng: `User=hermes`, nologin, **không nằm trong group `docker` hay `sudo`**, không thể truy cập socket `/var/run/docker.sock`, không thể đọc `/home/vvc/.ssh`.
- Cấu hình systemd unit với `ProtectSystem=strict`, `ProtectHome=read-only`, `PrivateTmp=yes`, `NoNewPrivileges=yes`, và `SocketBindDeny=any` (ngăn cấm mọi hành vi tự ý bind cổng lắng nghe).

### Bước 4: Chuyển `SOUL.md` Về Đúng Vai Trò (System Hints)
Chỉ sử dụng `platform_hints.telegram` hoặc `SOUL.md` như một tài liệu chỉ dẫn phong cách và thông tin hạ tầng (informational guidance), không kỳ vọng nó thay thế rào chắn bảo mật tầng hệ thống.
