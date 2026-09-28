# Báo Cáo Phản Biện Chéo Độc Lập — Grok 4.7 Thẩm Định Kế Hoạch Issue #77

**Thời điểm**: 2026-09-28 22:26 ICT  
**Thực hiện**: Grok 4.7 (Auditor & Peer Reviewer)  
**Đối tượng**: Kế hoạch triển khai Issue #77 (Tiến hóa `ccba-llm-pipeline-patterns` và `vllm-manager` cho reasoning models)  
**Tài liệu đối soát**: `.md/peer_exchange/prompt_grok_review_issue_77.md`, runtime vLLM :8004, LiteLLM :8090, Redis DB 0, `docker-compose.yml`, `.env`.

---

## Phán Quyết Của Grok: CHẤP THUẬN CÓ ĐIỀU KIỆN (CONDITIONAL ACCEPT)

> *"Hướng Pattern 16 và cặp parser `qwen3` + `qwen3_coder` khớp sự cố thật và khớp vLLM 0.26.0 đang chạy. Bản kế hoạch, và hai file nháp đã nằm trong working tree, chưa được phép merge: chúng ghi sai lệnh khởi động, sai tên metric, sai cơ chế `tool_call_parser`, và lập một nguồn chân lý thứ hai."*

### Bảng Điểm Đánh Giá (Adversarial Scorecard)

| Tiêu chí | Điểm | Nhận định của Grok |
|---|:---:|---|
| **Vững chắc kỹ thuật (Technical Robustness)** | **5/10** | Chẩn đoán starvation và cặp parser là đúng trên host này. Lệnh launch, metric Prometheus, và cảnh báo double-parser trong skill nháp thì sai. |
| **Tiện dụng vận hành (Operational Usability)** | **6/10** | `local-instruct` và mount cache đã chạy và có ích. Skill viết lại một recipe mà agent có thể đem đi thu nhỏ context. |
| **Tuân thủ KISS (KISS Compliance)** | **3/10** | Hai bài doctrine, một dòng catalog không tồn tại, một file `audit-skills.md` không có trong repo, cổng kiểm không phải lệnh chuẩn. |
| **Rủi ro hồi quy (Regression Risk)** | **7/10** | Cao nếu agent làm theo snippet trong `ccba-vllm-manager`. Cache gateway còn phục vụ lại response đã bị starvation. |

---

## 1. Dữ Liệu Đối Soát Trực Tiếp Trên Host DGX Spark (Audited Runtime Facts)

Container `qwen36b` đang chạy `vllm/vllm-openai:latest`, vLLM **0.26.0**, process chạy quyền `root`. Model vật lý là `/home/vvc/models/Qwen3.6-35B-A3B-FP8` mount vào `/models/model`. `.env` đặt `LOCAL_PRIMARY_GPU_UTIL=0.60` và `LOCAL_PRIMARY_MAX_MODEL_LEN=98304`. Cổng 8003 chạy `cyankiwi/Qwen3.5-9B-AWQ-4bit` (không phải Qwen2.5-Coder-7B).

### Volume Cache & Quyền Sở Hữu (UIDs)
- Mount `/home/vvc/.cache/vllm` $\to$ `/root/.cache/vllm` đúng thư mục vLLM 0.26 ghi (`torch_compile_cache`, `flashinfer_autotune_cache`, `modelinfos`).
- Xung đột quyền: Container process là `root`, các thư mục cache con do container tạo mang quyền `root:root` mode `755`. User `vvc` (UID 1000) không xóa được file bên trong nếu không dùng `sudo`.
- **CẤM** hướng dẫn `chmod 777`. Khi nâng cấp digest image vLLM, phải di chuyển thư mục cache cũ sang backup.

### Dual Parser & Stream SSE
- vLLM 0.26.0 bắt buộc phải có cờ `--enable-auto-tool-choice` đi kèm `--tool-call-parser qwen3_coder` thì mới chấp nhận request có `tools`.
- Cùng một stream SSE có thể mang `delta.reasoning` rồi mới tới `delta.tool_calls`. Nếu thinking đốt hết `max_tokens` $\to$ `finish_reason=length`, cả content lẫn tool calls đều bị nuốt chửng (starvation).

### Về `tool_call_parser: openai` trên LiteLLM
- Không phải "double parser gây xung đột schema". LiteLLM 1.83.3 không có trường này trong `LiteLLM_Params`, đẩy nó vào `extra_body`. vLLM 0.26 cũng bỏ qua trường này.
- Đây là **cấu hình chết (dead config)** trên `rag-core`. Cần dọn dẹp để vệ sinh tương thích (tránh rủi ro khi vLLM bản sau đổi sang `extra: forbid`), chứ không phải vì xung đột schema.

### Về Truyền Tham Số Thinking Qua Gateway & Rủi Ro Redis Cache
- Các hình thái gửi `chat_template_kwargs: {"enable_thinking": False}` (kể cả alias `local-instruct` hay OpenAI SDK qua extra_body) đều đi xuyên LiteLLM tới vLLM thành công.
- **Rủi ro lớn**: LiteLLM Redis Cache (DB 0, TTL 3600) **KHÔNG** đưa `chat_template_kwargs` vào hash key cache. Nếu một prompt trước đó vừa bị starvation dưới thinking bật, lần gọi sau dù đổi sang `enable_thinking: False` vẫn có thể dính lại cached response rỗng trong 3600 giây! Cần gửi kèm `caching: false` hoặc cơ chế cache-bust khi retry.

### Tên Prometheus Metrics Chuẩn của vLLM 0.26
- `vllm:num_requests_running`: Còn tồn tại.
- `vllm:gpu_cache_usage_perc`: **Đã bị xóa**. Thay bằng `vllm:kv_cache_usage_perc` (thang 0.0 - 1.0, ngưỡng cảnh báo `0.95`).
- `vllm:avg_generation_throughput_toks_per_s`: **Đã bị xóa**. Thay bằng counter `vllm:generation_tokens_total`.

---

## 2. Bảy Điều Kiện Bắt Buộc (7 Actionable Mandates) Của Grok

1. **Sửa nháp `ccba-vllm-manager/SKILL.md`**:
   - Xóa lệnh `docker run` tự tạo. Ghi rõ tham số sống nằm ở `docker-compose.yml` service `vllm-36b` và `.env` (`LOCAL_PRIMARY_*`).
   - Bổ sung `--enable-auto-tool-choice` đi kèm `--reasoning-parser qwen3` và `--tool-call-parser qwen3_coder`.
   - Sửa model cổng 8003 thành `cyankiwi/Qwen3.5-9B-AWQ-4bit`.
   - Đổi tên metric sang `vllm:kv_cache_usage_perc` (ngưỡng `0.95`) và `vllm:generation_tokens_total`.
2. **Ghi nhận quyền cache chính xác**:
   - Process container chạy dưới `root`, cây cache con là `root:root 755`. User `vvc` dọn bằng `sudo`, tuyệt đối không `chmod 777`.
   - Lưu ý khi đổi image digest vLLM: lưu cache cũ sang backup.
3. **Hiệu chỉnh tài liệu về LiteLLM**:
   - Mô tả chính xác: `tool_call_parser: openai` là dead config trên `rag-core`, cần dọn dẹp để phòng ngừa `extra: forbid` trong tương lai, không phải vì lỗi schema méo mó.
4. **Chuẩn hóa Pattern 16 trong `ccba-llm-pipeline-patterns`**:
   - Trỏ tới code thực tế: `ai_gateway_client.extract_json`, `retrieval/hyde.py`, alias `local-instruct`.
   - Hợp đồng dựa trên loại tác vụ (JSON, HyDE, titling, tagging, OCR), không dựa vào ngưỡng token số học `512`.
   - Fallback một lần, có cờ chống lặp vô hạn, kèm `caching: false` để chống trúng response starvation cũ từ Redis cache.
5. **Cấu trúc lại `vllm-manager/SKILL.md` theo KISS**:
   - Biến `vllm-manager/SKILL.md` thành một pointer ngắn gọn trỏ sang `ccba-vllm-manager`, dẫn hướng tới các scripts cục bộ `./scripts`.
   - Không nhân bản tài liệu (Single Source of Truth), không tạo symlink cả thư mục làm bẩn Hub.
6. **Đăng ký chuẩn hóa**:
   - Kiểm định bằng `.venv/bin/python -m ccba_harness verify-patch --preset skill` hoặc `validate_skills.py --enforce-gpi`.
   - Chạy `compile_catalog.py` để đăng ký chính thức vào `catalog.yaml`.
7. **Đồng bộ mã nguồn `chat_service.py`**:
   - Sửa `_generate_answer()` để thống nhất hợp đồng với `stream()`: thinking chỉ bật khi model thuộc `rag-core`, `local-coder`, `qwen-local-primary`; tên chứa `instruct` giữ thinking tắt.
