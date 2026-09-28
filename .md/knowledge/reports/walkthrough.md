# Walkthrough — PR #76: AI-Native Architecture, Modular Chunkers, Fast MCP Tooling & Qwen 3.6 Upgrade

> **PR:** [#76 feat(architecture): refactor for ai-native codebase, modular chunkers, and mcp tooling (ADR-0005)](https://github.com/vvChu/dgx-spark-toolkit/pull/76)  
> **Merged Commit:** `f92ecb2` $\rightarrow$ `master`  
> **Verification Status:** ✅ 100% PASS (527/527 Tests Passed, 0 Flake8 Errors, Dual-Gate CI 4/4 Green)  
> **Production Status:** 🟢 RELEASED & DEPLOYED TO PRODUCTION

---

## 1. Tổng Quan Kết Quả Phát Hành (Release Summary)

Gói phát hành PR #76 mang lại hai bước chuyển biến quan trọng cho hệ thống:
1. **Chuyển đổi Kiến trúc AI-Native (ADR-0005)**: Phân rã cấu trúc tệp monolithic, cách ly Redis DB split, rút ngắn hàm tuân thủ KISS (< 50 dòng), và tích hợp hệ thống MCP Server siêu nhẹ cho AI Agents.
2. **Nâng cấp Toàn diện Local Primary LLM Lên Qwen 3.6 35B FP8 & Tối Ưu Hệ Sinh Thái**: Tăng tốc bóc tách JSON và các tác vụ nền gấp 13.5 lần, kích hoạt Thinking Preservation với parser `qwen3`, và chống cạn kiệt token trong pipeline RAG/HyDE.

---

## 2. Toàn Bộ Các Hạng Mục Đã Phát Hành

### A. Kiến Trúc AI-Native & Modular Chunkers (ADR-0005)
- **Scoped Progressive Disclosure**: Bổ sung `AGENTS.md` phạm vi hẹp (< 40 dòng) cho các dịch vụ `services/rag-service/`, `services/ai-gateway/`, và `services/frontend/`.
- **Phân rã Chunking Monolith**: Tách `chunking.py` (894 dòng) thành gói module chuyên biệt `services/rag-service/ingestion/chunkers/` (`base.py`, `legal.py`, `layout.py`, `table.py`, `fallback.py`) kèm Facade mỏng bảo đảm 100% tương thích ngược.
- **Cách Ly Redis DB 3**: Chuyển Table Summary Cache sang Redis DB 3 (`format_redis_db3_url`), giải phóng triệt để Redis DB 1 cho hàng đợi ingestion stream (`ingest:queue`).
- **Tối Giản Hóa Pipeline Tìm Kiếm (KISS)**: Refactor các stage trong `search_pipeline.py` thành các hàm con < 35 dòng, bảo đảm 100% hàm trong phạm vi kiểm toán $\le 50$ dòng.
- **Fast MCP Server (`scripts/mcp_server.py`)**: Cầu nối HTTP Bridge sang RAG daemon `:8005`, tiêu thụ 0 MB VRAM bổ sung, cold start ~0.3s.

### B. Nâng Cấp Local Primary LLM Lên Qwen 3.6 35B FP8
- **Mô hình**: `Qwen/Qwen3.6-35B-A3B-FP8` chạy trên vLLM (container `qwen36b`), kiến trúc `Qwen3_5MoeForConditionalGeneration` (MoE 256/8, Dynamic FP8, native Vision multimodal).
- **Thinking Preservation**: Kích hoạt `--reasoning-parser qwen3` và `--tool-call-parser qwen3_coder`.
- **Inductor AOT Cache**: Bổ sung volume mount `- /home/vvc/.cache/vllm:/root/.cache/vllm` tiết kiệm 40s thời gian khởi động container.

### C. Tối Ưu Hóa Hệ Sinh Thái Đa Dịch Vụ (Ecosystem Optimization)
- **Role-based Aliases trên AI Gateway (`litellm_config.yaml`)**:
  - `local-instruct`: Ép buộc `enable_thinking: False`, rút ngắn độ trễ xử lý JSON từ 5.6s xuống **0.398s (nhanh hơn 13.5x)**, loại bỏ hoàn toàn token suy luận thừa.
  - `local-coder`: Dành riêng cho lập trình và bài toán suy luận sâu.
- **Open WebUI (`docker-compose.yml`)**: Cấu hình `TASK_MODEL: local-instruct`, giúp các tác vụ ngầm (auto-titling, tóm tắt) hoàn tất trong < 0.4s.
- **RAG Service & HyDE Pipeline**:
  - `extract_json()`: Mặc định `enable_thinking: False`, chống cạn kiệt token trên prompt ngắn.
  - `HyDEGenerator`: Tắt thinking với `max_tokens=512`, khắc phục triệt để hiện tượng câu trả lời giả định bị rỗng (sinh thành công 1,308 ký tự chuẩn xác).

---

## 3. Nhật Ký Nghiệm Thu Chất Lượng (Quality Gates)

| Hạng mục kiểm tra | Kết quả thực tế | Trạng thái |
|---|:---:|:---:|
| **Local Unit Tests** | 527/527 tests passed | ✅ 100% PASS |
| **Local Linter (flake8)** | 0 errors trên toàn bộ file thay đổi | ✅ PASS |
| **Maskara Secret Scanner** | 0 secrets / 0 leaks | ✅ PASS |
| **GitHub Actions: Backend Tests** | Hoàn thành thành công | ✅ PASS |
| **GitHub Actions: Frontend Build** | Hoàn thành thành công | ✅ PASS |
| **GitHub Actions: Python Lint** | Hoàn thành thành công | ✅ PASS |
| **GitHub Actions: Security Audit** | Hoàn thành thành công | ✅ PASS |
| **Model Throughput Concurrency=1** | 54.46 tokens/s (TTFT: 0.28s) | ✅ PASS |
| **Model Throughput Concurrency=4** | 137.35 tokens/s tổng thông lượng | ✅ PASS |

---

## 4. Dọn Dẹp Môi Trường & Lưu Trữ
- **Branch**: Nhánh `refactor/ai-native-codebase` đã được xóa sạch cục bộ và trên remote `origin`.
- **Nhánh Master**: Đã đồng bộ hoàn toàn với `origin/master` tại commit `f92ecb2`.
- **Mô hình cũ**: `/home/vvc/models/Qwen3.5-35B-A3B-FP8` (34.89 GB) được lưu giữ an toàn làm rollback safety net; dung lượng trống NVMe hiện tại là 849 GB (> 70%).
