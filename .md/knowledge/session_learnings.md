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
- `RULE-1.6 (Heuristic Tier Preservation)`: Hậu tố `-high`, `-medium`, `-low` (`gemini-3.8-flash-high`) được Antigravity Tools cấp ngân sách tư duy tương ứng (16k/4k/1k). Không map về model gốc trong `custom_mapping` để tránh bị tước hậu tố làm sụt giảm ngân sách suy luận.
- `RULE-1.7 (Zero Quota Circuit Breaker)`: `lock_on_zero_quota: true` thuộc root `circuit_breaker` trong `gui_config.json`. Khóa tài khoản cạn quota đến `reset_time` tuần của Google thay vì lùi ngắn hạn (60s-300s), chặn retry 429 vô ích.
- `RULE-1.8 (Prompt Caching & Compression)`: Chế độ `Balance` (KV Cache $\ge 85\%$) nghiêm cấm nén L2/L3 (Caveman) vì làm biến dạng prefix hash, kéo cache hit về 0%. Chỉ dùng `compression_level: "low"` (RTK Denoising) làm sạch ANSI/progress bar để bảo toàn 100% prefix cache.
- `RULE-1.9 (Dynamic Version Gate)`: Nâng cấp container so khớp phiên bản (`packaging.version.parse`). Chỉ gợi ý khi `latest > current`. Nếu `current == latest`, báo đã ở bản mới nhất kèm `reinstall`. Khi không lấy được bản upstream, yêu cầu chỉ định version.
- `RULE-1.10 (Audit Chain Continuity & Hermetic Tests)`: Daemon có audit trail băm nối tiếp (Chained SHA-256) bắt buộc đọc mã băm bản ghi cuối từ disk lúc boot để nối chuỗi. Mọi unit test nghiệp vụ bắt buộc mock hàm ghi audit; test chính cơ chế audit bắt buộc chuyển hướng `AUDIT_FILE` sang `tmp_path` fixture để cô lập hermetic 100%.
- `RULE-1.11 (Spoke Contribution Worktree)`: Đóng góp Spoke lên Hub khi Hub có uncommitted changes trên branch, bắt buộc tạo isolated worktree (`git worktree add /tmp/... origin/main`). Sau merge vào Hub `main`, Hub repo host checkout `main` để editable packages (`pip install -e`) cập nhật.
- `RULE-1.12 (Cold-Cache & Multi-Key Gate)`: Đo SLA RAG bắt buộc dùng Cold Cache (UUID prompt) để tránh trúng SemanticCache giả tạo. Model gateway phải test $\ge 3$ keys trong pool tránh lỗi 404/503 do vendor khai tử tài khoản mới. Khâu real-time (Rewrite, Timeline, Rerank) bắt buộc dùng chuỗi `claude-haiku-4` $\rightarrow$ `rag-core` GPU (SLA $< 2.0\text{s}$).
- `RULE-1.13 (Warmup Budget & Shield Self-Healing)`: Nạp BGE-M3 (CPU ~60s) + BGE-Reranker (GPU ~34s) trên DGX Spark mất ~94s; `WARMUP_TIMEOUT_SECONDS` phải đặt $\ge 110.0\text{s}$ (dưới trần `start_period: 120s`). Dùng `asyncio.shield` để worker tiếp tục chạy ngầm và tự chuyển `warmup_status = ready` nếu vượt timeout.

---

## Miền 2: Code Quality & Testing

- `RULE-2.1 (Null Content in Thinking Models)`: Các mô hình suy luận (Gemini 3.8 Flash, Claude Thinking) có thể trả về `choices[0].message.content = None` khi reasoning tokens chiếm toàn bộ quota `max_tokens`. Client parser bắt buộc dùng `(msg.get("content") or "").strip()` và cấu hình `max_tokens` đủ lớn ($\ge 256$) để tránh ngoại lệ `AttributeError: 'NoneType' object has no attribute 'strip'`.
- `RULE-2.2 (Spoke Cleanliness Guard)`: Thư mục `scripts/` khống chế nghiêm ngặt $\le 15$ tệp tin hợp lệ. Các script legacy/tạm thời phải dọn dẹp và lưu trữ vào `.md/archive/legacy_scripts/`.
- `RULE-2.3 (Shift-Left Determinism)`: Trước khi commit hoặc release, bắt buộc thực thi bộ kiểm chuẩn `.venv/bin/python -m ccba_harness verify-patch` với 4 chốt chặn cục bộ (Cleanliness, Import Depth, Flake8, Gateway Live Endpoints).
- `RULE-2.4 (Poison Budget Elimination in Gemini 3.x)`: Gửi tham số `thinking_budget < 2048` (đặc biệt là hardcode `1000`) khiến Gemini 3.x đánh giá không gian tư duy không đủ và tự động tắt hoàn toàn luồng suy luận (reasoning tokens = 0). Cần thiết lập `control_source = "gateway"` để gateway tự động chuẩn hóa budget an toàn ($\ge 10001$ cho Pro, $\ge 16384$ cho Flash High).
- `RULE-2.5 (Vector DB Parity Lock)`: Kiểm toán RAG bắt buộc chốt chặn Parity: `set(exported_doc_ids) - set(indexed_doc_ids) == empty`. Lấy mẫu ngẫu nhiên (sampling) chỉ đo chất lượng chunk, không bảo đảm tính toàn vẹn của danh mục tài liệu.
- `RULE-2.6 (Pre-Lock Validation Invariant)`: Mọi tham số timeout/config phải parse và kiểm tra trước khi acquire lock mutex trong async worker. Bọc dispatch worker trong try-except để giải phóng lock ngay nếu lỗi, triệt tiêu 100% rủi ro deadlock.

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
- `RULE-5.3 (Headless Tauri GUI Daemon)`: App Tauri systemd user service trên Linux không gán cứng `DISPLAY=:11.0`. Khởi chạy qua `/usr/bin/xvfb-run -a <binary> --minimized` cấp virtual display RAM độc lập, bật `loginctl enable-linger <user>` để daemon chạy 24/7 sau reboot.
- `RULE-5.4 (PR Release Synchronization Cycle)`: Sau khi PR được squash & merge trên GitHub và remote branch bị xóa, local `master` cần thực hiện chu trình đồng bộ hoàn tất: checkout `master` $\rightarrow$ `git pull origin master` (fast-forward) $\rightarrow$ `git branch -D <branch>` $\rightarrow$ `git fetch --prune` để dọn sạch tracking branches mồ côi.
- `RULE-5.5 (Headless Watchdog Metric Aggregation)`: Trong môi trường containerized watchdog (`smart-watchdog`), các chỉ số phần cứng máy chủ (SoC Temp, RAM, NVMe) có thể đọc trực tiếp từ `/proc/meminfo`, `shutil.disk_usage('/')`, `/sys/class/thermal` mà không cần quyền root hay cài đặt thêm driver nặng. Kết hợp truy vấn qua mạng nội bộ IP Tailscale để thu thập metrics và token stats của các desktop daemon chạy trên host.
- `RULE-5.6 (Blackwell GB10 Unified Memory SMI Query)`: Trên GPU Grace Blackwell (GB10 128GB Unified Memory), `nvidia-smi --query-gpu=memory.total,memory.used` trả về `[N/A]`. Script giám sát bắt buộc truy vấn qua `nvidia-smi --query-compute-apps=process_name,used_memory`, cộng dồn tiến trình tính toán và gán nhãn `128 GB Unified Memory`.
- `RULE-5.7 (WAL-Safe SQLite Container Disaster Recovery)`: Nâng cấp container dùng SQLite WAL (Open WebUI) bắt buộc dùng API `sqlite3.backup()` trực tiếp trong container để kết xuất snapshot trước khi tarball. Rollback khẩn cấp dùng `alpine:latest` mount volume xóa sạch `-wal`/`-shm` cũ và khôi phục snapshot trước khi up lại bản cũ.

