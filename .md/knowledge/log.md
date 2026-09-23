# Knowledge Activity Log

Nhật ký dòng thời gian ghi nhận các hoạt động nạp, cập nhật và chuẩn hóa tri thức tại repository `dgx-spark-toolkit`.

---

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

