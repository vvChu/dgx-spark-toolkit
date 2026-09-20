# Ticket [TICK-03]: Tối ưu Thinking Budget & Nén Ngữ Cảnh Đa Tầng (L1-L3)

**Bản đồ cha:** [Bản đồ Định hướng Tối ưu Antigravity Tools](../map.md)  
**Phân loại:** `Task [AFK]`  
**Trạng thái:** `Completed (Done)`  
**Assignee:** Antigravity Agent  
**Ngày hoàn tất:** 20/09/2026  

---

## 1. Mục tiêu đã hoàn thành
- Chuyển `thinking_budget.control_source` sang `"gateway"`:
  - Áp đặt trần ngân sách tư duy an toàn: Flash High: `16,384`, Pro High: `10,001`, Claude Thinking: `16,384`.
  - Triệt tiêu lỗi client gửi budget $< 2048$ (ngân sách độc 1000) làm tắt luồng suy luận.
- **Quyết định sau thẩm định (Adversarial Review)**:
  - **TỪ CHỐI L2/L3 (Caveman)** vì làm biến dạng text cũ, phá hủy hoàn toàn Prompt Caching (Cache Hit tụt về 0%).
  - Thiết lập `compression_level: "low"` để duy trì tầng **L1 (RTK Denoising)**: lọc sạch mã màu ANSI và tiến trình tải rác trong tool output mà không làm vỡ prefix cache.
- **Bảo vệ Heuristics v4.7.8**: Không map `gemini-3.8-flash-high` trong `custom_mapping` để giữ nguyên hậu tố `-high`, tránh bị hạ cấp về Medium/Low.

## 2. Thay đổi đã áp dụng
Trong `/home/vvc/.antigravity_tools/gui_config.json`:
```json
{
  "proxy": {
    "thinking_budget": {
      "control_source": "gateway",
      "flash_mode": "custom",
      "pro_mode": "custom",
      "claude_mode": "custom"
    },
    "experimental": {
      "compression_level": "low"
    }
  }
}
```

## 3. Nghiệm thu
- Log khởi động: `[Thinking-Budget] Global config initialized: source=Gateway, flash_mode=Custom...`
- Kiểm tra E2E: `gemini-3.8-flash-high` phản hồi kèm thinking blocks đầy đủ (duration ~13.4s).
