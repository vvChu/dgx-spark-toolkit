# Session Learnings & Spoke Patterns

> **Repository:** `dgx-spark-toolkit` (Spoke)  
> **Ngân sách bộ nhớ:** $\le 10.0\text{ KB}$ (Tiered Memory Model - ADR-0030 / ADR-0057)  
> **Kho lưu trữ lịch sử & narratives:** [session_learnings_history.md](archive/session_learnings_history.md)

---

## Miền 1: Architecture & Governance

- `RULE-1.1 (Base Branch Invariant)`: Nhánh chính tại Spoke `dgx-spark-toolkit` là `master`. Mọi lệnh PR (`gh pr create`), merge/sync phải dùng base `master`.
- `RULE-1.2 (Gateway drop_params)`: Bật `litellm_settings.drop_params: true` trong `litellm_config.yaml` chặn HTTP 400 khi OpenAI SDK gửi tham số embedding (`encoding_format: "base64"`) đến Gemini.
- `RULE-1.3 (Reasoning Models Timeout)`: Timeout mô hình suy luận (`claude-opus-4-6-thinking`, `gemini-3.7-flash-high`) cấu hình $\ge 90s - 300s$ tại cả router và deployment tránh timeout chuỗi suy luận dài.
- `RULE-1.4 (Proxy Provider Prefix Invariant)`: Model qua Centralized Proxy bắt buộc dùng prefix `model: openai/<model-id>` tránh `anthropic/` bị LiteLLM thêm `/v1/messages` lỗi 404.
- `RULE-1.5 (Canonical Aliases Sync)`: Cung cấp 3 alias chuẩn hóa (`gemini-flash-latest`, `gemini-reasoning-latest`, `embedding-default`), khai báo đồng thời tại `router_settings.model_group_alias` và `litellm_settings.model_aliases`.
- `RULE-1.6 (Heuristic Tier Preservation)`: Hậu tố `-high`, `-medium`, `-low` (`gemini-3.8-flash-high`) cấp ngân sách tư duy (16k/4k/1k); không map về model gốc trong `custom_mapping` tránh sụt giảm ngân sách suy luận.
- `RULE-1.7 (Zero Quota Circuit Breaker)`: `lock_on_zero_quota: true` trong `gui_config.json` khóa tài khoản cạn quota đến `reset_time` tuần thay vì lùi ngắn hạn (60s-300s), chặn retry 429 vô ích.
- `RULE-1.8 (Prompt Caching & Compression)`: Chế độ `Balance` (KV Cache $\ge 85\%$) cấm nén L2/L3 (Caveman) vì lệch prefix hash; chỉ dùng `compression_level: "low"` (RTK) bảo toàn prefix cache hit.
- `RULE-1.9 (Audit Chain Continuity)`: Chained SHA-256 đọc hash cuối từ disk lúc boot. Unit test mock audit; test audit chuyển `AUDIT_FILE` sang `tmp_path` fixture.
- `RULE-1.10 (Cold-Cache & Multi-Key Gate)`: Đo SLA RAG dùng Cold Cache. Gateway pool test $\ge 3$ keys. Tác vụ real-time dùng chuỗi `claude-haiku-4` $\rightarrow$ `rag-core` GPU (SLA $< 2.0\text{s}$).
- `RULE-1.11 (Warmup Budget)`: Nạp BGE-M3/Reranker mất ~94s; đặt `WARMUP_TIMEOUT_SECONDS` $\ge 110s$. Dùng `asyncio.shield` để worker ngầm tự chuyển `ready`.
- `RULE-1.12 (LiteLLM Virtual Key API)`: Virtual Keys: (1) Tránh regenerate (500, dùng delete $\to$ generate). (2) Lấy O(1) qua `return_full_object=true`. (3) `budget_duration="30d"`. (4) Delete nhận `key_aliases`.
- `RULE-1.13 (Account Pool Quorum Guard & Health Probe)`: (1) Dùng `rpm`/`tpm`, cooldown 60-120s. (2) Quorum dừng cô lập khi `active_count <= 2` hoặc `failed_ratio >= 0.5`. (3) Re-enable qua ChatOps bắt buộc qua Health Probe (HTTP 200).
- `RULE-1.14 (Deep Seams Facade Pattern)`: Khi tách module lớn (>500 dòng), tệp gốc biến thành Facade mỏng re-export 100% symbols bảo đảm zero-regression và 100% test pass.
- `RULE-1.15 (Redis DB Partitioning)`: Redis split: DB 0 LiteLLM, DB 1 `ingest:queue`, DB 2 Context Lake, DB 3 Semantic/Table Cache, DB 4 HITL, DB 5 Healer. Bọc `format_redis_db3_url` chặn ghi nhầm DB 1.
- `RULE-1.16 (Zero-VRAM Fast MCP Bridge)`: Fast MCP Server kết nối daemon RAG (:8005) qua Lightweight HTTP Bridge, khởi động ~0.3s, 0 MB VRAM phụ, loại bỏ cold warmup 94s (Pitfall #14).
- `RULE-1.17 (Dual-Level Quota Schema & Fail-Closed Predicate)`: Predicate kiểm tra hạn mức tài khoản Antigravity (`quota_probe_allows_toggle`) bắt buộc xét cả root level (`body.get("is_forbidden")`) và nested level (`body.get("quota", {}).get("is_forbidden")`), và BẮT BUỘC trả về `False` (fail-closed) nếu body rỗng hoặc thiếu cờ boolean tường minh.
- `RULE-1.18 (Cross-Process MCP Mutual Exclusion Lock)`: MCP Server gọi CLI subprocess nặng (Grok/AGY), `asyncio.Semaphore(1)` chỉ có hiệu lực nội bộ 1 process. BẮT BUỘC dùng `fcntl.flock` trên file khóa chung (`/tmp/*.lock`) kèm `await proc.wait()` dọn dẹp zombie processes.

---

## Miền 2: Code Quality & Testing

- `RULE-2.1 (Null Content in Thinking Models)`: Thinking models trả `content = None` khi reasoning hết quota. Parser dùng `(msg.get("content") or "").strip()` và `max_tokens >= 256` tránh lỗi `NoneType`.
- `RULE-2.2 (Spoke Cleanliness Guard)`: Thư mục `scripts/` khống chế $\le 15$ tệp hợp lệ. Script legacy lưu vào `.md/archive/legacy_scripts/`.
- `RULE-2.3 (Shift-Left Determinism)`: Trước commit/release, bắt buộc chạy `.venv/bin/python -m ccba_harness verify-patch` với 4 chốt chặn (Cleanliness, Import Depth, Flake8, Gateway Endpoints).
- `RULE-2.4 (Poison Budget in Gemini 3.x)`: `thinking_budget < 2048` làm tắt luồng suy luận. Đặt `control_source = "gateway"` để gateway tự chuẩn hóa ($\ge 10001$ Pro, $\ge 16384$ Flash High).
- `RULE-2.5 (Vector DB Parity Lock)`: Kiểm toán RAG bắt buộc chốt Parity: `set(exported_doc_ids) - set(indexed_doc_ids) == empty`.
- `RULE-2.6 (Pre-Lock Validation)`: Timeout/config phải validate trước khi acquire mutex trong async worker. Bọc try-except giải phóng lock ngay nếu lỗi tránh deadlock.
- `RULE-2.7 (Vite Build & Zombie Pruning)`: Tách vendor bằng `manualChunks` hạ bundle < 300 kB. Cấu hình `"typecheck": "tsc --noEmit"` trên CI và Local Gate. Định kỳ gỡ zombie dependencies.
- `RULE-2.8 (Fast-Path Chunker Online LLM Isolation)`: Fast-Path nạp tài liệu sạch tắt sửa bảng/tóm tắt LLM (`TABLE_CORRECT_ENABLED = False`), hạ độ trễ từ 80s+ xuống < 1s.
- `RULE-2.9 (Dynamic Catalog Sizing Invariant)`: Unit test kho tri thức cấm assert kích thước cố định (`assert len == 60`), bắt buộc dùng kiểm tra cận dưới (`assert len >= 60`).
- `RULE-2.10 (KISS Function Size Limit)`: Hàm pipeline chính bắt buộc $\le 50$ dòng. Phân tách thành sub-functions có tên rõ ràng để AI Coding Agents dễ đọc, giảm attention drift.
- `RULE-2.11 (URL-Encoded Path Identifiers)`: Endpoint REST/MCP nhận mã văn bản qua path (`/graph/neighbors/{node_id}`), số hiệu pháp lý có dấu `/` bắt buộc mã hóa `quote(so_hieu, safe="")` tránh 404.

---

## Miền 3: Legal & Data Standards

- `RULE-3.1 (Verbatim Grounding & Provenance)`: Mọi knowledge bundle/văn bản pháp luật phải gắn mã băm SHA-256 đối chiếu công báo gốc, cấm sinh giả định/mock điều khoản.
- `RULE-3.2 (Hard Cryptographic Ingestion Gate)`: Pipeline nạp văn bản (`ingest:queue` / Milvus) bắt buộc chặn mã băm SHA-256 (ADR-0059); chặn đứng gói `TAMPERED`.

---

## Miền 4: Workflows & Review

- `RULE-4.1 (GitHub Actions Billing Fallback)`: Khi GitHub Actions chạm hạn mức chi tiêu, dùng Shift-Left Local Gate làm căn cứ nghiệm thu.
- `RULE-4.2 (Copilot Review Verification)`: Mọi review từ Copilot (`PRR_...`) phải đối soát và giải trình tại `walkthrough.md`.
- `RULE-4.3 (Bidirectional LLM Peer Review)`: Phối hợp 2 LLMs (Antigravity & Grok) qua tệp JSON/MD (`status.json`, `grok_cross_review.md`). 2 vòng đối soát: Vòng 1 rà soát blockers, Vòng 2 kiểm chứng chéo AST & test suite.
- `RULE-4.4 (Maskara URL False-Positive Guard)`: Trong tài liệu và log (.md), cấm ghi thô URL database vì pre-commit Maskara chặn nhầm Database URL leak. Bắt buộc mô tả ngữ nghĩa hoặc dùng masked placeholder.
- `RULE-4.5 (Dual-LLM Adversarial Validation & Tilde Path Traversal)`: Phản biện chéo giữa 2 LLMs bắt buộc kiểm thử thâm nhập thực tế. Tool rule matcher của Grok CLI coi dấu ngã `~` là chuỗi thô (literal), cấm dùng `~/...` trong `--deny`; bắt buộc dùng đường dẫn tuyệt đối chuẩn hóa (`/home/vvc/...`) và loại bỏ công cụ duyệt thư mục (`list_dir`).

---

## Miền 5: Linux, Tooling & Environment

- `RULE-5.1 (Python Executable Ambiguity)`: Trên Ubuntu/Linux, lệnh `python` không tồn tại mặc định. Mọi script/hook phải gọi `python3` hoặc `.venv/bin/python`.
- `RULE-5.2 (Spoke Virtual Key & Credential Isolation)`: (1) Masking khóa bí mật CLI. (2) File `.env` Spoke bắt buộc gán `0o600`. (3) Chuẩn hóa endpoint Tailscale bỏ dư thừa `/v1`.
- `RULE-5.3 (Headless Watchdog Metric Aggregation)`: Watchdog container đọc metrics SoC Temp, RAM, NVMe trực tiếp từ `/proc/meminfo`, `shutil.disk_usage(/)`, `/sys/class/thermal` không cần root.
- `RULE-5.4 (Blackwell GB10 Unified Memory SMI Query)`: GPU GB10 (128GB Unified Memory), `nvidia-smi` trả `[N/A]`. Truy vấn qua `--query-compute-apps=process_name,used_memory` rồi cộng dồn tiến trình.
- `RULE-5.5 (WAL-Safe SQLite Disaster Recovery)`: Nâng cấp container SQLite WAL gọi `sqlite3.backup()` xuất snapshot trước khi tarball. Rollback xóa `-wal`/`-shm` cũ và phục hồi snapshot.
- `RULE-5.6 (Reasoning Model Thinking Token Management)`: Qwen 3.6 suy luận cho JSON/HyDE/WebUI/fallback chains bắt buộc tắt thinking (`enable_thinking: false`). Đổi cờ gateway phải gắn `cache_params.namespace` mới tránh cache hit rỗng trên Redis DB 0.
- `RULE-5.7 (LAN Access Binding & Process Restart Invariant)`: Sửa đổi mạng LAN trong `gui_config.json` bắt buộc restart `antigravity-tools.service` để re-bind socket; tránh `Errno 111 Connection refused` từ container Docker qua Tailscale IP.
- `RULE-5.8 (Hermes Platform Sentinel & Stdio CLI Prompt Ingestion)`: Hermes MCP tool isolation dùng sentinel `no_mcp` trên platform không cấp quyền; gỡ bỏ `skills` khỏi Telegram chặn Prompt Injection; CLI runner truyền prompt qua `stdin` (`-p -`) hoặc file `0600` tránh lỗi `E2BIG` (128 KiB).
