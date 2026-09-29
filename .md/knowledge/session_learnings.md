# Session Learnings & Spoke Patterns

> **Repository:** `dgx-spark-toolkit` (Spoke)  
> **Ngân sách bộ nhớ:** $\le 10.0\text{ KB}$ (Tiered Memory Model - ADR-0030 / ADR-0057)  
> **Kho lưu trữ lịch sử & narratives:** [session_learnings_history.md](archive/session_learnings_history.md)

---

## Miền 1: Architecture & Governance

- `RULE-1.1 (Base Branch)`: Nhánh chính Spoke là `master`. Mọi PR (`gh pr create`), merge/sync phải dùng base `master`.
- `RULE-1.2 (Gateway drop_params)`: Bật `litellm_settings.drop_params: true` chặn HTTP 400 khi client gửi tham số embedding không tương thích (`encoding_format: "base64"`).
- `RULE-1.3 (Reasoning Timeout)`: Timeout mô hình suy luận cấu hình $\ge 90s - 300s$ tại router và deployment tránh timeout chuỗi tư duy dài.
- `RULE-1.4 (Proxy Prefix)`: Model qua Centralized Proxy bắt buộc dùng prefix `openai/<model-id>` tránh LiteLLM thêm `/v1/messages` lỗi 404.
- `RULE-1.5 (Canonical Aliases)`: Khai báo alias chuẩn hóa (`gemini-flash-latest`, v.v.) đồng thời tại `router_settings.model_group_alias` và `litellm_settings.model_aliases`.
- `RULE-1.6 (Heuristic Tier)`: Hậu tố `-high`/`-medium`/`-low` cấp ngân sách tư duy (16k/4k/1k); không map về model gốc trong `custom_mapping`.
- `RULE-1.7 (Zero Quota Breaker)`: `lock_on_zero_quota: true` khóa tài khoản cạn quota đến `reset_time` tuần thay vì lùi ngắn hạn (60s-300s), chặn retry 429.
- `RULE-1.8 (Prompt Caching)`: Chế độ `Balance` cấm nén L2/L3 (Caveman) lệch prefix hash; chỉ dùng `compression_level: "low"` bảo toàn KV cache hit $\ge 85\%$.
- `RULE-1.9 (Audit Chain)`: Chained SHA-256 đọc hash cuối từ disk lúc boot. Unit test mock audit; test audit chuyển `AUDIT_FILE` sang `tmp_path`.
- `RULE-1.10 (Cold-Cache Gate)`: Đo SLA RAG dùng Cold Cache. Gateway pool $\ge 3$ keys. Real-time SLA $< 2.0\text{s}$ dùng chuỗi `claude-haiku-4` $\rightarrow$ `rag-core` GPU.
- `RULE-1.11 (Warmup Budget)`: Nạp BGE-M3/Reranker mất ~94s; đặt `WARMUP_TIMEOUT_SECONDS` $\ge 110s$. Dùng `asyncio.shield` để worker tự chuyển `ready`.
- `RULE-1.12 (Virtual Key API)`: Virtual Keys: (1) Delete $\to$ generate thay vì regenerate (500). (2) Lấy O(1) qua `return_full_object=true`. (3) `budget_duration="30d"`. (4) Delete nhận `key_aliases`.
- `RULE-1.13 (Account Quorum & Probe)`: (1) Dùng `rpm`/`tpm`, cooldown 60-120s. (2) Quorum dừng cô lập khi `active_count <= 2` hoặc `failed_ratio >= 0.5`. (3) Re-enable ChatOps bắt buộc qua Health Probe (HTTP 200).
- `RULE-1.14 (Deep Seams Facade)`: Khi tách module lớn (>500 dòng), tệp gốc biến thành Facade mỏng re-export 100% symbols bảo đảm zero-regression và 100% test pass.
- `RULE-1.15 (Redis DB Partitioning)`: Redis split: DB 0 LiteLLM, DB 1 `ingest:queue`, DB 2 Context Lake, DB 3 Semantic/Table Cache, DB 4 HITL, DB 5 Healer. Bọc `format_redis_db3_url` chặn ghi nhầm DB 1.
- `RULE-1.16 (Zero-VRAM Fast MCP Bridge)`: Fast MCP Server kết nối daemon RAG (:8005) qua Lightweight HTTP Bridge, khởi động ~0.3s, 0 MB VRAM phụ, loại bỏ cold warmup 94s (Pitfall #14).
- `RULE-1.17 (Dual-Level Quota Schema)`: `quota_probe_allows_toggle` xét cả root (`is_forbidden`) và nested (`quota.is_forbidden`); fail-closed (`False`) nếu thiếu cờ tường minh.
- `RULE-1.18 (Cross-Process Mutex)`: Subprocess nặng (Grok/AGY) dùng `fcntl.flock` trên `/tmp/*.lock` kèm `await proc.wait()` dọn dẹp zombie processes.
- `RULE-1.19 (1-Click Google URL & Stage 1)`: Antigravity challenge bóc link bằng `extract_validation_url()`. Stage 1 Health Probe tách `disabled manually` với challenge bảo mật.
- `RULE-1.20 (Pattern 17 CLI Isolation)`: Subprocess nặng dùng Pattern 17: Mutex `fcntl.flock`, `Path.resolve()` chặn traversal, và `start_new_session=True` dọn process group.
- `RULE-1.21 (Parameter Externalization)`: Cấm hardcode model (`gemini-*`) và IP (`100.83.*`); dùng alias (`fast-realtime`, `ocr-primary`) và env vars. Alias phải có fallback về `rag-core`.
- `RULE-1.22 (Registry Timeout Cap)`: Đề xuất tác vụ ChatOps/MCP bắt buộc lấy timeout từ server registry (`cmd_def.timeout_seconds`), chặn client timeout inflation.

---

## Miền 2: Code Quality & Testing

- `RULE-2.1 (Null Content in Thinking Models)`: Thinking models trả `content = None` khi reasoning hết quota. Parser dùng `(msg.get("content") or "").strip()` và `max_tokens >= 256` tránh lỗi `NoneType`.
- `RULE-2.2 (Spoke Cleanliness Guard)`: `scripts/` tối đa 15 tệp đếm. Daemon, MCP và crontab ở lại `scripts/`. One-off vào `.md/archive/legacy_scripts/`. Xem `platform_aware_kiss_standard.md`.
- `RULE-2.3 (Shift-Left Determinism)`: Trước commit/release, bắt buộc chạy `.venv/bin/python -m ccba_harness verify-patch` với 4 chốt chặn (Cleanliness, Import Depth, Flake8, Gateway Endpoints).
- `RULE-2.4 (Poison Budget in Gemini 3.x)`: `thinking_budget < 2048` làm tắt luồng suy luận. Đặt `control_source = "gateway"` để gateway tự chuẩn hóa ($\ge 10001$ Pro, $\ge 16384$ Flash High).
- `RULE-2.5 (Vector DB Parity Lock)`: Kiểm toán RAG bắt buộc chốt Parity: `set(exported_doc_ids) - set(indexed_doc_ids) == empty`.
- `RULE-2.6 (Pre-Lock Validation)`: Timeout/config phải validate trước khi acquire mutex trong async worker. Bọc try-except giải phóng lock ngay nếu lỗi tránh deadlock.
- `RULE-2.7 (Vite Build & Zombie Pruning)`: Tách vendor bằng `manualChunks` hạ bundle < 300 kB. CI/Local Gate cấu hình `"typecheck": "tsc --noEmit"`. Định kỳ gỡ zombie dependencies.
- `RULE-2.8 (Fast-Path Chunker Online LLM Isolation)`: Fast-Path nạp tài liệu sạch tắt sửa bảng/tóm tắt LLM (`TABLE_CORRECT_ENABLED = False`), hạ độ trễ từ 80s+ xuống < 1s.
- `RULE-2.9 (Dynamic Catalog Sizing Invariant)`: Unit test kho tri thức cấm assert kích thước cố định (`assert len == 60`), bắt buộc dùng kiểm tra cận dưới (`assert len >= 60`).
- `RULE-2.10 (KISS Function Limit)`: Complexity cảnh báo từ 10, lỗi review từ 15. SLOC > 80 là câu review. Xem `platform_aware_kiss_standard.md`.
- `RULE-2.11 (URL-Encoded Path IDs)`: Endpoint REST/MCP nhận mã văn bản qua path (`/graph/neighbors/{node_id}`), số hiệu pháp lý có `/` bắt buộc `quote(so_hieu, safe="")`.
- `RULE-2.12 (AST Model/IP Linter)`: Linter tĩnh dùng `ast` duyệt syntax tree quét chuỗi model thô (bỏ qua docstring) và `ipaddress` quét IPv4. Miễn trừ qua cú pháp tường minh (`# ccba:allow-raw-model`, `# ccba:allow-raw-ip`); cấm `# noqa`.

---

## Miền 3: Legal & Data Standards

- `RULE-3.1 (Verbatim Grounding & Provenance)`: Mọi knowledge bundle/văn bản pháp luật phải gắn mã băm SHA-256 đối chiếu công báo gốc, cấm sinh giả định/mock điều khoản.
- `RULE-3.2 (Hard Cryptographic Ingestion Gate)`: Pipeline nạp văn bản (`ingest:queue` / Milvus) bắt buộc chặn mã băm SHA-256 (ADR-0059); chặn đứng gói `TAMPERED`.

---

## Miền 4: Workflows & Review

- `RULE-4.1 (GitHub Actions Billing Fallback)`: Khi GitHub Actions chạm hạn mức chi tiêu, dùng Shift-Left Local Gate làm căn cứ nghiệm thu.
- `RULE-4.2 (Copilot Review Verification)`: Mọi review từ Copilot (`PRR_...`) phải đối soát và giải trình tại `walkthrough.md`.
- `RULE-4.3 (Bidirectional LLM Peer Review)`: Phối hợp Antigravity & Grok qua JSON/MD (`status.json`, `grok_cross_review.md`). Vòng 1 rà soát blockers, Vòng 2 kiểm chứng AST & test suite.
- `RULE-4.4 (Maskara URL False-Positive Guard)`: Trong tài liệu và log (.md), cấm ghi thô URL database vì pre-commit Maskara chặn nhầm Database URL leak. Bắt buộc mô tả ngữ nghĩa hoặc dùng masked placeholder.
- `RULE-4.5 (Dual-LLM Adversarial Validation & Path Traversal)`: Grok CLI coi `~` là chuỗi thô (literal), cấm `~/...` trong `--deny`; bắt buộc dùng đường dẫn tuyệt đối chuẩn hóa (`/home/vvc/...`) và loại bỏ `list_dir`.
- `RULE-4.6 (Read-Only PR Discovery & Dirty Tree Guard)`: Bước 0 `/ccba-create-pr` strictly read-only, cấm auto-push hoặc self-heal trên `master`. Dirty Tree Guard chặn tạo PR nếu cây làm việc còn uncommitted changes.

---

## Miền 5: Linux, Tooling & Environment

- `RULE-5.1 (Python Executable Ambiguity)`: Trên Ubuntu/Linux, lệnh `python` không tồn tại mặc định. Mọi script/hook phải gọi `python3` hoặc `.venv/bin/python`.
- `RULE-5.2 (Spoke Virtual Key & Credential Isolation)`: (1) Masking khóa bí mật CLI. (2) File `.env` Spoke bắt buộc gán `0o600`. (3) Chuẩn hóa endpoint Tailscale bỏ dư thừa `/v1`.
- `RULE-5.3 (Headless Watchdog Metrics)`: Container watchdog đọc SoC Temp, RAM, NVMe từ `/proc/meminfo`, `shutil.disk_usage(/)`, `/sys/class/thermal` không cần root.
- `RULE-5.4 (Blackwell GB10 SMI)`: GPU GB10 Unified Memory `nvidia-smi` trả `[N/A]`; truy vấn qua `--query-compute-apps=process_name,used_memory` cộng dồn tiến trình.
- `RULE-5.5 (WAL-Safe SQLite Recovery)`: Nâng cấp container SQLite WAL gọi `sqlite3.backup()` xuất snapshot trước tarball. Rollback xóa `-wal`/`-shm` cũ phục hồi snapshot.
- `RULE-5.6 (Thinking Token Management)`: Qwen 3.6 JSON/HyDE/fallbacks bắt buộc `enable_thinking: false`. Đổi cờ gateway phải gắn `cache_params.namespace` mới.
- `RULE-5.7 (LAN Binding Restart)`: Sửa LAN `gui_config.json` bắt buộc restart `antigravity-tools.service` để re-bind socket tránh Connection refused qua Tailscale IP.
- `RULE-5.8 (Hermes Sentinel & Prompt Ingestion)`: Hermes MCP dùng sentinel `no_mcp`; gỡ `skills` khỏi Telegram chặn prompt injection; CLI runner truyền prompt qua `stdin` tránh `E2BIG`.
