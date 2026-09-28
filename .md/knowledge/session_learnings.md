# Session Learnings & Spoke Patterns

> **Repository:** `dgx-spark-toolkit` (Spoke)  
> **Ngân sách bộ nhớ:** $\le 10.0\text{ KB}$ (Tiered Memory Model - ADR-0030 / ADR-0057)

---

## Miền 1: Architecture & Governance

- `RULE-1.1 (Base Branch Invariant)`: Nhánh chính tại Spoke `dgx-spark-toolkit` là `master`. Mọi lệnh PR (`gh pr create`), merge hoặc sync phải dùng base `master`.
- `RULE-1.2 (Gateway drop_params)`: Bật `litellm_settings.drop_params: true` trong `litellm_config.yaml` chặn HTTP 400 khi OpenAI SDK gửi tham số embedding (`encoding_format: "base64"`) đến Gemini.
- `RULE-1.3 (Reasoning Models Timeout)`: Timeout mô hình suy luận (`claude-opus-4-6-thinking`, `gemini-3.7-flash-high`) cấu hình $\ge 90s - 300s$ tại cả router và deployment tránh timeout chuỗi suy luận dài.
- `RULE-1.4 (Proxy Provider Prefix Invariant)`: Model qua Centralized Proxy bắt buộc dùng prefix `model: openai/<model-id>` (kể cả Claude), tránh `anthropic/` bị LiteLLM thêm `/v1/messages` lỗi 404.
- `RULE-1.5 (Canonical Aliases Sync)`: Cung cấp 3 alias chuẩn hóa (`gemini-flash-latest`, `gemini-reasoning-latest`, `embedding-default`), khai báo đồng thời tại `router_settings.model_group_alias` và `litellm_settings.model_aliases`.
- `RULE-1.6 (Heuristic Tier Preservation)`: Hậu tố `-high`, `-medium`, `-low` (`gemini-3.8-flash-high`) cấp ngân sách tư duy (16k/4k/1k); không map về model gốc trong `custom_mapping` tránh sụt giảm ngân sách suy luận.
- `RULE-1.7 (Zero Quota Circuit Breaker)`: `lock_on_zero_quota: true` trong `gui_config.json` khóa tài khoản cạn quota đến `reset_time` tuần thay vì lùi ngắn hạn (60s-300s), chặn retry 429 vô ích.
- `RULE-1.8 (Prompt Caching & Compression)`: Chế độ `Balance` (KV Cache $\ge 85\%$) cấm nén L2/L3 (Caveman) vì lệch prefix hash; chỉ dùng `compression_level: "low"` (RTK) bảo toàn prefix cache hit.
- `RULE-1.9 (Dynamic Version Gate)`: Nâng cấp container dùng `packaging.version.parse`. Gợi ý khi `latest > current`; `current == latest` báo đã ở bản mới nhất kèm `reinstall`.
- `RULE-1.10 (Audit Chain Continuity)`: Chained SHA-256 đọc hash cuối từ disk lúc boot. Unit test nghiệp vụ mock audit; test audit chuyển `AUDIT_FILE` sang `tmp_path` fixture.
- `RULE-1.11 (Spoke Contribution Worktree)`: Đóng góp Spoke lên Hub khi branch có thay đổi: dùng worktree cô lập (`git worktree add /tmp/... origin/main`), merge xong checkout `main` để update.
- `RULE-1.12 (Cold-Cache & Multi-Key Gate)`: Đo SLA RAG dùng Cold Cache. Gateway pool test $\ge 3$ keys. Tác vụ real-time dùng chuỗi `claude-haiku-4` $\rightarrow$ `rag-core` GPU (SLA $< 2.0\text{s}$).
- `RULE-1.13 (Warmup Budget)`: Nạp BGE-M3/Reranker mất ~94s; đặt `WARMUP_TIMEOUT_SECONDS` $\ge 110s$. Dùng `asyncio.shield` để worker chạy ngầm tự chuyển `ready`.
- `RULE-1.14 (LiteLLM Virtual Key API)`: Quản trị Virtual Keys: (1) Tránh regenerate (500), dùng delete -> generate. (2) Lấy O(1) qua `return_full_object=true`. (3) Dùng `budget_duration="30d"` (cấm `duration`). (4) Delete nhận mảng `key_aliases`.
- `RULE-1.15 (Account Pool Quorum Guard & Health Probe)`: (1) Dùng `rpm`/`tpm`, cooldown: 60-120s. (2) Quorum Guard dừng cô lập khi `active_count <= 2` hoặc `failed_ratio >= 0.5`. (3) Re-enable qua ChatOps bắt buộc qua Health Probe Gate (HTTP 200).
- `RULE-1.16 (Deep Seams Facade Pattern)`: Khi tách module lớn (>500 dòng), tệp gốc biến thành Facade mỏng re-export 100% symbols bảo đảm zero-regression và 100% test pass.
- `RULE-1.17 (Redis DB Partitioning)`: Redis split: DB 0 LiteLLM, DB 1 `ingest:queue`, DB 2 Context Lake, DB 3 Semantic/Table Cache, DB 4 HITL. Table cache bắt buộc bọc `format_redis_db3_url(raw_url)` chặn ghi nhầm vào DB 1.
- `RULE-1.18 (Zero-VRAM Fast MCP Bridge)`: MCP Server kết nối daemon RAG (:8005) qua Lightweight HTTP Bridge, khởi động ~0.3s, 0 MB VRAM phụ, loại bỏ cold warmup 94s (Pitfall #14).

---

## Miền 2: Code Quality & Testing

- `RULE-2.1 (Null Content in Thinking Models)`: Thinking models trả `content = None` khi reasoning hết quota. Parser dùng `(msg.get("content") or "").strip()` và `max_tokens >= 256` tránh lỗi `NoneType`.
- `RULE-2.2 (Spoke Cleanliness Guard)`: Thư mục `scripts/` khống chế $\le 15$ tệp hợp lệ. Script legacy lưu vào `.md/archive/legacy_scripts/`.
- `RULE-2.3 (Shift-Left Determinism)`: Trước commit/release, bắt buộc chạy `.venv/bin/python -m ccba_harness verify-patch` với 4 chốt chặn (Cleanliness, Import Depth, Flake8, Gateway Endpoints).
- `RULE-2.4 (Poison Budget in Gemini 3.x)`: `thinking_budget < 2048` làm tắt luồng suy luận. Đặt `control_source = "gateway"` để gateway tự chuẩn hóa ($\ge 10001$ Pro, $\ge 16384$ Flash High).
- `RULE-2.5 (Vector DB Parity Lock)`: Kiểm toán RAG bắt buộc chốt Parity: `set(exported_doc_ids) - set(indexed_doc_ids) == empty`.
- `RULE-2.6 (Pre-Lock Validation)`: Timeout/config phải validate trước khi acquire mutex trong async worker. Bọc try-except giải phóng lock ngay nếu lỗi tránh deadlock.
- `RULE-2.7 (Vite ManualChunks & AnimatePresence)`: Tách vendor lớn bằng `manualChunks` hạ bundle < 300 kB. Child trong `<AnimatePresence mode="wait">` bắt buộc gán `key` riêng.
- `RULE-2.8 (Vite Typecheck & Zombie Pruning)`: Cấu hình `"typecheck": "tsc --noEmit"` trên CI và Local Gate. Định kỳ gỡ zombie dependencies giảm phình `node_modules` (-50%).
- `RULE-2.9 (Dual-Requirement File Sync)`: Thêm thư viện mới bắt buộc đồng bộ cả `requirements.txt` và `requirements-ci.txt` tránh crash CI GitHub Actions.
- `RULE-2.10 (Fast-Path Chunker Online LLM Isolation)`: Fast-Path nạp tài liệu sạch tắt sửa bảng/tóm tắt LLM (`TABLE_CORRECT_ENABLED = False`), hạ độ trễ từ 80s+ xuống < 1s.
- `RULE-2.11 (Dynamic Catalog Sizing Invariant)`: Unit test kho tri thức cấm assert kích thước cố định (`assert len == 60`), bắt buộc dùng kiểm tra cận dưới (`assert len >= 60`).
- `RULE-2.12 (KISS Function Size Limit)`: Mọi hàm trong pipeline xử lý chính bắt buộc $\le 50$ dòng. Phân tách thành sub-functions nội bộ có tên mô tả rõ ràng để AI Coding Agents dễ đọc và giảm attention drift.
- `RULE-2.13 (URL-Encoded Path Identifiers)`: Endpoint REST/MCP nhận mã văn bản qua path (`/graph/neighbors/{node_id}`), số hiệu pháp lý có dấu `/` bắt buộc mã hóa `quote(so_hieu, safe="")` tránh 404.

---

## Miền 3: Legal & Data Standards

- `RULE-3.1 (Verbatim Grounding & Provenance)`: Mọi knowledge bundle/văn bản pháp luật phải gắn mã băm SHA-256 đối chiếu công báo gốc, cấm sinh giả định/mock điều khoản.
- `RULE-3.2 (Hard Cryptographic Ingestion Gate)`: Pipeline nạp văn bản (`ingest:queue` / Milvus) bắt buộc chặn mã băm SHA-256 (ADR-0059); chặn đứng gói `TAMPERED`.

---

## Miền 4: Workflows & Review

- `RULE-4.1 (GitHub Actions Billing Fallback)`: Khi GitHub Actions chạm hạn mức chi tiêu, dùng Shift-Left Local Gate làm căn cứ nghiệm thu.
- `RULE-4.2 (Copilot Review Verification)`: Mọi review từ Copilot (`PRR_...`) phải đối soát và giải trình tại `walkthrough.md`.
- `RULE-4.3 (GitHub PR Merge In-Progress Recovery)`: Khi `gh pr merge` lỗi `Merge already in progress`, chờ 10-20s rồi merge qua REST API với `merge_method=squash`.
- `RULE-4.4 (Idempotent Label Provisioning)`: Khâu claim issue gán nhãn `in-progress` phải idempotent: chạy `gh label create in-progress --force --color fbca04 2>/dev/null || true`.
- `RULE-4.5 (Bidirectional LLM Peer Review)`: Phối hợp 2 LLMs (Antigravity & Grok) qua tệp JSON/MD thời gian thực (`status.json`, `grok_cross_review.md`). Tiến hành 2 vòng đối soát: Vòng 1 rà soát blockers, Vòng 2 kiểm chứng chéo AST & test suite.
- `RULE-4.6 (Maskara URL False-Positive Guard)`: Trong tài liệu và log (.md), cấm ghi thô chuỗi URL dạng database vì pre-commit Maskara chặn nhầm Database URL leak. Bắt buộc mô tả ngữ nghĩa hoặc dùng masked placeholder.

---

## Miền 5: Linux, Tooling & Environment

- `RULE-5.1 (Python Executable Ambiguity)`: Trên Ubuntu/Linux, lệnh `python` không tồn tại mặc định. Mọi script/hook phải gọi `python3` hoặc `.venv/bin/python`.
- `RULE-5.2 (Spoke Virtual Key & Credential Isolation)`: (1) Masking khóa bí mật trên CLI runner. (2) Tệp `.env` Spoke bắt buộc gán quyền `0o600`. (3) Chuẩn hóa endpoint Tailscale loại bỏ dư thừa `/v1`.
- `RULE-5.3 (Headless Tauri GUI Daemon)`: App Tauri chạy qua `xvfb-run -a <bin> --minimized`, bật `loginctl enable-linger <user>` để daemon chạy 24/7 sau reboot.
- `RULE-5.4 (PR Release Sync Reconciliation)`: Sau squash-merge: `git checkout master` $\rightarrow$ `git pull origin master` (phân kỳ: `git reset --hard origin/master`) $\rightarrow$ `git branch -D <branch>`.
- `RULE-5.5 (Headless Watchdog Metric Aggregation)`: Watchdog container đọc metrics SoC Temp, RAM, NVMe trực tiếp từ `/proc/meminfo`, `shutil.disk_usage('/')`, `/sys/class/thermal` không cần root.
- `RULE-5.6 (Blackwell GB10 Unified Memory SMI Query)`: GPU GB10 (128GB Unified Memory), `nvidia-smi` trả `[N/A]`. Truy vấn qua `--query-compute-apps=process_name,used_memory` rồi cộng dồn tiến trình.
- `RULE-5.7 (WAL-Safe SQLite Disaster Recovery)`: Nâng cấp container SQLite WAL gọi `sqlite3.backup()` xuất snapshot trước khi tarball. Rollback xóa `-wal`/`-shm` cũ và phục hồi snapshot.
- `RULE-5.8 (Reasoning Model Thinking Token Management)`: Mô hình suy luận (Qwen 3.6), tác vụ JSON (`extract_json`), HyDE, WebUI (`TASK_MODEL`), 34 fallback chains BẮT BUỘC tắt thinking (`enable_thinking: false` trên `rag-core`). Đổi cờ gateway phải gắn `cache_params.namespace` mới để chặn cache hit response rỗng trên Redis DB 0.
