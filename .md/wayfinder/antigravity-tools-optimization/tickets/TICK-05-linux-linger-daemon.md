# Ticket [TICK-05]: Kích hoạt Linux Linger & Cố Định Daemon 24/7

**Bản đồ cha:** [Bản đồ Định hướng Tối ưu Antigravity Tools](../map.md)  
**Phân loại:** `Task [HITL / AFK]`  
**Trạng thái:** `Completed (Done)`  
**Assignee:** Antigravity Agent  
**Ngày hoàn tất:** 20/09/2026  

---

## 1. Mục tiêu đã hoàn thành
- Kích hoạt thành công `Linger=yes` cho user `vvc` trên máy chủ DGX Spark bằng lệnh:
  ```bash
  loginctl enable-linger vvc
  ```
- **Khắc phục lỗi Display XRDP bằng Xvfb**:
  - Đổi lệnh `ExecStart` trong `antigravity-tools.service` sang `/usr/bin/xvfb-run -a /home/vvc/.local/bin/antigravity-tools --minimized`.
  - Biến Antigravity Tools thành **headless daemon 100%**, cấp phát màn hình ảo tự động trong RAM, không bị crash restart khi server reboot chưa có phiên XRDP.

## 2. Thay đổi đã áp dụng
File `/home/vvc/.config/systemd/user/antigravity-tools.service`:
```ini
[Unit]
Description=Antigravity Tools Proxy Manager (Headless via Xvfb)
After=network.target

[Service]
Type=simple
Environment=XDG_RUNTIME_DIR=/run/user/1000
ExecStart=/usr/bin/xvfb-run -a /home/vvc/.local/bin/antigravity-tools --minimized
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

## 3. Nghiệm thu
- `loginctl show-user vvc | grep -i linger` $\rightarrow$ `Linger=yes`.
- Service chạy dưới `xvfb-run` ổn định, PID `2729277`, trạng thái `Active (running)`.
