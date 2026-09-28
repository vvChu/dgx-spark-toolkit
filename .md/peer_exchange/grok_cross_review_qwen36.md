# Báo Cáo Phản Biện Chéo Độc Lập — Grok 4.7 Thẩm Định Tối Ưu Hóa Qwen 3.6

**Thời điểm**: 2026-09-28 16:27 ICT  
**Thực hiện**: Grok 4.7 (Auditor & Peer Reviewer)  
**Đối tượng**: Đề xuất 3 tinh chỉnh tối ưu hóa khai thác mô hình `Qwen/Qwen3.6-35B-A3B-FP8` trên DGX Spark.  
**Tài liệu đối soát**: `.md/peer_exchange/prompt_grok_review.md`, mã nguồn `services/rag-service/`, cấu hình `litellm_config.yaml`, `docker-compose.yml`.

---

## Phán Quyết: CHẤP THUẬN CÓ ĐIỀU KIỆN (Approve with modifications)

Hướng đi tối ưu hóa là hoàn toàn chính xác: Qwen 3.6 mặc định bật thinking, và các call site JSON chạy ngân sách token nhỏ sẽ mất `content`. Tuy nhiên, 3 tinh chỉnh nếu viết đúng như đề xuất ban đầu thì chưa nên merge. Các điều kiện bên dưới là điều kiện bắt buộc để bảo đảm tính ổn định production.

---

## 1. Phản biện Tinh chỉnh 1: Hai Alias `instruct` / `coder` trên LiteLLM
- **Tách theo vai trò trường tồn (Role-based), không gắn version**:
  - Không đặt tên `qwen-3.6-35b-instruct` và `qwen-3.6-35b-coder`. Việc gắn số phiên bản vào alias sẽ lặp lại sai lầm của `qwen-3.5-35b` (khi nâng cấp checkpoint mới thì tên bị sai lệch).
  - Khuyến nghị đổi tên thành: **`local-instruct`** và **`local-coder`**, cùng trỏ về backend `qwen-local-primary`, `api_base: os.environ/GATEWAY_LOCAL_URL`.
- **Cấu hình tham số sampling chuẩn**:
  - `local-instruct`: `extra_body: {chat_template_kwargs: {enable_thinking: false}, top_k: 20}`, `temperature: 0.7`, `top_p: 0.8`, `presence_penalty: 1.5`, `repetition_penalty: 1.0` (theo đúng model card của Qwen).
  - `local-coder`: Thinking để default bật, `temperature: 0.6`, `presence_penalty: 0.0`. `preserve_thinking` giữ mặc định tắt.
  - Phải gán cùng hạn mức `rpm: 600, tpm: 10000000` như primary.

## 2. Phản biện Tinh chỉnh 2: Open WebUI
- Trạng thái hiện tại: `docker-compose.yml` đang đặt `DEFAULT_MODELS=qwen-local-primary` và `TASK_MODEL=qwen-local-primary`.
- Khuyến nghị: Đặt `TASK_MODEL=local-instruct` để Open WebUI tự động dùng chế độ non-thinking cho title generation, tag, autocomplete mà không bị chậm trễ suy luận.

## 3. Phản biện Tinh chỉnh 3: RAG Service & JSON Extraction
- **Cơ chế Deep-Merge bắt buộc**:
  ```python
  ctk = dict((extra_body or {}).get("chat_template_kwargs") or {})
  if "enable_thinking" not in ctk:
      ctk["enable_thinking"] = False
  ```
  Nếu caller đã chủ động truyền `enable_thinking: true` thì phải giữ nguyên.
- **BÁC BỎ HOÀN TOÀN việc tự động Fallback sang Thinking**:
  - `compliance_service._extract_compliance_keywords()` dùng `max_tokens=100`. Thinking tốn 300-1000 tokens sẽ làm `content=None`. Fallback thinking sẽ chỉ thất bại lặp lại!
  - `search_pipeline.py` agentic plan và eval có timeout 3s và 4s. Thinking tốn 5.6s sẽ gây timeout 100%!
  - `LegalMetadata` chỉ là nhận dạng trường, không phải suy luận đa bước.
  - Call site duy nhất cần suy luận pháp lý là `_generate_compliance_report()`. Caller ở vị trí này sẽ tự opt-in: truyền `enable_thinking=True`, `max_tokens >= 4096`, `timeout >= 30s`.
- **Phát hiện điểm mù HyDE**:
  - `retrieval/hyde.py` gọi `complete()` với `max_tokens=512`, KHÔNG tắt thinking! Cần tắt thinking cho HyDE để tránh bị cạn token sinh giả định tìm kiếm.
- **Sửa Heuristic "35b"**:
  - Trong `stream()` và `chat_service._generate_answer()`, điều kiện `if "35b" in target_model.lower()` sẽ vô tình kích hoạt lại thinking cho cả các alias instruct nếu tên có chữ `35b`. Cần chuyển sang kiểm tra theo danh sách vai trò rõ ràng.

## 4. Phản biện về Hermes Agent & vLLM Parsers
- Giữ Hermes trên `qwen-local-primary` hoặc `local-coder`.
- **Tuyệt đối KHÔNG trỏ Hermes vào `rag-core`**: vì entry `rag-core` trong LiteLLM có `tool_call_parser: openai` tạo thành lớp parser kép (double-parsing) đè lên vLLM.
- `preserve_thinking` giữ mặc định TẮT cho Hermes vì transcript dài kết hợp `presence_penalty=0.0` sẽ kích hoạt lỗi lặp suy luận (Discussion #9).
