# Nghiệm thu cuối — PR #79 và PR #80

Ngày: 2026-09-29 05:56 +0700. Đối soát commit `241b961` (PR #79) và `78808d2` (PR #80) với kế hoạch v3, báo cáo `.md/peer_exchange/grok_plan_v3_review.md`, và process trên host.

## Phán quyết

**FINAL ACCEPT** cho PR #79 và PR #80.

Cổng 1 đạt trên hai commit. Cổng 2 đạt trên ba process đang chạy: user unit `dgx-chatops.service` PID `1860646`, `antigravity-tools.service` PID `1864129`, container `smart-watchdog` PID `1865377`.

Lúc 05:54 worktree chuyển sang `refactor/search-pipeline-bge-reranker` tại `8dbc287`. File host `scripts/chatops_daemon.py` trên đĩa lại chứa `POST /api/accounts/{id}/probe` và `/enable` (dòng 803–804). Process `1860646` đã nạp bản `241b961` lúc 05:44 và vẫn chạy bản đó. Restart unit từ worktree này sẽ nạp lại lỗi P0. Container watchdog mount từng file, nên inode đang gắn vẫn là nội dung `78808d2`. Tạo lại container sẽ mount file của `8dbc287` và mất bản healer.

## Scorecard

| Tiêu chí | Điểm | Lý do |
|---|---|---|
| Defense Robustness | 9/10 | Predicate fail-closed ở cả hai file. Test HTTP chặn flat `is_forbidden: true`, nested `true`, body `{}`, và cặp root `False` + nested `True`. |
| Operational Usability | 8/10 | Ba process đúng PID và đứng sau commit. `WATCHDOG_REDIS_URL` trong container đang trống; mã rewrite `REDIS_URL` `/0` sang `/5`. |
| KISS Compliance | 8/10 | Predicate và `is_account_blocked` nằm trong từng file. Container chỉ mount `scripts/smart_watchdog.py`. |
| Feasibility | 9/10 | Pytest 72/72 trên commit, flake8 sạch, CI 4/4 trên cả hai PR. Diff gateway so với `master` rỗng. |

## Cổng 1 — mã và test

`8dbc287` là tổ tiên của `241b961`. `241b961` là tổ tiên của `78808d2`. PR #79 trên GitHub là `241b96187563c39005331abdf5d3675bb588e4f3`. PR #80 là `78808d25ccb322e3759488de2cea6cef9e85b7d8`. Cả hai PR đang mở.

`git diff 8dbc287 241b961 -- services/ai-gateway/litellm_config.yaml` rỗng. `78808d2` cũng rỗng trên file đó. `pipeline_config.py` chỉ đổi default `TEXT_METADATA_MODEL` thành `text-gemma-12b`.

Predicate trong `scripts/chatops_daemon.py` (`241b961`, dòng 800–824) và `scripts/smart_watchdog.py` (`78808d2`, dòng 378–402) là cùng một hợp đồng: dict khác rỗng, xét root và `quota` lồng nhau, `True` hoặc non-bool trả `False`, phải thấy ít nhất một boolean `False`. Stage 1 ChatOps trả `False` và ghi `PRE_CHECK_REJECTED` khi HTTP khác 200, exception, không thấy account, `disabled`, `validation_url`, `validation_blocked`, hoặc reason đã `.lower()` chứa tập từ khóa của `is_eligible_for_auto_heal`, kể cả `unauthorized_client` và `quota.forbidden_reason`. `proxy_disabled` đơn thuần vẫn đi tới quota. Toggle chỉ là `POST /toggle-proxy` với `{"enable": true}`. Hai file commit không còn chuỗi `/probe`, `/enable`, `/warmup`.

Watchdog: `_get_redis_client` dùng nguyên `WATCHDOG_REDIS_URL` khi biến có giá trị, kể cả path `/15`. Biến trống thì `urlparse` đổi path thành `/5`, giữ password. Default `redis DB 5 (port 6379)`. `check_swap_pressure` vẫn tự đọc `REDIS_URL` (default trong mã `/1`). `check_quota_pool` dựng `blocked_ids` bằng `is_account_blocked` (bốn cờ), SCAN `watchdog:healer:first_seen:*`, decode `bytes`, rồi `clear_account_healer_state` cho `healer_ids - blocked_ids` trước `return` của quorum. List rỗng hoặc HTTP khác 200 thì không dọn. `build_daily_digest_message` đếm active bằng `not is_account_blocked`. DB 5 có trong `docs/PITFALLS.md`, `docs/ARCHITECTURE.md`, và `services/rag-service/AGENTS.md`. `docker-compose.yml` thêm `WATCHDOG_REDIS_URL=${WATCHDOG_REDIS_URL}` cạnh `REDIS_URL=${REDIS_CACHE_URL}`.

Pytest chạy trên worktree lúc HEAD còn `78808d2`:

```text
.venv/bin/pytest tests/test_chatops.py tests/test_smart_watchdog.py -q
72 passed in 4.61s
```

`git grep -c '^def test_'` trên commit: `tests/test_chatops.py` 56, `tests/test_smart_watchdog.py` 16. Ca flat `is_forbidden: true` assert `post.call_count == 0` và audit `PROBE_FAILED`. Ca flat `false` assert một `POST` body `{"enable": true}` và audit `SUCCESS`. Ca phục hồi để RAM có `acc_rec_1` và SCAN trả thêm `acc_rec_2`, rồi `delete` được gọi ít nhất hai lần. URL test giữ `/15`, rewrite DB 0 URI sang path `/5` và còn password.

Flake8 với `services/rag-service/.flake8` trên bốn file daemon và test: exit 0, lúc worktree còn đúng commit.

CI trên GitHub, cả hai PR, bốn check SUCCESS: Backend Tests, Frontend Build, Python Lint, Security Audit.

## Cổng 2 — process

| Process | Bằng chứng |
|---|---|
| ChatOps | User unit `dgx-chatops.service` active, enabled. MainPID `1860646`, start 05:44:17 +0700, sau commit `241b961` (05:41:55). Cwd là repo. Lúc 05:48 SHA-256 file trên đĩa và `git show 241b961:scripts/chatops_daemon.py` cùng `3e301a4c510d9110454b91d10012377515230daac4d8514d2d7c2e9fc4ee86d9`. File đó không có `/probe`, `/enable`, `/warmup`. Unit lắng nghe `0.0.0.0:8095`. |
| Antigravity | User unit `antigravity-tools.service` active. PID `1864129`, start 05:45:31 +0700, `LISTEN *:8045`. `GET /healthz` trả `{"status":"ok","version":"4.8.4"}`. `~/.antigravity_tools/gui_config.json` mtime 05:44, trước giờ start. Trong file: `proxy.allow_lan_access = true`, `proxy.custom_mapping.internal-background-task = gemini-2.5-flash`. `GET /api/config` với bearer của ChatOps trả 401, nên mapping được chứng minh bằng file mà process đọc lúc start, không bằng body API. |
| smart-watchdog | Container start 05:45:56 +0700, sau commit `78808d2` (05:43:12). Process là `python /app/smart_watchdog.py`. SHA-256 `/app/smart_watchdog.py` trong container là `a03581ced99736fcf241bec54e2669449e1e8b26d8d570c10260800527ccfce6`, trùng nội dung commit. `GATEWAY_PROXY_URL` là `http://100.83.192.30:8045/v1`. `get_proxy_base_url` bỏ hậu tố `/v1`. Log từ lúc start có banner khởi động và không có `Connection refused`. Vòng `run_watchdog_cycle` chạy trước `sleep 600`; `check_antigravity_tools` chỉ ghi log khi lỗi. |

`WATCHDOG_REDIS_URL` trong container trống. `REDIS_URL` trỏ vào DB 0 (port 6379), không có password. Mã commit coi biến trống là không đặt và đổi path sang `/5`. Đó là đường DB 5 của process này.

## Việc cần giữ sau phán quyết

Process ChatOps và inode watchdog đang chạy mã đã nghiệm thu. Đĩa host lúc 05:56 là `8dbc287`. Trước khi restart `dgx-chatops` hoặc tạo lại `smart-watchdog`, trả `scripts/chatops_daemon.py` và `scripts/smart_watchdog.py` về `78808d2`.
