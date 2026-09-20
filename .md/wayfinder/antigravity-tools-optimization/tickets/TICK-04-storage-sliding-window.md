# Ticket [TICK-04]: Cấu hình Giới Hạn Lưu Trữ SQLite & Log Retention

**Bản đồ cha:** [Bản đồ Định hướng Tối ưu Antigravity Tools](../map.md)  
**Phân loại:** `Task [AFK]`  
**Trạng thái:** `Completed (Done)`  
**Assignee:** Antigravity Agent  
**Ngày hoàn tất:** 20/09/2026  

---

## 1. Mục tiêu đã hoàn thành
- Thiết lập hạn ngạch lưu trữ `proxy_logs.db` tối đa 1.0 GB (`max_disk_mb: 1024`, `max_storage_gb: 1.0`).
- Kích hoạt cơ chế **Sliding Window Eviction (30%)**: Khi vượt trần, tự động xóa 30% bản ghi cũ nhất và thu hồi dung lượng bằng `PRAGMA incremental_vacuum`, không gây khóa bảng SQLite hay nghẽn I/O.
- Tự động nén Gzip AGZ1 cho các khối thinking $\ge 384$ ký tự trong `thinking_store.db`.

## 2. Thay đổi đã áp dụng
Trong `/home/vvc/.antigravity_tools/gui_config.json`:
```json
{
  "proxy": {
    "log_retention": {
      "max_rows": 100000,
      "max_disk_mb": 1024,
      "max_storage_gb": 1.0,
      "max_body_age_hours": 24,
      "max_age_days": 30
    }
  }
}
```

## 3. Nghiệm thu
- Cấu hình nằm đúng schema trong object `proxy`.
- Service khởi động ghi nhận cấu hình log retention và nén thinking store.
