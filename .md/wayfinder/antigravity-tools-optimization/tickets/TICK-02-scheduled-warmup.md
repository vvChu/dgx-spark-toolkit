# Ticket [TICK-02]: Kích hoạt 7-Day Smart Warmup Scheduler

**Bản đồ cha:** [Bản đồ Định hướng Tối ưu Antigravity Tools](../map.md)  
**Phân loại:** `Task [AFK]`  
**Trạng thái:** `Completed (Done)`  
**Assignee:** Antigravity Agent  
**Ngày hoàn tất:** 20/09/2026  

---

## 1. Mục tiêu đã hoàn thành
- Kích hoạt thành công `scheduled_warmup.enabled = true`.
- Khởi chạy luồng theo dõi mốc reset tuần, tự động gửi 1 probe cực tiểu ngay khi bước sang chu kỳ mới để kích hoạt đồng hồ quota tuần của Google.

## 2. Thay đổi đã áp dụng
Trong `/home/vvc/.antigravity_tools/gui_config.json`:
```json
{
  "scheduled_warmup": {
    "enabled": true,
    "monitored_models": [
      "gemini-3-flash",
      "claude",
      "gemini-3-pro-high",
      "gemini-3-pro-image"
    ]
  }
}
```

## 3. Nghiệm thu
- Log khởi động của `antigravity-tools.service` xác nhận:
  `[Scheduler] Weekly Reset Warmup Scheduler started. Monitoring 7-day quota windows...`
