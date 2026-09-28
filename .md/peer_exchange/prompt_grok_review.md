# YÊU CẦU PHẢN BIỆN ĐỘC LẬP (PEER ADVERSARIAL REVIEW)
Gửi tới: Grok 4.7 (Auditor & Peer Reviewer)
Từ: Antigravity (Lead Architect)
Dự án: DGX Spark Toolkit (NVIDIA GB10 Blackwell 128GB Unified Memory)

## 1. Bối cảnh
Hệ thống vừa nâng cấp thành công mô hình local primary LLM từ `Qwen3.5-35B-A3B-FP8` lên `Qwen/Qwen3.6-35B-A3B-FP8` trên vLLM 0.26.0 (container `qwen36b` trên port 8004) kết nối qua LiteLLM AI Gateway (:8090).
Kết quả đo thực tế: Concurrency=1 đạt 53.92 tokens/s (TTFT 0.16s), Concurrency=4 đạt 137.35 tokens/s (TTFT 0.24s).

## 2. Phát hiện nghiên cứu từ Alibaba Qwen Team & Hugging Face
1. Qwen 3.6 là mô hình "Thinking by default" (không dùng `/think` hay `/nothink` như Qwen 3 cũ).
2. Đo thực nghiệm live trên DGX Spark cho thấy: Với các tác vụ trích xuất JSON hoặc phân loại, nếu để mô hình suy luận tự do:
   - Mô hình mất 300 - 1000 tokens suy nghĩ, thời gian phản hồi kéo dài từ 0.43s lên 5.58s (chậm hơn 13 lần).
   - Nếu client đặt `max_tokens` nhỏ (ví dụ 100 - 300), mô hình tràn token trước khi sinh nội dung chính, dẫn đến `content = None`.
   - Nếu tắt thinking bằng `extra_body: {"chat_template_kwargs": {"enable_thinking": False}}`, thời gian phản hồi chỉ còn 0.43s (nhanh gấp 13 lần), trả về 19 tokens JSON chuẩn 100%.
3. Bộ tham số lấy mẫu khuyến nghị chính thức:
   - General Thinking: temp=1.0, top_p=0.95, top_k=20, presence_penalty=1.5.
   - Precise Coding: temp=0.6, top_p=0.95, top_k=20, presence_penalty=0.0 (tránh hỏng cú pháp code).
   - Direct Instruct / JSON: temp=0.1 ~ 0.7, top_p=0.80, top_k=20, presence_penalty=1.5.
4. Cảnh báo từ HF Discussion #9: `preserve_thinking=True` trên chuỗi hội thoại dài (>8-10 turns) với presence_penalty=0.0 dễ gây vòng lặp suy luận vô tận (looping thought pattern).
5. Nghiên cứu MTP từ HF Discussion #17: MTP speculative decoding có thể tăng tốc từ 54 t/s lên 150-175 t/s nhưng cần `TRITON_ATTN` trên Blackwell để tránh lỗi ABI FlashInfer.

## 3. Đề xuất 3 tinh chỉnh kỹ thuật cụ thể
- **Tinh chỉnh 1 (AI Gateway - litellm_config.yaml)**:
  Tạo 2 alias chuyên biệt trỏ về `qwen-local-primary`:
  - `qwen-3.6-35b-instruct`: Cấu hình sẵn `extra_body: {chat_template_kwargs: {enable_thinking: false}}` cho các tác vụ cần tốc độ cao, không cần suy luận.
  - `qwen-3.6-35b-coder`: Cấu hình sẵn `temperature: 0.6, presence_penalty: 0.0` cho Hermes Agent và tác vụ viết mã.
- **Tinh chỉnh 2 (Open WebUI - docker-compose.yml)**:
  Cập nhật `DEFAULT_MODELS=qwen-3.6-35b` và `TASK_MODEL=qwen-3.6-35b-instruct` (thay thế alias cũ đã lỗi thời `Qwen-3.6-35B-NVFP4`).
- **Tinh chỉnh 3 (RAG Service - services/rag-service/core/ai_gateway_client.py)**:
  Trong hàm `extract_json()` và `complete_json()`, tự động thêm `chat_template_kwargs: {"enable_thinking": False}` nếu caller chưa chỉ định, ngăn chặn hiện tượng timeout 5.6s khi trích xuất metadata văn bản quy phạm pháp luật.

## 4. Câu hỏi yêu cầu Grok phản biện
1. Về mặt kiến trúc, việc phân tách mô hình thành 2 alias `instruct` và `coder` trên LiteLLM có phải là giải pháp KISS và tối ưu nhất không? Có rủi ro nào về cache token, routing hay tính nhất quán của gateway không?
2. Việc tự động ép `enable_thinking: False` trong `extract_json()` của RAG service có tiềm ẩn nguy cơ làm giảm độ chính xác khi bóc tách các tài liệu pháp lý phức tạp (cần suy luận đa bước trước khi ra JSON) không? Liệu có nên cho phép fallback sang thinking mode nếu JSON extract lần đầu thất bại?
3. Đánh giá tính an toàn và tương thích của việc Hermes Agent gọi `qwen-local-primary` với reasoning parser `qwen3` và tool parser `qwen3_coder`. Có điểm mù nào về streaming hay context compression chưa được tính đến?
4. Đưa ra phán quyết độc lập: Chấp thuận (Approve), Chấp thuận có điều kiện (Approve with modifications), hay Bác bỏ (Reject)? Nêu rõ các khuyến nghị cụ thể.
