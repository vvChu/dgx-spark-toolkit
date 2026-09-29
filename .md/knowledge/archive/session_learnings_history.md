# Session Learnings Historical Archive

> **Repository:** `dgx-spark-toolkit` (Spoke)  
> **Tiêu chuẩn:** Tiered Memory Model (ADR-0030 / ADR-0057)  
> **Mục đích:** Lưu trữ đầy đủ lịch sử bài học kinh nghiệm, chi tiết post-mortem và bug narratives từ các phiên làm việc trước khi nén vào Active Working Memory (`session_learnings.md`).

---

## Lưu Trữ Phiên Ngày 2026-09-28 & 2026-09-29

### Miền 1: Architecture & Governance

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
- `RULE-1.19 (Dual-Level Quota Schema & Fail-Closed Predicate)`: Predicate kiểm tra hạn mức tài khoản Antigravity (`quota_probe_allows_toggle`) bắt buộc xét cả root level (`body.get("is_forbidden")`) và nested level (`body.get("quota", {}).get("is_forbidden")`), và BẮT BUỘC trả về `False` (fail-closed) nếu body rỗng, thiếu cờ, hoặc cờ không phải boolean `False` tường minh.
- `RULE-1.20 (Watchdog Healer Dedicated Redis DB)`: Watchdog auto-healing loop bắt buộc cô lập state store tại **Redis DB 5** (hoặc `WATCHDOG_REDIS_URL`). Helper client tự động rewrite URL sang path `/5` khi cấu hình dùng chung cache URL, tuyệt đối không chia sẻ DB 0 hoặc DB 1.
- `RULE-1.21 (Unified Four-Flag Account Blocking Metric)`: Mọi module đếm hoặc lọc tài khoản khả dụng (`is_account_blocked`) BẮT BUỘC kiểm tra đủ 4 cờ: `proxy_disabled`, `disabled`, `validation_blocked`, và `quota.is_forbidden` (kèm fallback root `is_forbidden`), bảo đảm nhất quán 100% giữa `/stats`, `/antigravity_status`, Watchdog Quorum, và Telegram Daily Digest.

### Miền 2: Code Quality & Testing

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

### Miền 3: Legal & Data Standards

- `RULE-3.1 (Verbatim Grounding & Provenance)`: Mọi knowledge bundle/văn bản pháp luật phải gắn mã băm SHA-256 đối chiếu công báo gốc, cấm sinh giả định/mock điều khoản.
- `RULE-3.2 (Hard Cryptographic Ingestion Gate)`: Pipeline nạp văn bản (`ingest:queue` / Milvus) bắt buộc chặn mã băm SHA-256 (ADR-0059); chặn đứng gói `TAMPERED`.

### Miền 4: Workflows & Review

- `RULE-4.1 (GitHub Actions Billing Fallback)`: Khi GitHub Actions chạm hạn mức chi tiêu, dùng Shift-Left Local Gate làm căn cứ nghiệm thu.
- `RULE-4.2 (Copilot Review Verification)`: Mọi review từ Copilot (`PRR_...`) phải đối soát và giải trình tại `walkthrough.md`.
- `RULE-4.3 (GitHub PR Merge In-Progress Recovery)`: Khi `gh pr merge` lỗi `Merge already in progress`, chờ 10-20s rồi merge qua REST API với `merge_method=squash`.
- `RULE-4.4 (Idempotent Label Provisioning)`: Khâu claim issue gán nhãn `in-progress` phải idempotent: chạy `gh label create in-progress --force --color fbca04 2>/dev/null || true`.
- `RULE-4.5 (Bidirectional LLM Peer Review)`: Phối hợp 2 LLMs (Antigravity & Grok) qua tệp JSON/MD thời gian thực (`status.json`, `grok_cross_review.md`). Tiến hành 2 vòng đối soát: Vòng 1 rà soát blockers, Vòng 2 kiểm chứng chéo AST & test suite.
- `RULE-4.6 (Maskara URL False-Positive Guard)`: Trong tài liệu và log (.md), cấm ghi thô chuỗi URL dạng database vì pre-commit Maskara chặn nhầm Database URL leak. Bắt buộc mô tả ngữ nghĩa hoặc dùng masked placeholder.

### Miền 5: Linux, Tooling & Environment

- `RULE-5.1 (Python Executable Ambiguity)`: Trên Ubuntu/Linux, lệnh `python` không tồn tại mặc định. Mọi script/hook phải gọi `python3` hoặc `.venv/bin/python`.
- `RULE-5.2 (Spoke Virtual Key & Credential Isolation)`: (1) Masking khóa bí mật trên CLI runner. (2) Tệp `.env` Spoke bắt buộc gán quyền `0o600`. (3) Chuẩn hóa endpoint Tailscale loại bỏ dư thừa `/v1`.
- `RULE-5.3 (Headless Tauri GUI Daemon)`: App Tauri chạy qua `xvfb-run -a <bin> --minimized`, bật `loginctl enable-linger <user>` để daemon chạy 24/7 sau reboot.
- `RULE-5.4 (PR Release Sync Reconciliation)`: Sau squash-merge: `git checkout master` $\rightarrow$ `git pull origin master` (phân kỳ: `git reset --hard origin/master`) $\rightarrow$ `git branch -D <branch>`.
- `RULE-5.5 (Headless Watchdog Metric Aggregation)`: Watchdog container đọc metrics SoC Temp, RAM, NVMe trực tiếp từ `/proc/meminfo`, `shutil.disk_usage('/')`, `/sys/class/thermal` không cần root.
- `RULE-5.6 (Blackwell GB10 Unified Memory SMI Query)`: GPU GB10 (128GB Unified Memory), `nvidia-smi` trả `[N/A]`. Truy vấn qua `--query-compute-apps=process_name,used_memory` rồi cộng dồn tiến trình.
- `RULE-5.7 (WAL-Safe SQLite Disaster Recovery)`: Nâng cấp container SQLite WAL gọi `sqlite3.backup()` xuất snapshot trước khi tarball. Rollback xóa `-wal`/`-shm` cũ và phục hồi snapshot.
- `RULE-5.8 (Reasoning Model Thinking Token Management)`: Mô hình suy luận (Qwen 3.6), tác vụ JSON (`extract_json`), HyDE, WebUI (`TASK_MODEL`), 34 fallback chains BẮT BUỘC tắt thinking (`enable_thinking: false` trên `rag-core`). Đổi cờ gateway phải gắn `cache_params.namespace` mới để chặn cache hit response rỗng trên Redis DB 0.
- `RULE-5.9 (LAN Access Binding & Process Restart Invariant)`: Antigravity-Tools chỉ lắng nghe `0.0.0.0:8045` khi khởi động với `allow_lan_access: true`. Sửa đổi cấu hình mạng LAN trong `gui_config.json` bắt buộc phải restart `antigravity-tools.service` để re-bind socket; container Docker kết nối qua Tailscale IP sẽ bị `Errno 111 Connection refused` nếu bỏ qua bước restart process.

---

## Bổ sung Phiên [2026-09-29] — Hermes Peer Consultation & Stdio Security Hardening

- `RULE-1.22 (Cross-Process MCP Mutual Exclusion Lock)`: Khi MCP Server điều phối các tác vụ CLI subprocess nặng hoặc mô hình AI độc lập (Grok 4.7 / Antigravity CLI), `asyncio.Semaphore(1)` chỉ có hiệu lực trong phạm vi một tiến trình Python. BẮT BUỘC phải bọc thêm `fcntl.flock` trên file khóa chung cấp OS (`/tmp/*.lock`) và gọi tường minh `await proc.wait()` sau khi gửi tín hiệu `SIGTERM/SIGKILL` để tránh cạn kiệt vRAM/CPU và ngăn chặn triệt để zombie processes.
- `RULE-4.7 (Dual-LLM Adversarial Validation & Tilde Path Traversal)`: Phản biện chéo giữa 2 LLMs (Antigravity & Grok) bắt buộc phải kiểm thử thâm nhập thực tế. Tool rule matcher của Grok CLI coi dấu ngã `~` là chuỗi thô (literal), cấm dùng `~/...` trong `--deny`; bắt buộc dùng đường dẫn tuyệt đối chuẩn hóa (`/home/vvc/...`) và loại bỏ công cụ duyệt thư mục (`list_dir`) để ngăn rò rỉ secret credentials.
- `RULE-5.10 (Hermes Platform Sentinel & Stdio CLI Prompt Ingestion)`: Hermes MCP tool isolation bắt buộc dùng sentinel `no_mcp` trên toàn bộ platform không được cấp quyền (`cli`, `discord`, `cron`); gỡ bỏ `skills` khỏi chat platform (Telegram) để chặn đứng kênh Prompt Injection tạo mã độc gián tiếp sang CLI. Subprocess CLI runner truyền prompt qua `stdin` (`-p -` cho Antigravity) hoặc tệp tạm `0600` (`--prompt-file` cho Grok) để triệt tiêu giới hạn `MAX_ARG_STRLEN` (128 KiB) của nhân Linux.

---

## Bổ sung Phiên [2026-09-29] — Skill Evolution (PR #87) & Antigravity Pool Triage (PR #88)

- `RULE-1.23 (1-Click Google Validation URL & Stage 1 Decoupling)`: Antigravity Tools lỗi challenge (`accounts.google.com/signin/continue`) bắt buộc dùng regex `extract_validation_url()` bóc tách link gốc và render trực tiếp thành nút 1-click URL trên Telegram. Tại Stage 1 Health Probe Gate, phân tách rạch ròi tài khoản bị challenge/block bảo mật với tài khoản do người dùng chủ động tắt (`disabled manually by user`); cho phép tài khoản tắt thủ công đi tiếp sang Stage 2 Quota Probe Gate để kiểm tra hạn mức Google upstream trước khi kích hoạt lại (`toggle-proxy`).
- `RULE-1.24 (Pattern 17 - Subprocess CLI Isolation & Mutex Lock)`: Khi chạy các tác vụ CLI subprocess nặng hoặc ngoại vi qua Agent/Tool, bắt buộc áp dụng Pattern 17: (1) Async-safe non-blocking mutex `fcntl.flock(LOCK_NB)` ngăn chặn starvation của event loop; (2) Chuẩn hóa đường dẫn phía tiến trình cha (`Path(p).resolve()`) trước khi truyền sang subprocess để chặn triệt để path traversal và shell escape; (3) Gán `start_new_session=True` và dọn dẹp theo nhóm tiến trình (`os.killpg(os.getpgid(proc.pid), SIGKILL)`) kèm `proc.wait()` chống cạn tài nguyên vRAM/CPU.
- `RULE-4.8 (Read-Only PR Discovery Invariant & Dirty Tree Guard)`: Bước 0 của quy trình `/ccba-create-pr` bắt buộc ở trạng thái strictly read-only. Nghiêm cấm tuyệt đối việc tự động push hoặc nhảy vào vòng lặp tự sửa lỗi (Step 4 self-healing) khi đang đứng trên nhánh mặc định (`master`/`main`). Bổ sung Dirty Tree Guard kiểm tra `git status --porcelain` trước khi thực hiện bất kỳ thao tác git branch/push nào; nếu còn thay đổi chưa commit phải dừng ngay lập tức và cảnh báo cho kỹ sư.

---

## Bổ sung Phiên [2026-09-30] — Parameter Externalization (ADR-0060) & Hermes Executive MCP (PR #89)

- `RULE-1.25 (Parameter Externalization & SSOT Alias Routing)`: Mọi lời gọi mô hình LLM trong Spoke bắt buộc sử dụng Capability Aliases chuẩn hoá (`ocr-primary`, `ocr-fallback`, `fast-realtime`, `text-auto`, `text-gemma`, `rag-core`), cấm hardcode tên provider model (`gemini-*`, `claude-*`, `gpt-*`). Toàn bộ cấu hình model thực tế do `services/ai-gateway/litellm_config.yaml` quản lý tập trung. Mọi alias mới khai báo bắt buộc phải có chuỗi `fallbacks` dự phòng về `rag-core` (Local GPU Blackwell GB10) để bảo đảm tính sẵn sàng 100% khi proxy ngoài bị rate-limit.
- `RULE-1.26 (Authoritative Server Registry Timeout Capping)`: Khi tiếp nhận đề xuất tác vụ qua ChatOps hoặc MCP Server (`scripts/hermes_executive_mcp.py`), timeout thực thi phải lấy giá trị chặn trên từ server-side registry (`cmd_def.get("timeout_seconds")`). Cấm tuyệt đối cho phép client tự ý nâng timeout (inflation attack) hoặc bypass timeout của hệ thống.
- `RULE-2.12 (AST-Based Model String & IPv4 Linter Invariant)`: Bộ linter tĩnh (`scripts/check_spoke_cleanliness.py`) bắt buộc sử dụng Python `ast` syntax tree walk để quét chuỗi model thô (bỏ qua docstrings) và module `ipaddress` để phát hiện IPv4 không phải loopback/public DNS. Chỉ chấp nhận miễn trừ qua cú pháp tường minh (`# ccba:allow-raw-model`, `# ccba:allow-raw-ip`, `# ccba:allow-raw-model-file`); CẤM dùng `# noqa` làm suy yếu rào chắn.

