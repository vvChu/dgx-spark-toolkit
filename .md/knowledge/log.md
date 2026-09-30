# Knowledge Activity Log

Nhật ký dòng thời gian ghi nhận các hoạt động nạp, cập nhật và chuẩn hóa tri thức tại repository `dgx-spark-toolkit`.

## [2026-09-29] [feat/skills-and-antigravity-pool] | Skill Evolution v1.3/v1.5 & Antigravity Pool Triage v1.2.0 (PR #87 & PR #88 Merged)

- **Nhiệm vụ**: Tiến hóa trực tiếp 2 Kernel Skills (`ccba-create-pr` v1.3.0 và `ccba-llm-pipeline-patterns` v1.5.0 Pattern 17) tại PR #87; nâng cấp cơ chế bảo vệ tài khoản Google qua Antigravity Tools và tối ưu hóa hiển thị ChatOps Triage tại PR #88.
- **Thành phần**:
  - `Skill Evolution (PR #87)`:
    - `ccba-create-pr` v1.3.0: Bổ sung Bước 0.4 Read-Only Discovery Router và Dirty Tree Guard, tuyệt đối không tự push hoặc kích hoạt vòng lặp tự sửa lỗi (Step 4 self-healing) khi đứng trên nhánh mặc định (`master`/`main`).
    - `ccba-llm-pipeline-patterns` v1.5.0: Chuẩn hóa Pattern 17 (Subprocess CLI Isolation & Mutex Lock) với `fcntl.flock(LOCK_NB)`, chuẩn hóa đường dẫn cha `Path.resolve()`, và `start_new_session=True` dọn theo nhóm tiến trình (`os.killpg`).
  - `Antigravity Pool Triage & Google Account Protection (PR #88)`:
    - Bóc tách 1-click Google validation URL qua regex `extract_validation_url()` và render nút liên kết trực tiếp trên thông báo Telegram.
    - Phân loại tài khoản bị chặn thành 3 nhóm rõ ràng: Browser Challenge (cần giải captcha/challenge), Manual Disabled (tắt thủ công), Quota Cooldown (tạm khóa hạn mức).
    - Refine Stage 1 Health Probe: Tách biệt tài khoản tắt thủ công với vi phạm bảo mật, cho phép tài khoản `is_manual_disabled` vượt Stage 1 để kiểm tra hạn mức Google upstream tại Stage 2 Quota Probe trước khi kích hoạt lại (`toggle-proxy`).
    - Bổ sung thanh trực quan trạng thái tài khoản `render_health_bar()` (Unicode block bar) và 4 unit tests mới (`tests/test_chatops.py`, 62/62 tests pass).
    - Cập nhật skill `ccba-infrastructure-manager` lên v1.2.0 và restart `dgx-chatops.service`.
- **Xác thực**:
  - Unit tests: 62/62 chatops tests passed (bao gồm 4 tests mới cho URL parser, blocked breakdown, health bar, manual disabled Stage 1 bypass).
  - Validation: 100% skills vượt qua `python scripts/validate_skills.py` (GPI >= 12.0).
  - Production Daemon: `dgx-chatops.service` running active (PID 580462).
  - Release: Squash & Merge thành công PR #87 (`76f964f`) và PR #88 (`d7eb3ff`).

## [2026-09-29] [fix/chatops-and-watchdog] | Khắc Phục Lỗi P0 Schema, Triển Khai Watchdog Auto-Healing & Phát Hành PR #79 / #80 (FINAL ACCEPT)

- **Nhiệm vụ**: Khắc phục triệt để lỗi P0 flat schema trong quota probe, xây dựng vòng lặp Watchdog Healer tự phục hồi tài khoản hết quota tạm thời, cô lập Redis DB 5, đồng bộ số liệu Quota Pool 4 cờ, vượt qua 2 vòng phản biện đối kháng của Grok 4.7 xhigh (FINAL ACCEPT), phát hành thành công PR #79 và PR #80 vào `master`.
- **Thành phần**:
  - `ChatOps Resilience (PR #79)`: Khắc phục mismatch endpoint re-enable (gọi `POST /api/accounts/{id}/toggle-proxy` với `{"enable": true}`); triển khai 4-stage health probe gate (Local Pre-Check loại trừ challenge-blocked không gọi Google, Quota Probe qua Admin Secret reset `is_forbidden`, Proxy Activation, Audit Log 4 trạng thái); đồng bộ task models (`text-gemma-12b`, `gemini-2.5-flash`).
  - `Watchdog Auto-Healing (PR #80)`: Triển khai vòng lặp auto-healing kiểm tra Quota Pool định kỳ; áp dụng exponential backoff (600s $\to$ 7200s); cô lập hoàn toàn Healer State Store trên **Redis DB 5** (tránh corrupt DB 0 Cache hoặc DB 1 Ingest Queue); dọn dẹp mapping `first_seen` theo `account_id` sau khi tài khoản phục hồi.
  - `P0 Flat Schema Resolution`: Antigravity-Manager trả về flat `QuotaData` (`is_forbidden` ở root level). Triển khai predicate `quota_probe_allows_toggle` kiểm tra cả root và nested, fail-closed khi thiếu cờ. Đồng bộ hàm `is_account_blocked` kiểm tra đủ 4 cờ trên toàn hệ sinh thái.
  - `LAN Access Socket Binding`: Cấu hình `"allow_lan_access": true` trong `gui_config.json` và restart `antigravity-tools.service` để bind `0.0.0.0:8045`, giải quyết dứt điểm lỗi `Connection refused` từ container Docker qua mạng Tailscale.
- **Xác thực**:
  - Unit tests: 72/72 tests passed in 4.66s (56 chatops + 16 watchdog).
  - Flake8: 0 errors, 0 warnings across all daemon and test files.
  - GitHub Actions Dual-Gate CI: 4/4 checks (Backend Tests, Frontend Build, Python Lint, Security Audit) 100% Green trên cả PR #79 và PR #80.
  - Grok 4.7 Adversarial Review: Phê duyệt **FINAL ACCEPT** chính thức (Defense 9/10, Usability 8/10, KISS 8/10, Feasibility 9/10).
  - Runtime Daemons: `dgx-chatops.service`, `antigravity-tools.service`, `smart-watchdog` container hoạt động đồng bộ, không phát sinh lỗi.
  - Release: Squash & Merge PR #79 (`6d4a02b`) và PR #80 (`266377e`), dọn sạch remote/local branches.

## [2026-09-28] [feat/llm-upgrade] | Nâng Cấp Qwen 3.6 35B FP8 & Tối Ưu Hệ Sinh Thái Đa Dịch Vụ (PR #76 Merged)

- **Nhiệm vụ**: Nâng cấp Local Primary LLM từ `Qwen/Qwen3.5-35B-A3B-FP8` lên `Qwen/Qwen3.6-35B-A3B-FP8` trên NVIDIA DGX Spark (Blackwell GB10 128GB Unified Memory), kích hoạt Thinking Preservation với `--reasoning-parser qwen3`, đối soát phản biện cùng Grok 4.7 xhigh, và tối ưu hóa toàn diện hệ sinh thái (AI Gateway, Open WebUI, RAG Service, HyDE).
- **Thành phần**:
  - `Model Upgrade`: Tải và phục vụ `Qwen/Qwen3.6-35B-A3B-FP8` (34.92 GiB, 42 shards) qua vLLM 0.26.0; bổ sung volume mount cache Inductor AOT (`~/.cache/vllm`) và `--reasoning-parser qwen3`.
  - `AI Gateway`: Bổ sung 2 role-based aliases `local-instruct` (ép `enable_thinking: False`) và `local-coder`. Tăng tốc bóc tách JSON từ 5.6s xuống **0.398s (13.5x speedup)**.
  - `Open WebUI`: Cấu hình `TASK_MODEL: local-instruct`, giúp các tác vụ nền nội bộ (tự tạo tiêu đề chat, tóm tắt) hoàn tất trong < 0.4s.
  - `RAG Service & HyDE`: Mặc định tắt thinking trong `extract_json()` và `HyDEGenerator` (`max_tokens=512`), ngăn chặn triệt để hiện tượng cạn kiệt token (`finish_reason: length`) và sinh thành công 1,308 ký tự tài liệu giả định.
  - `Docs & Knowledge`: Ghi nhận `RULE-5.8` trong `session_learnings.md` (giữ ngân sách $\le 10.0$ KB), lưu biên bản phản biện Grok tại `.md/peer_exchange/grok_cross_review_qwen36.md`, và cập nhật báo cáo phát hành tại `.md/knowledge/reports/walkthrough.md`.
- **Xác thực**:
  - Model Throughput: 54.46 tokens/s (Concurrency 1), 137.35 tokens/s (Concurrency 4).
  - Test suite: 527/527 unit tests passed in 13.1s; flake8: 0 errors; secret scanner: 0 leaks.
  - GitHub Actions Dual-Gate CI: 4/4 checks (Backend Tests, Frontend Build, Python Lint, Security Audit) 100% Green.
  - Release: Squash & Merge thành công PR #76 (commit `f92ecb2`), dọn sạch branch cục bộ và remote.

## [2026-09-28] [refactor/ai-native] | Hoàn tất Tái Cấu Trúc AI-Native Codebase (ADR-0005) & Nghiệm Thu Đối Soát Grok

- **Nhiệm vụ**: Thực hiện tái cấu trúc hệ thống `dgx-spark-toolkit` sang kiến trúc AI-Native Codebase theo chuẩn Deep Seams, thiết lập Scoped Progressive Disclosure, phân vùng cách ly Redis DB 3 cho Table Cache, xây dựng Fast MCP Server, ban hành ADR-0005 và nghiệm thu đối soát chéo 2 chiều cùng Grok 4.7 xhigh.
- **Thành phần**:
  - `Task 0`: Sửa assertion tại `test_hub3_bridge.py:76` sang `>= 12` theo RULE-2.11, mở khóa toàn bộ 527 tests xanh.
  - `Task 1`: Tạo 3 tệp `AGENTS.md` (< 40 dòng) cho `services/rag-service/`, `services/ai-gateway/`, và `services/frontend/`.
  - `Task 2`: Phân rã monolith `chunking.py` (894 dòng) thành package `ingestion.chunkers/` (100–240 dòng/file); di chuyển Table Cache sang Redis DB 3 qua helper `format_redis_db3_url(raw_url)`, bảo vệ Redis DB 1 cho `ingest:queue`. Giữ facade `chunking.py` 148 dòng zero-regression.
  - `Task 3`: Phân rã toàn bộ các hàm > 50 dòng trong `search_pipeline.py` và các chunkers thành sub-functions $\le 35$ dòng tuân thủ triệt để KISS (quét AST 82/82 hàm đều $\le 50$ dòng).
  - `Task 4`: Xây dựng Fast MCP Server (`scripts/mcp_server.py`) dạng Lightweight HTTP Bridge kết nối daemon RAG (:8005), 0 MB VRAM phụ, boot ~0.3s. Hỗ trợ 4 tools chuẩn hóa router và URL-encoding cho số hiệu văn bản có dấu `/`.
  - `Task 5`: Tự động xuất schema OpenAPI và API_MODELS ra `.md/schemas/`.
  - `Task 6`: Ban hành `docs/adr/0005-ai-native-codebase-modularization.md`, đồng bộ `ARCHITECTURE.md` và Living Traceability Matrix `docs/adr/TRACEABILITY_MATRIX.md`.
  - `Đối soát Grok`: Kênh bắt tay thời gian thực qua `.md/peer_exchange/`. Grok nghiệm thu chính thức sau 2 vòng kiểm chứng tại `.md/peer_exchange/grok_cross_review.md`.
- **Xác thực**:
  - Unit tests: 527/527 passed in 13.1s (rag-service).
  - Flake8: 0 findings.
  - Maskara Secret Scanner: 0 leaks (PASS).
  - AST Function Length: 82/82 functions $\le 50$ dòng (dài nhất 49 dòng).
  - Git: 6 atomic commits trên nhánh `refactor/ai-native-codebase`, mở thành công Pull Request #76 trên GitHub.

## [2026-09-23] [opt/rag-quality] | RAG Quality Score Optimization (90/100 → 95/100)

- **Nhiệm vụ**: Tối ưu hóa toàn diện chất lượng RAG theo kết quả kiểm toán đối kháng `/boost`, nâng điểm `comprehensive_audit.py` từ 90/100 lên 95/100 (trần toán học tối đa cho 10 file xuất khẩu).
- **Thành phần**:
  - `Dimension A (100/100)`: Nâng cấp `fix_table_gfm_v2` trong `normalizers/tables.py` cho phép ô đầu là số nếu hàng có ký tự chữ và mở rộng độ dài ô `< 2000`, giải quyết dứt điểm lỗi `broken_table` tại `BEP_Template` và `PreBEP_Template` mà vẫn bảo toàn 100% test case numeric. Reprocess 10 file Markdown xuất khẩu sạch bóng lỗi (0% broken).
  - `Dimension C (100/100) & Khử độc`: Nâng cấp `strip_ai_monologue` bóc tách khối suy luận đa dòng `Thinking Process:...`. Sanitize 421 chunk bị nhiễm chuỗi suy luận tiếng Anh trong file JSON xuất khẩu. Bổ sung `_raw_key.get_secret_value()` vá lỗi Pydantic SecretStr trong `backfill_synthetic_queries.py`. Backfill 244 parent chunks thành công với `gemini-3.7-flash-low` qua AI Gateway (độ trễ 1-2s, 0 lỗi 429), nâng tỷ lệ phủ từ 10.0% lên 41.0% (vượt ngưỡng mục tiêu >= 40%).
- **Xác thực**:
  - Comprehensive Audit: A: 100/100, B: 100/100, C: 100/100, E: 80/100 $\rightarrow$ Overall: **95/100**.
  - Unit tests: 425/425 passed in 2.47s (rag-service), 27/27 passed in 4.59s (root).
  - Flake8: 0 errors, 0 warnings.
  - Spoke cleanliness: Exit Code 0 (12/15 scripts, 0 machine-state leaks).

## [2026-09-22] [refactor/arch] | Architecture Refactoring & Quality Hardening (Phase 1 & Phase 2)

- **Nhiệm vụ**: Tối ưu hóa kiến trúc theo chuẩn `/ccba-codebase-design`, hoàn thành trọn vẹn Phase 1 (3 Deepening Opportunities) và Phase 2 (3 Follow-up Hardening & Cleanliness recommendations) sau các vòng kiểm chứng đối kháng `/boost` (`DeepInvestigator`).
- **Thành phần**:
  - `Phase 1`:
    - DocumentStore SSOT: Xóa bỏ hoàn toàn `LifecycleService` (53 LOC shallow wrapper) và `test_lifecycle_service.py`. Hợp nhất luồng `sync_status` vào `DocumentStore`.
    - Export Normalization SSOT: Hợp nhất `strip_ai_monologue`, `strip_random_emojis`, `fix_table_gfm_v2`, `_VN_STUCK_WORDS` vào `normalizers/`. Bổ sung `DataExporter.reprocess_exports()` in-process method. Archive legacy scripts sang `.md/archive/legacy_scripts/`.
    - Layer Decoupling: Triệt tiêu inverted import `from services.hitl_service...` trong `retrieval/search_pipeline.py` bằng Functional Seam `sampler_hook`.
  - `Phase 2`:
    - In-Process Audit Seam: Bổ sung `run_comprehensive_audit()` thread-safe (chỉ redirect `sys.stdout`), timeout 60s qua `asyncio.wait_for(...)` trả về `HTTP 504`, vá lỗi coverage false-positive 7300%, đóng kết nối socket Milvus an toàn trong `finally:`. Xóa bỏ 100% lệnh gọi subprocess khỏi router `admin.py`.
    - Spoke Cleanliness Exit Code 0: Thay thế 4 đường dẫn máy cứng trong `scripts/` bằng `os.path.dirname(...)` động; gắn nhãn `# ccba:allow-machine-path` cho model GPU và `hub_path`. `check_spoke_cleanliness.py` đạt Exit Code 0.
    - Concurrency Fast-Fail: Thêm `_pipeline_lock = asyncio.Lock()` tại `/admin/pipeline/{action}` trả về `HTTP 409 Conflict` khi đang có tác vụ chạy, bảo vệ file backup `.bak`.
- **Xác thực**:
  - `check_spoke_cleanliness.py`: Exit code 0 (12/15 scripts, 0 machine-state leaks).
  - Flake8: 0 errors, 0 warnings.
  - Test suite `rag-service`: 411/411 passed in 2.37s.
  - Root test suite: 24/24 passed in 4.54s.
  - Hub Import Depth: 18 files scanned, 0 violations.

## [2026-09-22] [refactor/deps] | Hoàn thành MAP-SPARK-OSS-DEPENDENCY-20260922 (Modernizing OSS Dependencies)

- **Nhiệm vụ**: Triển khai toàn diện bản đồ định hướng `MAP-SPARK-OSS-DEPENDENCY-20260922` nhằm tối ưu hóa quản lý dependency, bảo vệ kernel phần cứng Blackwell GB10, tăng tốc CI và bịt kín các vết rò rỉ kiến trúc.
- **Thành phần**:
  - `TICK-01`: Tạo `requirements-app.in` và biên dịch `requirements-app.lock` bằng `uv pip compile` với cờ `--no-emit-package` loại trừ hoàn toàn các gói phần cứng (`torch`, `torchvision`, `vllm`, `triton`, `nvidia-*`). Cập nhật `Dockerfile` dùng `pip3 install --no-deps -r requirements-app.lock`.
  - `TICK-02`: Hoàn thiện stubbing `sentence_transformers` và `FlagEmbedding` trong `conftest.py`, gỡ bỏ ~800MB torch khỏi `requirements-ci.txt`, biên dịch `requirements-ci.lock`. Tốc độ test đạt 408 tests trong 1.95s.
  - `TICK-03`: Bịt kín 100% Leaky Seams Milvus & Neo4j trong `pipeline.py`. Thu hồi raw driver export `@property def driver` khỏi `Neo4jRepository`. Đưa toàn bộ việc khởi tạo schema/collection và vòng đời vào `MilvusRepository`, `Neo4jRepository` và `DocumentStore`.
  - `TICK-04`: Tạo script chuẩn hóa `scripts/check_dependency_updates.sh` hỗ trợ kiểm tra outdated theo mô hình 3 Tiers và quét an ninh tự động (`pip-audit` + `npm audit --omit=dev --audit-level=critical`). Tích hợp job `security-audit` vào `.github/workflows/ci.yml`.
- **Xác thực**:
  - 408/408 unit tests pass 100% trong 1.95s.
  - Flake8 0 lỗi, ESLint 0 lỗi, Vite build frontend thành công trong 2.43s.
  - `scripts/check_dependency_updates.sh --audit` và `--outdated` chạy thành công (exit 0).
  - Bản đồ định hướng `map.md` đạt 100% hoàn thành (4/4 tickets đóng).

---

## [2026-09-22] [release/proposal] | Merged PR #324 (Deep Seam Legal OCR Normalizer) into Hub


- **Nhiệm vụ**: Hoàn tất quy trình đóng góp tính năng từ Spoke `dgx-spark-toolkit` lên Central Hub `ccba-agent-platform`, nghiệm thu và phát hành PR #324 theo quy chuẩn OKF v2.0 & ADR-0045/ADR-0058.
- **Thành phần**:
  - Double-Pass Adversarial Review: Thẩm định 3 ứng viên, loại bỏ DGX-ChatOps (Bounded Context) và Governance Rules (leaks), phê duyệt và cắt tỉa dead-wood cho Deep Seam Legal OCR Normalizer.
  - Porting & Facade: Chuyển giao 5 module chuẩn hóa OCR văn bản pháp luật vào `packages/ccba-legal-intel/src/ccba_legal/normalizers/`, nâng cấp facade `Cleaners.normalize_legal_text()`.
  - Issue & PR: Mở Hub Issue #322 và PR #324 (`proposal/legal-ocr-normalizer`), vượt qua 7/7 CI checks 100% Green, Squash & Merge vào `main` (commit `d2bcc09f`).
  - Downstream Closed-Loop Sync: Đồng bộ Hub `main` về Spoke qua `sync_spoke.py --apply` (1 mới, 22 cập nhật), cài đặt editable `ccba-legal-intel` tại Spoke venv, kiểm chuẩn shift-left.
- **Xác thực**:
  - Test suite Hub: 40/40 tests `test_text_normalizer.py` 100% PASS.
  - Spoke import: `from ccba_legal.normalizers import TextNormalizer` & `Cleaners.normalize_legal_text` hoạt động chính xác.
  - Shift-left gate: `check_hub_import_depth.py` 100% PASS (0 vi phạm).

---

## [2026-09-22] [learn/ops] | Dynamic Version Gate, Audit Chaining & Infrastructure Manager Expansion

- **Nhiệm vụ**: Chuẩn hóa và ban hành các quy tắc kỹ thuật, tri thức phiên làm việc và kỹ năng quản lý hạ tầng theo đề xuất học tập đã phê duyệt (`learning_proposal.md`).
- **Thành phần**:
  - Ban hành Rules 13 - 17 trong `.agents/rules/codebase-engineering-rules.md`: Dynamic Version Gate, Audit Chain Continuity & Test Isolation, WAL-Safe SQLite Backup & Alpine Rollback, Zombie Process Elimination, NVIDIA Blackwell GB10 Unified Memory SMI Query.
  - Bổ sung `RULE-1.9`, `RULE-1.10`, `RULE-5.6`, `RULE-5.7` (High-Density) vào `.md/knowledge/session_learnings.md`, đảm bảo nghiêm ngặt ngân sách bộ nhớ $\le 10.0$ KB (ADR-0030/ADR-0057).
  - Nâng cấp kỹ năng `.agents/skills/infrastructure-manager/` (`SKILL.md` và `TOOL_REGISTRY.md`): Tích hợp dịch vụ `dgx-chatops` (:8095), Open WebUI (:3001), kịch bản `update-openwebui.sh`, `chatops_daemon.py` và 5 lệnh Telegram.
- **Xác thực**:
  - Cú pháp YAML: `scripts/chatops_commands.yaml` & `SKILL.md` frontmatter 100% hợp lệ.
  - Unit test: `.venv/bin/pytest tests/test_chatops.py` (20/20 passed).
  - Shift-left cleanliness: `check_spoke_cleanliness.py` & `check_hub_import_depth.py` 100% PASS.
  - CCBA Harness: `.venv/bin/python -m ccba_harness verify-patch --preset doc` 100% PASS trên `session_learnings.md` và `log.md`.
  - Ngân sách bộ nhớ: `wc -c < .md/knowledge/session_learnings.md` $\le 10240$ bytes.

---

## [2026-09-20] [ops/monitoring] | Smart Watchdog Telegram Integration & Daily Digest

- **Nhiệm vụ**: Tích hợp giám sát thời gian thực cho Antigravity Tools (:8045), Quota Pool và Báo cáo hoạt động định kỳ (Daily Digest) kèm thông số phần cứng DGX Spark và Top Models qua Telegram bot `@RAG_Ingestion_Bot`.
- **Thành phần**:
  - Cập nhật `docker-compose.yml` chuyển tiếp biến `GATEWAY_PROXY_URL` và `GATEWAY_PROXY_KEY` cho container `smart-watchdog`.
  - Nâng cấp `scripts/smart_watchdog.py`: Thêm kiểm tra liveliness `:8045/healthz`, cảnh báo cạn kiệt pool tài khoản, bóc tách Top 2 models tiêu thụ token, đo lường RAM/NVMe/SoC Temp và phát Daily Digest lúc 08:00 sáng.
  - Thử nghiệm gửi tin nhắn mẫu đến Telegram: Thành công 100% (`Telegram test send result: True`).
  - Bổ sung `RULE-5.5` vào `session_learnings.md`.
- **Xác thực**:
  - `ccba-harness verify-patch --preset doc` 100% PASS.
  - `scripts/check_spoke_cleanliness.py` & `scripts/check_hub_import_depth.py` 100% PASS.

---

## [2026-09-20] [release] | Release PR #53 & Antigravity Tools v4.7.8 Integration

- **Nhiệm vụ**: Thực thi release PR #53 tích hợp toàn bộ giải pháp nâng cấp Antigravity Tools v4.7.8 và tối ưu AI Gateway vào `master`.
- **Thành phần**:
  - Merge PR #53 vào `master` qua Squash & Merge (Commit `1fe7901`).
  - Phục hồi sự cố merge in-progress lock trên GitHub API qua direct REST call `PUT /pulls/53/merge`.
  - Dọn dẹp branch remote `docs/antigravity-v478-retrospective` và branch cục bộ, đồng bộ `master` fast-forward.
  - Bổ sung `RULE-4.3` và `RULE-5.4` vào `session_learnings.md`.
- **Xác thực**:
  - `ccba-harness verify-patch --preset doc` 100% PASS.
  - `scripts/verify_gateway_endpoints.py` 100% PASS.
  - `scripts/check_spoke_cleanliness.py` & `scripts/check_hub_import_depth.py` 100% PASS.

---

## [2026-09-20] [governance/ops] | Antigravity Tools v4.7.8 Upgrade & AI Gateway Optimization

- **Nhiệm vụ**: Khắc phục sự cố giáng cấp ngầm (CR-SPARK-20260915-01), nâng cấp Antigravity Tools lên v4.7.8, cấu hình tối ưu hóa 24/7 theo Wayfinding Map.
- **Thành phần**:
  - `CR-SPARK-20260915-01`: Minh bạch hóa response header (`x-litellm-model-group`), nâng timeout 90s cho `gemini38-flash-high-base` và `claude-opus-4-6-thinking`.
  - Nâng cấp `antigravity-tools` từ v4.6.9 lên v4.7.8 (dpkg + symlink `.local/bin` + sync git branch `main`).
  - Độc lập hóa daemon qua `/usr/bin/xvfb-run -a`, kích hoạt Linux Linger `Linger=yes` cho user `vvc` duy trì service 24/7.
  - Tối ưu hóa cấu hình `gui_config.json`: Chế độ `Balance` (Cache Hit 85%+, Fast Failover 50ms), Quota Breaker (`lock_on_zero_quota = true`), 7-Day Warmup Scheduler, Thinking Budget Gateway Control, khống chế lưu trữ SQLite 1.0 GB + 30% Sliding Window.
  - Phản biện kiến trúc: Từ chối nén L2 Caveman để bảo vệ Prompt Caching, không map đè `gemini-3.8-flash-high` để giữ heuristic tier.
- **Tài liệu**:
  - Bản đồ Wayfinding: `.md/wayfinder/antigravity-tools-optimization/map.md` (6 tickets TICK-01 -> TICK-06 completed).
  - Báo cáo phản biện: Double-Pass Adversarial Review.
  - Tiêu chuẩn tri thức: `.md/knowledge/session_learnings.md` (bổ sung RULE-1.6, 1.7, 1.8, 2.4, 5.3).
- **Xác thực**:
  - Live Endpoints: `scripts/verify_gateway_endpoints.py` 100% PASS (200 OK cho claude-opus, gemini-3.8-flash, embeddings, aliases).
  - Health endpoint `:8045/healthz` 100% PASS.
  - E2E Test Suite `:8090` -> `:8045` 100% PASS.

---

## [2026-09-17] [release] | Release Issue #51 & AI Gateway Hardening

- **Nhiệm vụ**: Hoàn thành Issue #51, mở PR #52 và thực thi release tích hợp vào `master`.
- **Thành phần**:
  - `drop_params: true` toàn cục ngăn chặn HTTP 400 trên OpenAI SDK.
  - Timeout 300s cho các mô hình suy luận sâu (`gemini-3.8-flash-high`, `claude-opus-4-6-thinking`).
  - Fallback group luân chuyển `gemini-embedding-2` $\leftrightarrow$ `gemini-embed`.
  - Canonical aliases: `gemini-flash-latest`, `gemini-reasoning-latest`, `embedding-default`.
- **Tài liệu**:
  - Báo cáo nghiệm thu: `.md/knowledge/reports/walkthrough.md`
  - Tiêu chuẩn tri thức: `.md/knowledge/session_learnings.md` (5 Miền Kiến Trúc ADR-0057)
- **Xác thực**:
  - `.venv/bin/python -m ccba_harness verify-patch` 100% PASS.
  - Live endpoints test qua `scripts/verify_gateway_endpoints.py` 100% PASS.

---

## [2026-09-17] [skill-evolution] | Upgrade ccba-create-pr to v1.2.0

- **Kỹ năng**: `.agents/skills/ccba-create-pr/SKILL.md` (v1.1.0 $\rightarrow$ v1.2.0).
- **Mục tiêu**: Loại bỏ hardcode `--base main`, tự động phát hiện nhánh chính (`main` hoặc `master`) qua `git symbolic-ref refs/remotes/origin/HEAD` và `rev-parse`.
- **Phạm vi tác động**:
  - Bước 0 (Main Branch Guard): Nhận diện `$DEFAULT_BRANCH` để kiểm tra commits dở dang và tách nhánh hồi tố.
  - Bước 3 (PR Creation): Tự động gán `--base "$DEFAULT_BRANCH"` cho `gh pr create` và `git log`.
- **Xác thực**:
  - `ccba-harness validate-skill --file ... --enforce-gpi` 100% PASS.
  - `ccba-harness verify-patch` 100% PASS.

---

## [2026-09-29] [retrospective] | Hermes Peer Consultation Hardening & Session Retrospective

- **Nhiệm vụ**: Chuẩn hóa và thiết lập cơ chế Peer Consultation (Tham vấn Grok 4.7 & Antigravity) an toàn 100% cho Hermes Agent qua Telegram.
- **Thành phần**:
  - Triển khai Dedicated Stdio MCP Server `peer_consultant.py` với `fcntl.flock` cross-process locking.
  - Thiết lập Sandbox Profile độc lập cho Antigravity (`agy-home`) và Grok (`grok-home`) với cấm tuyệt đối `write_file(*)`, `command(*)`, và đường dẫn tuyệt đối cho deny rules.
  - Phân quyền Telegram Platform Toolset cách ly: sentinel `no_mcp` trên toàn bộ các platform khác, loại bỏ `skills` khỏi Telegram chặn Prompt Injection.
  - Chuyển cơ chế nạp prompt sang `stdin` (`-p -`) và tệp tạm `0600` triệt tiêu giới hạn `E2BIG` (128 KiB).
- **Tài liệu**:
  - Báo cáo phản biện Grok: `.md/peer_exchange/grok_cross_review_peer_consultation_results.md`
  - Walkthrough: `.md/knowledge/reports/walkthrough.md` và `walkthrough_hermes_peer_consultation_mcp.md`
  - Tiêu chuẩn tri thức: `.md/knowledge/session_learnings.md` (bổ sung RULE-1.18, 4.5, 5.8; lưu trữ lịch sử tại `archive/session_learnings_history.md`)
- **Xác thực**:
  - Live dispatch test qua Hermes Registry 100% PASS.
  - Canary Secret Deny test (Grok Deny Engine chặn đọc `/home/vvc/.ssh/id_ed25519.pub`) 100% PASS.
  - `hermes-gateway.service` active & running suốt đêm (>6h) không rò rỉ bộ nhớ.
---

## [2026-09-30] [retrospective] | Parameter Externalization (ADR-0060) & Hermes Executive MCP (PR #89)

- **Nhiệm vụ**: Thực thi 10 chỉ thị phản biện của Grok 4.7 xhigh về Parameter Externalization & Dynamic Scale Invariant (ADR-0060), triển khai Hermes Executive Ops MCP, và bảo vệ nhánh chính.
- **Thành phần**:
  - Khử 100% hardcoded model identifiers (`gemini-*`, `claude-*`) chuyển sang capability aliases (`ocr-primary`, `fast-realtime`, `text-auto`, `rag-core`) với SSOT `litellm_config.yaml`.
  - Khử 100% hardcoded IP (`100.83.192.30`, `100.79.241.120`) và user home paths qua biến môi trường.
  - Thiết lập chuỗi fallback `fast-realtime` $\to$ `text-gemma` $\to$ `rag-core` (Qwen 35B Local GPU) zero-downtime khi proxy ngoài rate-limit.
  - Nâng cấp `scripts/check_spoke_cleanliness.py` với AST model leak detector và `ipaddress` IPv4 detector (đạt chuẩn 15/15 script budget, 0 model leaks, 0 IP leaks, 0 path leaks).
  - Triển khai `scripts/hermes_executive_mcp.py` và bộ 27 bài kiểm thử bảo mật `tests/test_executive_ops_mcp.py`.
- **Tài liệu**:
  - Walkthrough: `.md/knowledge/reports/walkthrough.md`
  - Tiêu chuẩn tri thức: `.md/knowledge/session_learnings.md` (bổ sung RULE-1.21, RULE-1.22, RULE-2.12; duy trì kích thước 9.9 KB $\le 10.0$ KB)
  - Pull Request: PR #89 đã squash-merge thành công vào `master`.
- **Xác thực**:
  - 110/110 root unit tests PASS, 604/604 rag-service tests PASS, 0 flake8 errors, 5/5 bundle budgets PASS.
  - Dual-Gate CI 4/4 checks green.

---

## [2026-09-30] [governance/security] | Hermes SOUL Hardening & Call Budget Peer Review (FULL_ACCEPTANCE)

- **Nhiệm vụ**: Phối hợp đối soát tự động với Grok 4.7 xhigh, khắc phục triệt để nguy cơ nghẽn hàng đợi (Resource Starvation / Sequential Timeout Loop) trong `peer_consultant.py` và khử rò rỉ IP thô trong `SOUL.md`.
- **Thành phần**:
  - `SOUL.md`: Khử địa chỉ IP Tailscale thô theo RULE-1.21 & ADR-0060, giữ nguyên chính sách Zero-Inbound và 5 quy tắc Executive Operations.
  - `~/.hermes/mcp/peer_consultant.py`: Thay thế mô hình sliding window tính lúc bắt đầu bằng Quỹ 2 lần gọi (Admit Budget) + Khoảng yên 180s (Quiet Cooldown) tính từ lúc lần gọi làm đầy quỹ kết thúc, từ chối tức thì trước semaphore/lock, ngăn chặn triệt để vòng lặp 30 turns treo máy 75 phút.
  - Phán quyết đối kháng: Grok 4.7 xhigh nghiệm thu toàn diện **`FULL_ACCEPTANCE`** (29/29 tests đối kháng PASS).
- **Tài liệu & Trạng thái**:
  - Báo cáo phản biện: `.md/peer_exchange/grok_final_acceptance_hermes_hardening.md`
  - Bắt tay tác tử: `.md/peer_exchange/ANTIGRAVITY_TO_GROK.md` mục 7
  - Trạng thái: `.md/peer_exchange/status.json` (`hermes_hardening_review.full_acceptance = true`)
- **Xác thực**:
  - 110/110 root unit tests PASS (8.53s).
  - Spoke Cleanliness Linter 100% PASS (0 IP leaks, 0 model leaks, 15/15 script budget).
  - Test mô phỏng Call Budget độc lập trên môi trường Hermes Python 100% PASS.

