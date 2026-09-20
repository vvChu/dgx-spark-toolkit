# Session Learnings & Spoke Patterns

> **Repository:** `dgx-spark-toolkit` (Spoke)  
> **Ngân sách bộ nhớ:** $\le 10.0\text{ KB}$ (Tiered Memory Model - ADR-0030 / ADR-0057)

---

## Miền 1: Architecture & Governance

- `RULE-1.1 (Base Branch Invariant)`: Nhánh chính tại Spoke `dgx-spark-toolkit` là `master` (không phải `main`). Mọi lệnh PR (`gh pr create`), merge hoặc sync phải dùng base `master`.
- `RULE-1.2 (Gateway drop_params)`: Bắt buộc cấu hình `litellm_settings.drop_params: true` toàn cục trong `services/ai-gateway/litellm_config.yaml`. Ngăn chặn hoàn toàn lỗi HTTP 400 `UnsupportedParamsError` khi OpenAI SDK client gửi tham số embedding không tương thích (như `encoding_format: "base64"`) đến backend Gemini Embeddings.
- `RULE-1.3 (Reasoning Models Timeout)`: Timeout cho nhóm mô hình suy luận sâu (`claude-opus-4-6-thinking`, `gemini-3.7-flash-high`, `gemini-3.8-flash-high`, v.v.) phải cấu hình tối thiểu $\ge 90.0s$ - $300.0s$ tại cả router và deployment để tránh timeout khi xử lý chuỗi suy luận dài.
- `RULE-1.4 (Proxy Provider Prefix Invariant)`: Mọi model định tuyến qua Centralized Proxy (`100.83.192.30:8045/v1`) bắt buộc dùng prefix `model: openai/<model-id>` (kể cả Claude). Tuyệt đối không dùng `anthropic/` với proxy endpoint vì LiteLLM sẽ tự thêm `/v1/messages` gây HTTP 404.
- `RULE-1.5 (Canonical Aliases Sync)`: Cung cấp 3 alias chuẩn hóa (`gemini-flash-latest`, `gemini-reasoning-latest`, `embedding-default`), bắt buộc khai báo đồng thời tại `router_settings.model_group_alias` và `litellm_settings.model_aliases`.
- `RULE-1.6 (Heuristic Tier Preservation)`: Trong Antigravity Tools v4.7.8 (`model_specs.rs:110-127`), các model có hậu tố heuristic bậc suy luận như `-high`, `-medium`, `-low` (`gemini-3.8-flash-high`) được tự động nhận diện và gán ngân sách tư duy phù hợp (16k / 4k / 1k). Tuyệt đối KHÔNG map các model này trong `custom_mapping` về model gốc (như `gemini-3.8-flash`) vì router sẽ tước bỏ hậu tố tier, gây sụt giảm ngân sách suy luận (silent degradation).
- `RULE-1.7 (Zero Quota Circuit Breaker Root Schema)`: Trong `gui_config.json` của Antigravity Tools, tham số `lock_on_zero_quota: true` thuộc khối root `circuit_breaker` (không thuộc `proxy.scheduling`). Khi kích hoạt, nó khóa cứng tài khoản cạn kiệt đến đúng mốc `reset_time` tuần của Google thay vì lùi bước ngắn hạn (60s-300s), loại bỏ hoàn toàn vòng lặp retry 429 vô ích.
- `RULE-1.8 (Prompt Caching vs Context Compression Tradeoff)`: Khi áp dụng chiến lược điều phối `Balance` (để tận dụng Prompt Caching / KV Cache hit rate 85%+), TUYỆT ĐỐI KHÔNG bật nén ngữ cảnh L2 (Caveman Cleaner) hoặc L3. Caveman sửa đổi từ ngữ các tin nhắn cũ trước 4 tin gần nhất, làm biến dạng byte-for-byte prefix hash khiến Cache Hit tụt về 0%. Chỉ sử dụng `compression_level: "low"` (RTK Denoising) để làm sạch ANSI/progress bar trong output tool call mà vẫn bảo toàn 100% prefix cache.

---

## Miền 2: Code Quality & Testing

- `RULE-2.1 (Null Content in Thinking Models)`: Các mô hình suy luận (Gemini 3.8 Flash, Claude Thinking) có thể trả về `choices[0].message.content = None` khi reasoning tokens chiếm toàn bộ quota `max_tokens`. Client parser bắt buộc dùng `(msg.get("content") or "").strip()` và cấu hình `max_tokens` đủ lớn ($\ge 256$) để tránh ngoại lệ `AttributeError: 'NoneType' object has no attribute 'strip'`.
- `RULE-2.2 (Spoke Cleanliness Guard)`: Thư mục `scripts/` khống chế nghiêm ngặt $\le 15$ tệp tin hợp lệ. Các script legacy/tạm thời phải dọn dẹp và lưu trữ vào `.md/archive/legacy_scripts/`.
- `RULE-2.3 (Shift-Left Determinism)`: Trước khi commit hoặc release, bắt buộc thực thi bộ kiểm chuẩn `.venv/bin/python -m ccba_harness verify-patch` với 4 chốt chặn cục bộ (Cleanliness, Import Depth, Flake8, Gateway Live Endpoints).
- `RULE-2.4 (Poison Budget Elimination in Gemini 3.x)`: Gửi tham số `thinking_budget < 2048` (đặc biệt là hardcode `1000`) khiến Gemini 3.x đánh giá không gian tư duy không đủ và tự động tắt hoàn toàn luồng suy luận (reasoning tokens = 0). Cần thiết lập `control_source = "gateway"` để gateway tự động chuẩn hóa budget an toàn ($\ge 10001$ cho Pro, $\ge 16384$ cho Flash High).

---

## Miền 3: Legal & Data Standards

- `RULE-3.1 (Verbatim Grounding & Provenance)`: Mọi knowledge bundle, trích đoạn văn bản pháp luật hoặc fixture dữ liệu phải gắn provenance mã băm SHA-256 đối chiếu nguồn văn bản gốc, nghiêm cấm sinh giả định hoặc mock điều khoản.

---

## Miền 4: Workflows & Review

- `RULE-4.1 (GitHub Actions Billing Fallback)`: Khi runner GitHub Actions bị gián đoạn ở tầng dispatch do hạn mức tài khoản (`billing & plans spending limit`), đối chiếu annotation để xác nhận và sử dụng Shift-Left Local Quality Gate làm căn cứ nghiệm thu tin cậy, không suy đoán sai lệch sang lỗi mã nguồn.
- `RULE-4.2 (Copilot Review Verification)`: Mọi review từ bot/Copilot (`PRR_...`) phải được đối soát và giải trình minh bạch tại `.md/knowledge/reports/walkthrough.md`.
- `RULE-4.3 (GitHub PR Merge In-Progress Recovery)`: Khi `gh pr merge` gặp lỗi `GraphQL: Merge already in progress` (HTTP 405) sau sự cố kết nối gián đoạn (502 Bad Gateway), GitHub đang giữ transaction lock tạm thời trên PR. Tuyệt đối không force-push hay hủy branch; chờ 10-20 giây cooldown rồi hoàn tất merge trực tiếp qua REST API: `gh api -X PUT repos/{owner}/{repo}/pulls/{number}/merge -f merge_method=squash`.

---

## Miền 5: Linux, Tooling & Environment

- `RULE-5.1 (Python Executable Ambiguity)`: Trên môi trường Ubuntu/Linux, lệnh `python` không tồn tại mặc định. Mọi pre-commit hooks, scripts và lệnh tự động hóa phải gọi tường minh `python3` hoặc `.venv/bin/python`.
- `RULE-5.2 (Remote Branch Pruning)`: Sau khi squash & merge PR trên GitHub, bắt buộc chạy `git fetch --prune` để dọn dẹp tracking branches đã bị xóa trên remote.
- `RULE-5.3 (Headless Tauri GUI Daemon via Xvfb)`: Các ứng dụng Tauri desktop (như Antigravity Tools) chạy dưới dạng systemd user service trên máy chủ Linux/DGX Spark không được gán cứng biến môi trường `DISPLAY=:11.0` (phụ thuộc vào phiên XRDP). Phải khởi chạy qua `/usr/bin/xvfb-run -a <binary> --minimized` để tự cấp phát virtual display độc lập trong RAM, kết hợp `loginctl enable-linger <user>` để đảm bảo service chạy liên tục 24/7 sau khi reboot mà không cần người dùng đăng nhập remote desktop.
- `RULE-5.4 (PR Release Synchronization Cycle)`: Sau khi PR được squash & merge trên GitHub và remote branch bị xóa, local `master` cần thực hiện chu trình đồng bộ hoàn tất: checkout `master` $\rightarrow$ `git pull origin master` (fast-forward) $\rightarrow$ `git branch -D <branch>` $\rightarrow$ `git fetch --prune` để dọn sạch tracking branches mồ côi.
- `RULE-5.5 (Headless Watchdog Metric Aggregation)`: Trong môi trường containerized watchdog (`smart-watchdog`), các chỉ số phần cứng máy chủ (SoC Temp, RAM, NVMe) có thể đọc trực tiếp từ `/proc/meminfo`, `shutil.disk_usage('/')`, `/sys/class/thermal` mà không cần quyền root hay cài đặt thêm driver nặng. Kết hợp truy vấn qua mạng nội bộ IP Tailscale để thu thập metrics và token stats của các desktop daemon chạy trên host.

