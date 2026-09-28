# Walkthrough — PR #81: Harden Qwen 3.6 Reasoning Model Profiles, Non-Thinking Fallback & Cache Isolation

> **PR:** [#81 feat(gateway): harden qwen3.6 reasoning model profiles and non-thinking fallback](https://github.com/vvChu/dgx-spark-toolkit/pull/81)  
> **Merged Commit:** `81b419f` $\rightarrow$ `master`  
> **Verification Status:** ✅ 100% PASS (527/527 Tests Passed, 0 Flake8 Errors, Dual-Gate CI 4/4 Green, Live Gateway 5/5 Scenarios Pass)  
> **Peer Review Verdict:** 🛡️ FINAL APPROVE (Grok 4.7 Host-Direct Audit)  
> **Production Status:** 🟢 RELEASED & MERGED TO MASTER

---

## 1. Tổng Quan Kết Quả Phát Hành (Release Summary)

Gói phát hành PR #81 củng cố toàn diện tầng trung chuyển AI-Gateway (LiteLLM) và các dịch vụ RAG kết nối mô hình cục bộ Qwen 3.6 35B A3B FP8:
1. **Triệt tiêu nguy cơ Token Starvation**: Cấu hình `enable_thinking: false` trên `rag-core`, loại bỏ nguy cơ cạn kiệt token (`finish_reason: length`) trên các prompt ngắn, đảm bảo 34 chuỗi cloud fallback và các tác vụ trích xuất JSON hoạt động ổn định < 0.03s.
2. **Phân định rõ rệt 3 Profile Mô Hình**:
   - `rag-core` / `local-instruct`: Non-thinking siêu tốc, finish_reason=stop.
   - `local-coder`: Hỗ trợ function calling (`qwen3_coder`) và thinking (`max_tokens >= 512`).
   - `qwen-local-primary`: Giữ trọn Chain-of-Thought sâu (1,700+ ký tự suy luận).
3. **Cách ly Cache Namespace Redis DB 0**: Kích hoạt `cache_params.namespace: "v20260928_qwen36_nonthinking"` trên LiteLLM, ngăn chặn rủi ro phục vụ lại cache rỗng bị starvation trước đó mà không làm xáo trộn các DB dữ liệu khác (DB 1, 2, 4) và không cần chạy lệnh nguy hiểm `FLUSHALL`.
4. **Vệ sinh Hợp đồng Dịch vụ**: Sửa `ai_gateway_client.py` và `chat_service.py` để loại bỏ false positive với `ocr-primary`.

---

## 2. Toàn Bộ Các Hạng Mục Đã Phát Hành

### A. Cấu Hình AI Gateway (`services/ai-gateway/litellm_config.yaml`)
- **`rag-core`**: Bổ sung `extra_body.chat_template_kwargs.enable_thinking: false`. Loại bỏ cấu hình chết `tool_call_parser: openai`.
- **`local-coder`**: Bổ sung `chat_template_kwargs.enable_thinking: true`.
- **`qwen-local-primary`**: Bổ sung `extra_body.chat_template_kwargs.enable_thinking: true`.
- **Redis Cache Isolation**: Bổ sung `namespace: "v20260928_qwen36_nonthinking"` dưới `litellm_settings.cache_params`.

### B. RAG Backend Service (`services/rag-service/`)
- **`core/ai_gateway_client.py`**: Tinh chỉnh điều kiện stream thinking: Chỉ kích hoạt cho `local-coder`, `qwen-local-primary`, hoặc tên chứa `coder`/`qwen` kết hợp `primary` (tránh khớp nhầm `ocr-primary`).
- **`services/chat_service.py`**: Đồng bộ logic kiểm tra cờ thinking giữa sinh câu trả lời đồng bộ và streaming.

### C. Tri thức & Vận Hành Chuẩn Hóa
- **`.agents/skills/ccba-llm-pipeline-patterns/SKILL.md`**: Bổ sung Pattern 16 về quản trị reasoning profile và phòng thủ cache poisoning.
- **`.md/knowledge/session_learnings.md`**: Cập nhật RULE-5.8 (quản lý dung lượng tệp chặt chẽ $\le 10\text{ KB}$).
- **`scripts/verify_gateway_endpoints.py`**: Bổ sung Section 6 kiểm thử live tự động 3 profile Qwen 3.6.
- **`.md/peer_exchange/grok_completion_review_gateway.md`**: Lưu trữ biên bản nghiệm thu độc lập của Grok 4.7.

---

## 3. Nhật Ký Nghiệm Thu Chất Lượng (Quality Gates)

| Hạng mục kiểm tra | Kết quả thực tế | Trạng thái |
|---|:---:|:---:|
| **Local Unit Tests** | 527/527 tests passed in 10.68s | ✅ 100% PASS |
| **Local Linter (flake8)** | 0 errors trên toàn bộ backend & scripts | ✅ PASS |
| **Maskara Secret Scanner** | 0 secrets / 0 leaks | ✅ PASS |
| **Live Gateway Verification (:8090)** | 5/5 kịch bản PASS (đo đạc latency < 0.03s trên rag-core) | ✅ PASS |
| **Redis Cache Isolation (DB 0)** | 22 key mang prefix `v20260928_qwen36_nonthinking`, DB 1, 2, 4 nguyên vẹn | ✅ PASS |
| **Grok 4.7 Host-Direct Audit** | Phán quyết **FINAL APPROVE** không có khiếm khuyết chặn | ✅ PASS |
| **GitHub Actions: Backend Tests** | Hoàn thành thành công (1m 03s) | ✅ PASS |
| **GitHub Actions: Frontend Build** | Hoàn thành thành công (24s) | ✅ PASS |
| **GitHub Actions: Python Lint** | Hoàn thành thành công (11s) | ✅ PASS |
| **GitHub Actions: Security Audit** | Hoàn thành thành công (43s) | ✅ PASS |

---

## 4. Dọn Dẹp Môi Trường & Lưu Trữ
- **Branch**: Nhánh `feat/ai-gateway-reasoning-model-profiles` đã được xóa sạch cục bộ và remote `origin`.
- **Nhánh Master**: Đã đồng bộ hoàn toàn với `origin/master` tại commit `81b419f`.
- **Containers**: `ai-gateway` (:8090) up and healthy, `qwen36b` (:8004) ổn định liên tục không bị restart ngoài ý muốn.
