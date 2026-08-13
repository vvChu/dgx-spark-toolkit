# 🛡️ Codebase Engineering Rules — Learned Best Practices

Tài liệu lưu trữ các quy tắc kỹ thuật cố định được rút ra từ quá trình kiểm chứng thực tế và code review. Tất cả Agent làm việc trên repo này **BẮT BUỘC** tuân thủ:

---

## 1. Giao thức SSE Token Streaming
- **Quy tắc**: Event `data: [DONE]\n\n` LUÔN LUÔN phải là event cuối cùng được phát ra trong luồng SSE streaming (`chat_service.py` / `chat_stream.py`).
- **Chi tiết**: Mọi event metadata phụ (`trace`, `usage`, `sources`, `metrics`) phải được phát ra TRƯỚC `[DONE]`. Frontend & API Proxy lập tức ngắt kết nối HTTP khi gặp `[DONE]`, khiến dữ liệu gửi sau `[DONE]` bị gián đoạn.

## 2. Thread Safety cho Metric & State Counters
- **Quy tắc**: Khi một class sử dụng `self._lock = threading.Lock()` để bảo vệ state (`_hits`, `_misses`, `_timestamps`), MỌI biến đếm metric (kể cả L2 Cache Hit hay Fallback path) phải được đặt trong khối `with self._lock:`.
- **Chi tiết**: Tránh triệt để Race Condition trong môi trường web server chạy đa luồng đồng thời.

## 3. Kiểm tra Hợp lệ Nguyên tử cho Message Queue Payload
- **Quy tắc**: Khi nhận item từ queue (`msg = queue.claim_next()`), luôn phải kiểm tra điều kiện nguyên tử `if msg_id and file_path:` trước khi đưa vào luồng `safe_process()`, `acknowledge()`, hay `nack()`.
- **Chi tiết**: Ngăn ngừa tin nhắn không hợp lệ (corrupted/null payload) gây ra ngoại lệ dây chuyền (cascading failures).

## 4. An Toàn API Key & Tránh Hardcode Master Key
- **Quy tắc**: Tuyệt đối KHÔNG hardcode API Key / Master Key dự phòng (fallback strings như `sk-spark-...`) trong scripts verifier hay playbook markdown.
- **Chi tiết**: Mọi script phải yêu cầu biến môi trường `$LITELLM_MASTER_KEY` từ hệ thống hoặc file `.env`, đồng thời báo lỗi / ngắt an toàn thay vì dùng giá trị bí mật mặc định.

