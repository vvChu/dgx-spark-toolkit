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

## 5. Bảo toàn Số hiệu Văn bản Pháp lý khi Tách Namespace
- **Quy tắc**: Số hiệu văn bản pháp luật Việt Nam (như `01/2024/TT-BXD`, `100/2025/QD-TTg`) chứa nhiều dấu gạch chéo `/`. Khi phân tách namespace từ `doc_id` dạng `VBPL/01/2024/TT-BXD`, **bắt buộc** dùng `split('/', 1)` để tách tiền tố namespace, tuyệt đối không dùng `split('/')[-1]` vì sẽ cắt cụt số hiệu thành `TT-BXD`.
- **Chi tiết**: Đảm bảo bộ lọc metadata trên Milvus/Neo4j và truy vấn tìm kiếm pháp lý giữ nguyên số hiệu gốc.

## 6. Chuẩn hóa Document Identity & Sparse Vector khi Insert Vector DB
- **Quy tắc**: Khi truyền chunks vào `MilvusRepository.insert_chunks()`, luôn chuẩn hóa và gán bù các trường danh tính (`doc_id`, `doc_number`, `file_hash`, `source`, `doc_type`, `authority`) nếu chunk dict mang giá trị rỗng `""` (`if not cdict.get("doc_id"): cdict["doc_id"] = doc_id`), đồng thời bảo toàn trường `sparse_vector` để không làm mất năng lực Hybrid Search (BM25 / Splade).
- **Chi tiết**: Tránh việc insert các chunk mồ côi không có `doc_id`/`doc_number`, gây lỗi cascading khi filter, hybrid search hoặc cascade delete.

## 7. Test Adapter Hermetic & Không Eager Initialize Mạng
- **Quy tắc**: Các in-memory test adapters (`InMemorySearchPipeline`, `InMemoryDocumentStore`, `MockAIGatewayClient`) tuyệt đối KHÔNG tự động eager-initialize các network HTTP clients (`get_ai_gateway_client()`) trong `__init__`.
- **Chi tiết**: Đảm bảo unit test chạy hoàn toàn độc lập (hermetic), offline 100%, không rò rỉ socket hoặc tạo side-effects mạng.


