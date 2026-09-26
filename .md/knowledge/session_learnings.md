# Session Learnings & Spoke Patterns

> **Repository:** `dgx-spark-toolkit` (Spoke)  
> **Ngân sách bộ nhớ:** $\le 10.0\text{ KB}$ (Tiered Memory Model - ADR-0030 / ADR-0057)

---

## Miền 1: Architecture & Governance

- `RULE-1.1 (Base Branch Invariant)`: Nhánh chính tại Spoke `dgx-spark-toolkit` là `master` (không phải `main`). Mọi lệnh PR (`gh pr create`), merge hoặc sync phải dùng base `master`.
- `RULE-1.2 (Gateway drop_params)`: Bật `litellm_settings.drop_params: true` trong `services/ai-gateway/litellm_config.yaml` chặn lỗi HTTP 400 `UnsupportedParamsError` khi OpenAI SDK gửi tham số embedding (`encoding_format: "base64"`) đến Gemini.
- `RULE-1.3 (Reasoning Models Timeout)`: Timeout nhóm mô hình suy luận sâu (`claude-opus-4-6-thinking`, `gemini-3.7-flash-high`, v.v.) phải cấu hình $\ge 90s - 300s$ tại cả router và deployment để tránh timeout khi xử lý chuỗi suy luận dài.
- `RULE-1.4 (Proxy Provider Prefix Invariant)`: Model định tuyến qua Centralized Proxy (`100.83.192.30:8045/v1`) bắt buộc dùng prefix `model: openai/<model-id>` (kể cả Claude), tránh `anthropic/` bị LiteLLM tự thêm `/v1/messages` lỗi 404.
- `RULE-1.5 (Canonical Aliases Sync)`: Cung cấp 3 alias chuẩn hóa (`gemini-flash-latest`, `gemini-reasoning-latest`, `embedding-default`), bắt buộc khai báo đồng thời tại `router_settings.model_group_alias` và `litellm_settings.model_aliases`.
- `RULE-1.6 (Heuristic Tier Preservation)`: Hậu tố `-high`, `-medium`, `-low` (`gemini-3.8-flash-high`) được cấp ngân sách tư duy tương ứng (16k/4k/1k). Không map về model gốc trong `custom_mapping` tránh mất hậu tố làm sụt giảm ngân sách suy luận.
- `RULE-1.7 (Zero Quota Circuit Breaker)`: `lock_on_zero_quota: true` trong `gui_config.json` khóa tài khoản cạn quota đến `reset_time` tuần thay vì lùi ngắn hạn (60s-300s), chặn retry 429 vô ích.
- `RULE-1.8 (Prompt Caching & Compression)`: Chế độ `Balance` (KV Cache $\ge 85\%$) cấm nén L2/L3 (Caveman) vì lệch prefix hash (cache hit về 0%). Chỉ dùng `compression_level: "low"` (RTK) bảo toàn prefix cache.
- `RULE-1.9 (Dynamic Version Gate)`: Nâng cấp container: `packaging.version.parse`. Gợi ý khi `latest > current`; `current == latest` báo đã ở bản mới nhất kèm `reinstall`. Upstream lỗi thì yêu cầu chỉ định version.
- `RULE-1.10 (Audit Chain Continuity & Hermetic Tests)`: Audit trail băm nối tiếp (Chained SHA-256) phải đọc mã băm cuối từ disk lúc boot. Unit test nghiệp vụ mock ghi audit; test audit chuyển hướng `AUDIT_FILE` sang `tmp_path` fixture cô lập 100%.
- `RULE-1.11 (Spoke Contribution Worktree)`: Đóng góp Spoke lên Hub khi branch có uncommitted changes: tạo isolated worktree (`git worktree add /tmp/... origin/main`). Sau merge vào Hub `main`, host repo checkout `main` để editable packages cập nhật.
- `RULE-1.12 (Cold-Cache & Multi-Key Gate)`: Đo SLA RAG dùng Cold Cache (UUID prompt). Gateway pool test $\ge 3$ keys tránh 404/503. Khâu real-time (Rewrite, Timeline, Rerank) dùng chuỗi `claude-haiku-4` $\rightarrow$ `rag-core` GPU (SLA $< 2.0\text{s}$).
- `RULE-1.13 (Warmup Budget & Shield Self-Healing)`: Nạp BGE-M3 (CPU ~60s) + BGE-Reranker (GPU ~34s) mất ~94s; `WARMUP_TIMEOUT_SECONDS` đặt $\ge 110s$ (dưới trần `start_period: 120s`). Dùng `asyncio.shield` để worker tiếp tục chạy ngầm và tự chuyển `ready` nếu vượt timeout.

---

## Miền 2: Code Quality & Testing

- `RULE-2.1 (Null Content in Thinking Models)`: Thinking models trả về `content = None` khi reasoning tokens chiếm hết quota `max_tokens`. Parser bắt buộc dùng `(msg.get("content") or "").strip()` và `max_tokens >= 256` tránh crash `NoneType`.
- `RULE-2.2 (Spoke Cleanliness Guard)`: Thư mục `scripts/` khống chế $\le 15$ tệp hợp lệ. Script legacy/tạm thời lưu trữ vào `.md/archive/legacy_scripts/`.
- `RULE-2.3 (Shift-Left Determinism)`: Trước khi commit hoặc release, bắt buộc thực thi bộ kiểm chuẩn `.venv/bin/python -m ccba_harness verify-patch` với 4 chốt chặn cục bộ (Cleanliness, Import Depth, Flake8, Gateway Live Endpoints).
- `RULE-2.4 (Poison Budget Elimination in Gemini 3.x)`: Gửi `thinking_budget < 2048` khiến Gemini 3.x tắt hẳn luồng suy luận (`reasoning tokens = 0`). Đặt `control_source = "gateway"` để gateway tự chuẩn hóa budget ($\ge 10001$ cho Pro, $\ge 16384$ cho Flash High).
- `RULE-2.5 (Vector DB Parity Lock)`: Kiểm toán RAG bắt buộc chốt chặn Parity: `set(exported_doc_ids) - set(indexed_doc_ids) == empty`. Lấy mẫu ngẫu nhiên (sampling) chỉ đo chất lượng chunk, không bảo đảm tính toàn vẹn của danh mục tài liệu.
- `RULE-2.6 (Pre-Lock Validation Invariant)`: Tham số timeout/config phải validate trước khi acquire mutex trong async worker. Bọc dispatch worker trong try-except để giải phóng lock ngay nếu lỗi, triệt tiêu deadlock.
- `RULE-2.7 (Vite ManualChunks & AnimatePresence Key)`: Lazy import đơn lẻ không đủ hạ bundle < 300 kB nếu tab mặc định nạp vendor lớn; tách vendor bằng `manualChunks`. Direct child trong `<AnimatePresence mode="wait">` bắt buộc gán `key` riêng; fallback `<Suspense>` dùng `<div>` thuần kèm `role="status"`.
- `RULE-2.8 (Vite Typecheck & Zombie Pruning)`: Cấu hình `"typecheck": "tsc --noEmit"` chạy trên cả CI và Local Gate. Định kỳ rà soát gỡ bỏ zombie dependencies thừa tránh phình `node_modules` (-50%) và triệt tiêu lỗ hổng bảo mật.
- `RULE-2.9 (Dual-Requirement File Sync)`: Bổ sung thư viện mới (như `pyyaml`) cho service bắt buộc đồng bộ vào cả `requirements.txt` VÀ `requirements-ci.txt` để tránh lỗi crash import trong pha thu thập test trên runner GitHub Actions.
- `RULE-2.10 (Fast-Path Chunker Online LLM Isolation)`: Fast-Path converter nạp tài liệu sạch bắt buộc tắt tính năng tự sửa bảng / tóm tắt qua LLM Vision trong `DocumentChunker` (`TABLE_CORRECT_ENABLED = False`, `TABLE_SUMMARY_ENABLED = False`), triệt tiêu độ trễ mạng (giảm từ 80s+ xuống < 1s).
- `RULE-2.11 (Dynamic Catalog Sizing Invariant)`: Unit test kiểm thử kho tri thức hoặc catalog pháp luật sống cấm assert kích thước cố định (`assert len == 60`), bắt buộc dùng kiểm tra cận dưới (`assert len >= 60`) để tương thích khi dữ liệu liên tục mở rộng.

---

## Miền 3: Legal & Data Standards

- `RULE-3.1 (Verbatim Grounding & Provenance)`: Mọi knowledge bundle, trích đoạn văn bản pháp luật hoặc fixture dữ liệu phải gắn provenance mã băm SHA-256 đối chiếu nguồn văn bản gốc, nghiêm cấm sinh giả định hoặc mock điều khoản.
- `RULE-3.2 (Hard Cryptographic Ingestion Gate)`: Pipeline nạp văn bản pháp luật vào hàng đợi (`ingest:queue` / Milvus) bắt buộc tích hợp chốt chặn mã băm SHA-256 (ADR-0059). Cấm tuyệt đối nạp gói tài liệu `TAMPERED` hoặc thiếu nguồn pháp lý; phát hiện sai lệch băm phải lập tức chặn đứng.

---

## Miền 4: Workflows & Review

- `RULE-4.1 (GitHub Actions Billing Fallback)`: Khi runner GitHub Actions bị gián đoạn do hạn mức tài khoản (`billing spending limit`), đối chiếu annotation để xác nhận và dùng Shift-Left Local Gate làm căn cứ nghiệm thu, không suy đoán sang lỗi mã nguồn.
- `RULE-4.2 (Copilot Review Verification)`: Mọi review từ bot/Copilot (`PRR_...`) phải được đối soát và giải trình minh bạch tại `.md/knowledge/reports/walkthrough.md`.
- `RULE-4.3 (GitHub PR Merge In-Progress Recovery)`: Khi `gh pr merge` lỗi `GraphQL: Merge already in progress` (HTTP 405 do 502), chờ 10-20s rồi merge qua REST API: `gh api -X PUT repos/{owner}/{repo}/pulls/{number}/merge -f merge_method=squash`.
- `RULE-4.4 (Idempotent Label Provisioning)`: Khâu claim issue gán nhãn `in-progress` (`gh issue edit --add-label`) phải idempotent: chạy `gh label create in-progress --force --color fbca04 2>/dev/null || true` trước khi gán để tránh lỗi thiếu nhãn.

---

## Miền 5: Linux, Tooling & Environment

- `RULE-5.1 (Python Executable Ambiguity)`: Trên môi trường Ubuntu/Linux, lệnh `python` không tồn tại mặc định. Mọi pre-commit hooks, scripts và lệnh tự động hóa phải gọi tường minh `python3` hoặc `.venv/bin/python`.
- `RULE-5.3 (Headless Tauri GUI Daemon)`: App Tauri systemd trên Linux khởi chạy qua `xvfb-run -a <binary> --minimized` cấp virtual display RAM, bật `loginctl enable-linger <user>` để daemon chạy 24/7 sau reboot.
- `RULE-5.4 (PR Release Sync & Fast-Forward Reconciliation)`: Chu trình sau squash-merge: checkout `master` $\rightarrow$ `git pull origin master` (nếu phân kỳ: `git reset --hard origin/master`) $\rightarrow$ `git branch -D <branch>` $\rightarrow$ `git fetch --prune`.
- `RULE-5.5 (Headless Watchdog Metric Aggregation)`: Watchdog container đọc metrics SoC Temp, RAM, NVMe trực tiếp từ `/proc/meminfo`, `shutil.disk_usage('/')`, `/sys/class/thermal` không cần root/driver. Thu thập metrics daemon host qua IP Tailscale.
- `RULE-5.6 (Blackwell GB10 Unified Memory SMI Query)`: Trên GPU Grace Blackwell GB10 (128GB Unified Memory), `nvidia-smi --query-gpu=memory.total,memory.used` trả về `[N/A]`. Script bắt buộc truy vấn qua `--query-compute-apps=process_name,used_memory`, cộng dồn tiến trình và gán nhãn `128 GB Unified Memory`.
- `RULE-5.7 (WAL-Safe SQLite Container Disaster Recovery)`: Nâng cấp container SQLite WAL (Open WebUI) phải gọi `sqlite3.backup()` xuất snapshot trước khi tarball. Rollback dùng `alpine:latest` mount volume xóa `-wal`/`-shm` cũ và phục hồi snapshot.
