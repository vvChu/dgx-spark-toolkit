# Session Learnings & Spoke Patterns

Tài liệu lưu trữ các bài học kinh nghiệm, quy ước môi trường và mẫu kiến trúc được thiết lập cho repository `dgx-spark-toolkit`.

---

## 1. Môi Trường & Git Conventions

- **Default / Base Branch**: Nhánh chính của repository này là `master` (không phải `main`). Mọi PR hoặc thao tác merge mặc định đều trỏ về `master`.
- **Python Executable**: Trên môi trường Linux/Ubuntu hiện tại, lệnh `python` không trỏ trực tiếp đến `python3`. Các scripts, pre-commit hooks hoặc lệnh CI nội bộ phải dùng `python3` hoặc trỏ trực tiếp vào `.venv/bin/python`.
- **Spoke Cleanliness Guard**: Thư mục `scripts/` giới hạn tối đa $\le 15$ tệp tin thực thi. Các scripts tạm thời hoặc kiểm thử cũ cần được lưu trữ có hệ thống vào `.md/archive/legacy_scripts/`.

---

## 2. AI Gateway Architecture (Server Spark :8090)

- **`drop_params: true`**: Bắt buộc khai báo tại `litellm_settings` cấp toàn cục trong `services/ai-gateway/litellm_config.yaml`. Điều này ngăn chặn lỗi HTTP 400 `UnsupportedParamsError` khi OpenAI SDK client gửi các tham số như `encoding_format: "base64"` đến backend Gemini Embeddings.
- **Reasoning Models Timeout (300s)**: Các mô hình có tính năng suy luận sâu (`gemini-3.7-flash-high`, `gemini-3.8-flash-high`, `claude-opus-4-6-thinking`, `claude-opus-4-5-thinking`, v.v.) cần trần timeout tối thiểu `300.0s` tại cả router và model definition để tránh `TimeoutError` khi xử lý prompt phức tạp.
- **Canonical Stable Aliases**:
  - `gemini-flash-latest` $\rightarrow$ `gemini-3.8-flash`
  - `gemini-reasoning-latest` $\rightarrow$ `gemini-3.8-flash-high`
  - `embedding-default` $\rightarrow$ `gemini-embedding-2`
  Được khai báo đồng bộ tại `router_settings.model_group_alias` và `litellm_settings.model_aliases`.
- **Fallback Group**: Cấu hình fallback luân chuyển giữa `gemini-embedding-2` và `gemini-embed` để đảm bảo độ sẵn sàng của pipeline RAG.

---

## 3. CI / CD & Quality Gates

- **Authority Shift-Left Gate**: Sử dụng `.venv/bin/python -m ccba_harness verify-patch` với các bài kiểm thử:
  - `scripts/check_spoke_cleanliness.py` (kiểm soát số lượng scripts)
  - `scripts/check_hub_import_depth.py` (chống rò rỉ phụ thuộc ngược)
  - `flake8 services/rag-service/`
  - `scripts/verify_gateway_endpoints.py` (kiểm thử trực tiếp live endpoints)
- **GitHub Actions Runner Billing**: Khi tài khoản GitHub chạm ngưỡng spending limit, runner có thể bị hủy ở tầng dispatch kèm annotation thanh toán. Agent căn cứ vào Shift-Left Local Gate để đảm bảo độ tin cậy của mã nguồn.
