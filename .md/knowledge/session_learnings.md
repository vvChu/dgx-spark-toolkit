# Session Learnings & Spoke Patterns

> **Repository:** `dgx-spark-toolkit` (Spoke)  
> **Ngân sách bộ nhớ:** $\le 10.0\text{ KB}$ (Tiered Memory Model - ADR-0030 / ADR-0057)

---

## Miền 1: Architecture & Governance

- `RULE-1.1 (Base Branch Invariant)`: Nhánh chính tại Spoke `dgx-spark-toolkit` là `master` (không phải `main`). Mọi lệnh PR (`gh pr create`), merge hoặc sync phải dùng base `master`.
- `RULE-1.2 (Gateway drop_params)`: Bắt buộc cấu hình `litellm_settings.drop_params: true` toàn cục trong `services/ai-gateway/litellm_config.yaml`. Ngăn chặn hoàn toàn lỗi HTTP 400 `UnsupportedParamsError` khi OpenAI SDK client gửi tham số embedding không tương thích (như `encoding_format: "base64"`) đến backend Gemini Embeddings.
- `RULE-1.3 (Reasoning Models Timeout)`: Timeout cho nhóm mô hình suy luận sâu (`claude-opus-4-6-thinking`, `gemini-3.7-flash-high`, `gemini-3.8-flash-high`, v.v.) phải cấu hình tối thiểu $\ge 300.0s$ tại cả router và deployment để tránh timeout khi xử lý chuỗi suy luận dài.
- `RULE-1.4 (Proxy Provider Prefix Invariant)`: Mọi model định tuyến qua Centralized Proxy (`100.83.192.30:8045/v1`) bắt buộc dùng prefix `model: openai/<model-id>` (kể cả Claude). Tuyệt đối không dùng `anthropic/` với proxy endpoint vì LiteLLM sẽ tự thêm `/v1/messages` gây HTTP 404.
- `RULE-1.5 (Canonical Aliases Sync)`: Cung cấp 3 alias chuẩn hóa (`gemini-flash-latest`, `gemini-reasoning-latest`, `embedding-default`), bắt buộc khai báo đồng thời tại `router_settings.model_group_alias` và `litellm_settings.model_aliases`.

---

## Miền 2: Code Quality & Testing

- `RULE-2.1 (Null Content in Thinking Models)`: Các mô hình suy luận (Gemini 3.8 Flash, Claude Thinking) có thể trả về `choices[0].message.content = None` khi reasoning tokens chiếm toàn bộ quota `max_tokens`. Client parser bắt buộc dùng `(msg.get("content") or "").strip()` và cấu hình `max_tokens` đủ lớn ($\ge 256$) để tránh ngoại lệ `AttributeError: 'NoneType' object has no attribute 'strip'`.
- `RULE-2.2 (Spoke Cleanliness Guard)`: Thư mục `scripts/` khống chế nghiêm ngặt $\le 15$ tệp tin hợp lệ. Các script legacy/tạm thời phải dọn dẹp và lưu trữ vào `.md/archive/legacy_scripts/`.
- `RULE-2.3 (Shift-Left Determinism)`: Trước khi commit hoặc release, bắt buộc thực thi bộ kiểm chuẩn `.venv/bin/python -m ccba_harness verify-patch` với 4 chốt chặn cục bộ (Cleanliness, Import Depth, Flake8, Gateway Live Endpoints).

---

## Miền 3: Legal & Data Standards

- `RULE-3.1 (Verbatim Grounding & Provenance)`: Mọi knowledge bundle, trích đoạn văn bản pháp luật hoặc fixture dữ liệu phải gắn provenance mã băm SHA-256 đối chiếu nguồn văn bản gốc, nghiêm cấm sinh giả định hoặc mock điều khoản.

---

## Miền 4: Workflows & Review

- `RULE-4.1 (GitHub Actions Billing Fallback)`: Khi runner GitHub Actions bị gián đoạn ở tầng dispatch do hạn mức tài khoản (`billing & plans spending limit`), đối chiếu annotation để xác nhận và sử dụng Shift-Left Local Quality Gate làm căn cứ nghiệm thu tin cậy, không suy đoán sai lệch sang lỗi mã nguồn.
- `RULE-4.2 (Copilot Review Verification)`: Mọi review từ bot/Copilot (`PRR_...`) phải được đối soát và giải trình minh bạch tại `.md/knowledge/reports/walkthrough.md`.

---

## Miền 5: Linux, Tooling & Environment

- `RULE-5.1 (Python Executable Ambiguity)`: Trên môi trường Ubuntu/Linux, lệnh `python` không tồn tại mặc định. Mọi pre-commit hooks, scripts và lệnh tự động hóa phải gọi tường minh `python3` hoặc `.venv/bin/python`.
- `RULE-5.2 (Remote Branch Pruning)`: Sau khi squash & merge PR trên GitHub, bắt buộc chạy `git fetch --prune` để dọn dẹp tracking branches đã bị xóa trên remote.
