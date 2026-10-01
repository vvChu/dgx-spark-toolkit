# Hướng Dẫn Nút Bấm Đổi Model Cho Grok Build CLI Qua Telegram ChatOps

Tài liệu này ghi nhận tính năng chuyển đổi model cho Grok Build CLI (`~/.grok/config.toml`) trực tiếp từ Telegram ChatOps Gateway.

---

## 1. Giới thiệu & Động lực
Khi sử dụng **Grok Build CLI**, tài khoản X Premium+ có hạn mức tuần (`Weekly limit`) cố định cho model `Grok 4.7 (xhigh)`. Khi hạn mức này cạn kiệt (0%), người dùng có thể chuyển sang các model khác như:
* **Qwen 35B Local**: Chạy 100% offline trên GPU NVIDIA Blackwell GB10 của server Spark (hoàn toàn miễn phí, không tốn quota).
* **Gemini 3.8 Flash High / Claude Sonnet 4.6 / Claude Opus 4.6**: Chạy qua AI Gateway nội bộ (:8090).
* **Grok 4.7 Fast / Grok 4.6 / Grok 4.5**: Các phiên bản tiết kiệm quota của xAI.

Để không phải chỉnh sửa file `~/.grok/config.toml` bằng tay trên server mỗi lần cần đổi model, tính năng điều khiển cảm ứng qua Telegram ChatOps đã được tích hợp.

---

## 2. Các điểm truy cập trên ChatOps

### A. Từ Menu Chính (`/menu` hoặc `/start`)
* Bấm nút **`⚡ Đổi Model Grok CLI (MỚI)`** trên bảng điều khiển Telegram.
* ChatOps sẽ mở ra Sub-Menu quản lý model cho Grok.

### B. Gọi lệnh trực tiếp
* `/grok` hoặc `/grok_model`: Mở ngay Sub-Menu đổi model Grok.
* `/set_grok_model <model_id>`: Đặt ngay model mặc định (ví dụ: `/set_grok_model qwen-local`).

---

## 3. Giao diện Sub-Menu Grok trên Telegram

### Danh sách Model hỗ trợ (2 nút / hàng):
1. **🟢 Qwen 35B Local (GPU)** (`qwen-local`): Offline trên Blackwell GB10, không tốn token/credit.
2. **⚡ Gemini 3.8 Flash** (`gemini-38-flash`): Cực nhanh, context 1M qua AI Gateway.
3. **🧠 Claude Sonnet 4.6** (`claude-sonnet-4-6`): SOTA coding qua AI Gateway.
4. **🚀 Claude Opus 4.6** (`claude-opus-4-6`): Kiến trúc chuyên sâu qua AI Gateway.
5. **⭐ Grok 4.7 (xAI)** (`grok-4.7`): Model frontier của xAI.
6. **🏎️ Grok 4.7 Fast** (`grok-4.7-build-fast`): Bản tăng tốc của Grok 4.7.
7. **🌪️ Grok 4.6 (xAI)** (`grok-4.6`): Bản ổn định.
8. **📦 Grok 4.5 (xAI)** (`grok-4.5`): Bản legacy.

* Model đang được kích hoạt sẽ tự động hiển thị dấu **`✅`** ngay trên nút bấm.
* Khi bấm nút, ChatOps cập nhật file `~/.grok/config.toml` nguyên tử (atomic), giữ nguyên mọi ghi chú và bảng cấu hình khác, đồng thời cập nhật tức thì giao diện Telegram mà không gửi thêm tin nhắn rác.

### Tùy chọn Mức suy luận (`Reasoning Effort`):
Bấm **`🎯 Mức Suy Luận (Effort)`** để tùy chọn:
* **🟢 Low**: Tiết kiệm token nhất.
* **🟡 Medium**: Cân bằng tốc độ và chất lượng.
* **🟠 High**: Suy luận sâu.
* **🔴 xHigh**: Mức suy luận tối đa.

---

## 4. Kiểm thử & Vận hành
* Tự động kiểm thử: `pytest tests/test_chatops.py` (67/67 tests passed).
* Dịch vụ vận hành: `systemd --user status dgx-chatops.service`.
* Nhật ký bảo mật: Mọi thao tác đổi model đều được ghi nhận vào `logs/chatops/audit.jsonl` với chuỗi hàm băm SHA-256 chống giả mạo.
