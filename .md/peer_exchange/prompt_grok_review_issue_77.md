# Yêu Cầu Phản Biện Đối Kháng (Adversarial Review Request): Kế Hoạch Tiến Hóa Skills `ccba-llm-pipeline-patterns` & `vllm-manager` (Issue #77)

## Bối Cảnh (Context)
Bạn là **Grok 4.7**, đóng vai trò **Peer Reviewer đối kháng (Adversarial Peer Reviewer) & Kỹ sư Hệ thống AI cấp cao** cho máy chủ **NVIDIA DGX Spark** (Grace Blackwell GB10, 128GB Unified Memory, ARM64, Ubuntu Linux).

Sau khi nâng cấp Local Primary LLM thành công lên **Qwen 3.6 35B FP8** (PR #76), Antigravity Agent đã lập bản kế hoạch triển khai cho **Issue #77**: *"tiến hóa ccba-llm-pipeline-patterns và vllm-manager cho reasoning models"*.

Người dùng yêu cầu bạn **rà soát đối kháng, vạch lá tìm sâu, phản biện độc lập** bản kế hoạch này trước khi bước vào giai đoạn Coding.

---

## Toàn Văn Kế Hoạch Của Antigravity (Implementation Plan Under Review)

### 1. Đánh giá Khả năng Tái sử dụng (Reuse Assessment — Audit Receipt)
- `ccba-llm-pipeline-patterns`: Dòng 777 (`catalog.yaml`) -> Bổ sung Pattern 16 về Thinking Token Starvation Defense, củng cố quy tắc RULE-5.8.
- `ccba-vllm-manager`: Dòng 1145 (`catalog.yaml`) -> Skill chuẩn Hub (Tier 2B Domain), quản lý vLLM trên DGX Spark Blackwell GB10.
- `vllm-manager` (Spoke legacy): Cục bộ `.agents/skills/vllm-manager/` -> Đồng bộ hóa & Giữ tương thích: Nâng cấp nội dung khớp với Qwen 3.6 và dẫn truyền sang `ccba-vllm-manager` để không làm gãy các scripts hiện hữu (`workflow_optimizer.py`, `audit-skills.md`).

### 2. Kế hoạch Phân Lập 2 Giai Đoạn (2-Phase Execution Plan)

#### Giai đoạn 1: Pure Structural Alignment & Compatibility (Zero-Regression)
- Giữ nguyên cấu trúc thư mục và bảo tồn tham chiếu `.agents/skills/vllm-manager/`.
- Bổ sung/chuẩn hóa frontmatter của `.agents/skills/ccba-vllm-manager/SKILL.md` đạt tiêu chuẩn ADR-0056/ADR-0057 với điểm GPI >= 12.0.
- Cập nhật version metadata của `ccba-llm-pipeline-patterns/SKILL.md` lên `1.4.0` với GPI đạt chuẩn.

#### Giai đoạn 2: Feature & Knowledge Evolution Upgrades
1. **Nâng cấp `ccba-llm-pipeline-patterns/SKILL.md`**:
   - Bổ sung Pattern 16: *Thinking Token Starvation Defense & Role-Based Reasoning Management*.
   - Anti-pattern: Mô hình reasoning sinh `<think>...</think>` lan man làm cạn kiệt token trong các hàm `extract_json()`, HyDE generator (`max_tokens <= 512`), titling/tagging.
   - Best Practice: Cưỡng chế `enable_thinking: False` ở tầng chat template (`chat_template_kwargs: {"enable_thinking": False}`) hoặc định tuyến qua alias `local-instruct`.
   - Role-based aliases: `local-instruct` (nhanh ~0.4s, zero reasoning overhead) vs `local-coder` / `rag-core` (suy luận sâu CoT).
   - Defensive Pipeline Fallback: Bắt lỗi `finish_reason == "length"` khi `content` rỗng để retry với `enable_thinking=False`.
2. **Nâng cấp `vllm-manager/SKILL.md` & `ccba-vllm-manager/SKILL.md`**:
   - **Tối ưu AOT Inductor Cache**: Hướng dẫn volume mount `/home/vvc/.cache/vllm:/root/.cache/vllm` từ host vào container `qwen36b`, tiết kiệm 35-45s biên dịch lại đồ thị mỗi lần khởi động.
   - **Cấu hình Dual Parser**:
     - `--reasoning-parser qwen3` (tách `<think>...</think>`).
     - `--tool-call-parser qwen3_coder` (nhận diện cú pháp gọi tool).
   - **Cảnh báo Double-Parser với LiteLLM**:
     - Cảnh báo rõ ràng: Không cấu hình `tool_call_parser: openai` trên LiteLLM nếu vLLM backend đã xử lý parsing qua `qwen3_coder` để tránh xung đột định dạng schema.
   - **Bổ sung Prometheus Metrics & Troubleshooting**:
     - Giám sát `vllm:num_requests_running`, `vllm:gpu_cache_usage_perc`, `vllm:avg_generation_throughput_toks_per_s`.
     - Xử lý sự cố Thinking Token Starvation và VRAM fragmentation.

### 3. Kế Hoạch Kiểm Định (Scoped Verification Plan)
- Cổng 1: Skills Validation Gate: `validate_skills.py --file .agents/skills/ccba-llm-pipeline-patterns/SKILL.md --enforce-gpi`
- Cổng 2: vLLM Manager Gate: `validate_skills.py --file .agents/skills/ccba-vllm-manager/SKILL.md --enforce-gpi`
- Cổng 3: Cross-Reference & Link Check
- Cổng 4: Git Cleanliness & Scope Diff

---

## Nhiệm Vụ Của Bạn (Your Review Mandate)
Hãy thực hiện phản biện nghiêm ngặt trên các phương diện:
1. **Kiểm tra Kỹ thuật Thực tế (Hardware & Runtime Sanity)**:
   - Volume mount `/home/vvc/.cache/vllm:/root/.cache/vllm`: Container chạy dưới `root`, host chạy dưới `vvc` (UID 1000). Có xung đột file permission khi container ghi cache không?
   - Cấu hình `--reasoning-parser qwen3` kết hợp `--tool-call-parser qwen3_coder`: Có rủi ro nào khi client gọi streaming SSE (`stream: true`) có thinking blocks và tool calls đồng thời không?
   - Nhận định về `tool_call_parser: openai` trong `litellm_config.yaml` (dòng 1040): Liệu cấu hình hiện tại có thực sự gây lỗi double-parser không, hay LiteLLM yêu cầu tham số này để bóc tách từ vLLM OpenAI-compatible output?
2. **KISS & Architecture Invariants**:
   - Vấn đề tồn tại song song 2 skills: `vllm-manager` (cũ) và `ccba-vllm-manager` (mới). Kế hoạch đề xuất cập nhật cả 2 có vi phạm nguyên tắc Single Source of Truth không? Có nên biến `vllm-manager` thành symlink / thin proxy dẫn sang `ccba-vllm-manager`?
   - Giải pháp phòng thủ thinking token starvation: Việc đặt `enable_thinking: False` trong `chat_template_kwargs` có được tất cả OpenAI SDKs / LiteLLM proxy pass-through nguyên vẹn không?
3. **Phán Quyết & Bảng Điểm**:
   - Chấm điểm: Vững chắc kỹ thuật, Tiện dụng vận hành, Tuân thủ KISS, Rủi ro hồi quy.
   - Đưa ra Phán quyết: **CHẤP THUẬN (ACCEPT)** / **CHẤP THUẬN CÓ ĐIỀU KIỆN (CONDITIONAL ACCEPT)** / **BÁC BỎ (REJECT)**.
   - Liệt kê các điều kiện / hành động cụ thể bắt buộc sửa đổi (Actionable Mandates).
