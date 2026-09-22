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
- **Quy tắc**: Số hiệu văn bản pháp luật Việt Nam (như `01/2024/TT-BXD`, `100/2025/QD-TTg`) chứa nhiều dấu gạch chéo `/` và thường bắt đầu bằng chữ số. Khi phân tách namespace từ `doc_id` dạng `VBPL/01/2024/TT-BXD`, **chỉ tách tiền tố namespace khi tiền tố đó là chuỗi phi số (non-numeric string như `VBPL`, `TCVN`, `QCVN`)**. Nếu chuỗi đầu vào bắt đầu bằng chữ số (ví dụ `01/2024/TT-BXD`), phải giữ nguyên toàn bộ chuỗi làm số hiệu, tuyệt đối không cắt bỏ phần tử đầu tiên làm mất số thứ tự văn bản.
- **Chi tiết**: Đảm bảo bộ lọc metadata trên Milvus/Neo4j và truy vấn tìm kiếm pháp lý giữ nguyên số hiệu gốc chính xác 100%.

## 6. Chuẩn hóa Document Identity & Sparse Vector khi Insert Vector DB
- **Quy tắc**: Khi truyền chunks vào `MilvusRepository.insert_chunks()`, luôn chuẩn hóa và gán bù các trường danh tính (`doc_id`, `doc_number`, `file_hash`, `source`, `doc_type`, `authority`) nếu chunk dict mang giá trị rỗng `""` (`if not cdict.get("doc_id"): cdict["doc_id"] = doc_id`), đồng thời bảo toàn trường `sparse_vector` để không làm mất năng lực Hybrid Search (BM25 / Splade).
- **Chi tiết**: Tránh việc insert các chunk mồ côi không có `doc_id`/`doc_number`, gây lỗi cascading khi filter, hybrid search hoặc cascade delete.

## 7. Test Adapter Hermetic & Không Eager Initialize Mạng
- **Quy tắc**: Các in-memory test adapters (`InMemorySearchPipeline`, `InMemoryDocumentStore`, `MockAIGatewayClient`) tuyệt đối KHÔNG tự động eager-initialize các network HTTP clients (`get_ai_gateway_client()`) trong `__init__`.
- **Chi tiết**: Đảm bảo unit test chạy hoàn toàn độc lập (hermetic), offline 100%, không rò rỉ socket hoặc tạo side-effects mạng.

## 8. Kiểm tra Năng lực Thực thi Rõ ràng trong Graph Seams
- **Quy tắc**: Các phương thức thao tác đồ thị (như `DocumentStore.add_relation()`) phải có biến cờ `executed` để kiểm tra phương thức tương ứng trên repository có thực sự tồn tại và chạy thành công không. Nếu repository không hỗ trợ loại quan hệ đó, PHẢI trả về status lỗi rõ ràng (`unsupported_relation`), tuyệt đối không trả về `{"status": "success"}` giả mạo.
- **Chi tiết**: Ngăn ngừa việc tầng trên tưởng nhầm cạnh đồ thị đã được tạo trong khi thực tế không có thao tác nào được thực hiện.

## 9. Dọn dẹp Toàn diện Thư mục Tạm khi Chuyển đổi Định dạng
- **Quy tắc**: Khi chuyển đổi tài liệu qua subprocess (như LibreOffice headless chuyển `.doc` sang `.docx` trong thư mục tạm `mkdtemp`), khối `finally` không chỉ xóa file tạm đơn lẻ mà PHẢI dọn dẹp sạch sẽ toàn bộ thư mục cha tạm thời (`shutil.rmtree(parent_dir, ignore_errors=True)`).
- **Chi tiết**: Ngăn chặn rò rỉ dung lượng ổ đĩa (disk space leak) trong các worker tiến trình ingestion chạy liên tục trong thời gian dài.

## 10. Nguyên tắc Strict Yielding & Reactive Wakeup cho Background Tasks
- **Quy tắc**: Tuyệt đối **CẤM** gọi `manage_task(status)` theo vòng lặp (busy-polling) khi một lệnh được đẩy xuống chạy nền (`task-xxx`). Khi nhận thông báo `Tool is running as a background task`, Agent **PHẢI** lập tức dừng gọi công cụ (end turn) và xuất thông điệp ngắn cho người dùng.
- **Chi tiết**: Antigravity runtime là kiến trúc Reactive Event-Driven. Khi task nền chạy xong, runtime sẽ tự động phát `<SYSTEM_MESSAGE>` và resume lượt của Agent kèm toàn bộ output và exit code. Việc gọi loop poll `manage_task(status)` làm lãng phí hàng chục nghìn tokens, gây tắc nghẽn UI và tăng chi phí API không cần thiết.

## 11. Chuẩn hóa Định tuyến Centralized Proxy (Antigravity-Manager) qua Giao thức OpenAI
- **Quy tắc**: Mọi model định tuyến qua Centralized Proxy (`GATEWAY_PROXY_URL=http://<host>:8045/v1`) trong `litellm_config.yaml` hoặc client SDK **BẮT BUỘC** sử dụng prefix `openai/` (ví dụ `openai/claude-opus-4-6-thinking`, `openai/claude-sonnet-4-6`), tuyệt đối **CẤM** dùng prefix `anthropic/`.
- **Chi tiết**: Khi dùng `anthropic/`, SDK/LiteLLM tự động nối thêm `/v1/messages` vào `api_base`, sinh ra đường dẫn sai `...:8045/v1/v1/messages` gây lỗi `HTTP 404 Not Found (0ms)`. Antigravity-Manager tương thích hoàn toàn giao thức OpenAI (`POST /v1/chat/completions`), tự động xử lý thinking blocks, tool calls và cơ chế bảo vệ quota Ultra internally.

## 12. Kiểm tra Trạng thái Liveness cho LiteLLM Proxy Container
- **Quy tắc**: Khi kiểm tra trạng thái sống (liveness/health) của container LiteLLM Proxy (`:8090`), **BẮT BUỘC** dùng endpoint `GET /health/liveliness` (hoặc `GET /health/readiness`), tuyệt đối **CẤM** dùng `GET /health`.
- **Chi tiết**: Endpoint `GET /health` của LiteLLM mặc định kích hoạt kiểm tra đồng thời tất cả các model deployment backend (hơn 100 models), gây độ trễ hàng phút hoặc timeout. Khi proxy bật bảo mật master key, request phải kèm header `Authorization: Bearer $LITELLM_MASTER_KEY` (lấy từ `.env` gốc).

## 13. Chốt Chặn So Khớp Phiên Bản Động Trước Khi Gợi Ý Nâng Cấp (Dynamic Version Gate)
- **Quy tắc**: Khi thiết kế các công cụ tự động hóa, ChatOps, hoặc CLI có tính năng nâng cấp dịch vụ/container (như Open WebUI, vLLM, RAG), **BẮT BUỘC** thực hiện so khớp phiên bản ngữ nghĩa (`packaging.version.parse`) giữa phiên bản đang chạy (`current_version`) và phiên bản upstream mới nhất (`latest_version`).
- **Chi tiết**: Chỉ hiển thị menu hoặc nút xác nhận nâng cấp khi `latest_version > current_version`. Nếu `current == latest`, phải hiển thị thông báo dịch vụ đã ở bản mới nhất kèm tùy chọn cứu hộ/cài đặt lại (`reinstall`), tuyệt đối KHÔNG hiển thị hộp thoại nâng cấp lên chính phiên bản đang chạy gây thao tác thừa. Trường hợp không truy vấn được upstream (mất mạng/rate-limit), phải thông báo rõ trạng thái `unknown` và yêu cầu người dùng chỉ định rõ phiên bản qua tham số CLI thay vì tự động đoán định.

## 14. Bảo Toàn Chuỗi Băm Audit Trail & Cô Lập Kiểm Thử (Audit Chain Continuity & Test Isolation)
- **Quy tắc**: Khi ứng dụng cơ chế nhật ký kiểm toán băm nối tiếp (Chained SHA-256) cho các daemon vận hành dài hạn, lúc khởi động daemon **BẮT BUỘC** nạp lại mã băm bản ghi hợp lệ cuối cùng từ tệp disk (`load_last_audit_hash`), tuyệt đối không khởi tạo lại `prev_hash = "0"*64` làm đứt gãy tính liên tục của chuỗi kiểm toán (Audit Chain Fork).
- **Chi tiết**: Khi viết unit test, các test kiểm tra luồng nghiệp vụ khác của daemon phải mock hàm ghi đĩa (`patch("scripts.chatops_daemon.append_audit_log")`) để không làm ô nhiễm log production và không gây lệch hash in-memory; riêng các test kiểm tra chính tính năng băm nối tiếp và khôi phục chuỗi kiểm toán **BẮT BUỘC** chuyển hướng đường dẫn `AUDIT_FILE` sang tệp tạm thời cô lập (`tmp_path / "audit.jsonl"`).

## 15. Sao Lưu An Toàn Chuẩn WAL & Rollback Xác Định Cho SQLite Container (WAL-Safe Backup & Alpine Rollback)
- **Quy tắc**: Khi sao lưu hoặc nâng cấp các container chạy SQLite ở chế độ Write-Ahead Logging (WAL) như Open WebUI, tuyệt đối không sao chép tệp `webui.db` thô khi dịch vụ đang chạy. Bắt buộc kích hoạt API sao lưu trực tuyến (`sqlite3.backup()`) bên trong container đang chạy để gom sạch các giao dịch từ `-wal` và `-shm` vào tệp snapshot đồng nhất trước khi nén tarball (bao gồm cả thư mục `vector_db` và `uploads`).
- **Chi tiết**: Quy trình rollback khẩn cấp khi container phiên bản mới gặp sự cố migration hoặc timeout healthcheck phải dùng container phụ trợ độc lập (như `alpine:latest`) mount trực tiếp volume dữ liệu để giải nén snapshot và **bắt buộc xóa sạch các tệp lock `-wal`, `-shm` cũ** trước khi khởi động lại container phiên bản trước đó.

## 16. Triệt Tiêu Tiến Trình Zombie & Bảo Vệ Process Group Khi Ngắt Subprocess
- **Quy tắc**: Trong các daemon điều phối bất đồng bộ (`asyncio`), mọi subprocess chạy ngầm qua `asyncio.create_subprocess_shell` hoặc `asyncio.create_subprocess_exec` **BẮT BUỘC** phải được khởi tạo với cờ `start_new_session=True` để tạo process group độc lập. Khi xử lý ngoại lệ Timeout hoặc Cancelled, sau khi gửi tín hiệu `signal.SIGKILL` tới process group (`os.killpg(os.getpgid(proc.pid), signal.SIGKILL)`), **BẮT BUỘC** phải bọc `await asyncio.wait_for(proc.wait(), timeout=3.0)`.
- **Chi tiết**: Cờ `start_new_session=True` ngăn ngừa việc `os.killpg` tiêu diệt nhầm chính daemon cha hoặc test runner. Lệnh bọc `proc.wait()` có timeout giải phóng tiến trình con khỏi trạng thái `<defunct>` (zombie) trong bảng tiến trình Linux mà không làm treo vòng lặp sự kiện nếu tiến trình bị kẹt trong trạng thái D-state (Uninterruptible Sleep).

## 17. Truy Vấn Bộ Nhớ GPU Trên Kiến Trúc NVIDIA GB10 Blackwell Unified Memory
- **Quy tắc**: Trên kiến trúc bộ nhớ hợp nhất (Unified Memory) như NVIDIA Grace Blackwell GB10 (128GB LPDDR5X), lệnh truy vấn `nvidia-smi --query-gpu=memory.total,memory.used` trả về `[N/A]`. Các script giám sát, watchdog hoặc daemon chẩn đoán hệ thống tuyệt đối không dựa vào `query-gpu` để tính toán tỷ lệ tiêu thụ VRAM.
- **Chi tiết**: Bắt buộc truy vấn qua `nvidia-smi --query-compute-apps=process_name,used_memory --format=csv,noheader`, bóc tách dung lượng của từng tiến trình tính toán (như `VLLM::EngineCore`, `speaches`), tính tổng sử dụng thực tế và gán nhãn tường minh `X GiB / 128.0 GiB (Unified Memory)`.

