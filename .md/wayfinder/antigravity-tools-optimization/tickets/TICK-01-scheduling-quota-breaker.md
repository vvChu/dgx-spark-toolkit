# Ticket [TICK-01]: Cấu hình Scheduling Mode Balance & Quota Breaker

**Bản đồ cha:** [Bản đồ Định hướng Tối ưu Antigravity Tools](../map.md)  
**Phân loại:** `Task [AFK]`  
**Trạng thái:** `Completed (Done)`  
**Assignee:** Antigravity Agent  
**Ngày hoàn tất:** 20/09/2026  

---

## 1. Mục tiêu đã hoàn thành
- Chuyển đổi thành công `proxy.scheduling.mode` sang `"Balance"`:
  - Khóa phiên theo session SHA-256 để tối đa hóa Prompt Caching (KV Cache) trên Google.
  - Tự động kích hoạt P2C (Power of Two Choices) và Fast Failover 50ms khi gặp lỗi 429.
- Bật `circuit_breaker.lock_on_zero_quota = true` tại root schema chuẩn để khóa tài khoản cạn kiệt đến đúng mốc `reset_time` chính thức từ Google.

## 2. Thay đổi đã áp dụng
Trong `/home/vvc/.antigravity_tools/gui_config.json`:
```json
{
  "circuit_breaker": {
    "enabled": true,
    "backoff_steps": [60, 300, 1800, 7200],
    "lock_on_zero_quota": true
  },
  "proxy": {
    "scheduling": {
      "mode": "Balance",
      "max_wait_seconds": 60
    }
  }
}
```

## 3. Nghiệm thu
- File JSON hợp lệ, parsed thành công.
- Dịch vụ khởi động nạp đúng 7 tài khoản ở chế độ Balance.
