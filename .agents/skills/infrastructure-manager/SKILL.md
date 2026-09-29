---
name: infrastructure-manager
description: (Legacy Pointer) Quản trị hạ tầng máy chủ DGX Spark. Trỏ tới canonical skill ccba-infrastructure-manager.
bundle: _software
---

# Infrastructure Manager (Pointer)

> [!NOTE]
> Kỹ năng chuẩn hóa chính thức đã được chuyển tiếp sang **[ccba-infrastructure-manager](../ccba-infrastructure-manager/SKILL.md)** tuân thủ quy chuẩn không gian tên CCBA (ADR-0056 / ADR-0057).
> Vui lòng tham chiếu [ccba-infrastructure-manager/SKILL.md](../ccba-infrastructure-manager/SKILL.md) để xem toàn bộ kiến trúc DGX Spark, ChatOps Universal Gateway, Smart Watchdog Healer, quy trình Socket LAN cổng 8045, và phân vùng Redis DB 5.

## Bảng Tra Cứu Công Cụ & Dịch Vụ

Toàn bộ công cụ, scripts thực thi và danh mục lệnh ChatOps được quản lý tập trung tại Single Source of Truth (SSoT):
👉 **[TOOL_REGISTRY.md](../ccba-infrastructure-manager/TOOL_REGISTRY.md)**

## Hướng Dẫn Vận Hành Nhanh

* **Khởi động toàn bộ dịch vụ**: `bash scripts/start-all.sh`
* **Dừng toàn bộ dịch vụ**: `bash scripts/stop-all.sh`
* **Nâng cấp an toàn Open WebUI**: `bash scripts/update-openwebui.sh [ver]`
* **Kiểm tra trạng thái ChatOps**: `systemctl --user status dgx-chatops`
* **Lệnh Telegram tương tác**: `/menu`, `/status`, `/gpu`, `/stats`, `/antigravity`, `/reenable_account <id>`
