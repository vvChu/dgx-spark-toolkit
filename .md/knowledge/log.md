# Knowledge Activity Log

Nhật ký dòng thời gian ghi nhận các hoạt động nạp, cập nhật và chuẩn hóa tri thức tại repository `dgx-spark-toolkit`.

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

