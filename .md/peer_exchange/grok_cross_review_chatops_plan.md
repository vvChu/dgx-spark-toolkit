Tôi sẽ đối chiếu kế hoạch với mã nguồn thật trên nhánh mục tiêu: endpoint ChatOps, cờ tài khoản, và vòng tự phục hồi trong watchdog.Nhánh hiện trùng `master`, kế hoạch chưa được merge. Tôi đọc các hàm re-enable, metric và watchdog để đối chiếu với endpoint thật.**Verdict: CONDITIONAL APPROVE.** Phase 1 được làm sau khi đổi cổng probe và thứ tự gọi. Phase 2, vòng tự warmup mỗi 20 phút, không được vào PR này.

Nhánh `fix/chatops-reenable-and-quota-breaker-resilience` hiện trùng `master` tại `29a760a`. Kết luận dưới đây đối chiếu kế hoạch với `scripts/chatops_daemon.py`, `scripts/smart_watchdog.py`, `pipeline_config.py`, `litellm_config.yaml`, và Antigravity-Manager trong `/home/vvc/Codebase/Antigravity-Manager`.

## Scorecard

| Tiêu chí | Điểm | Lý do ngắn |
|---|---|---|
| Defense Robustness | 3/10 | Warmup đụng Google và có thể khóa lại tài khoản. Vòng tự phục hồi bỏ qua Quorum Guard và khóa tay của operator. |
| Operational Usability | 4/10 | Đổi URL là đúng hướng, nhưng chuỗi warmup rồi toggle không đưa tài khoản trở lại pool. Mọi HTTP khác 200 đang bị gán nhầm thành "challenge chưa giải". |
| KISS Compliance | 5/10 | Sửa metric và tên model là nhỏ. Vòng tự chữa trong watchdog lặp lại cảnh báo đã có và không đụng chính sách 1-strike. |
| Feasibility | 4/10 | `POST /warmup` trên tài khoản `proxy_disabled` trả HTTP 500 `Account is disabled`. Tiêu chí "warmup phải 200" không đạt được với đúng các tài khoản cần mở. |

## Những gì đã kiểm chứng

`/probe` và `/enable` không có trong router. Admin API nằm dưới `/api` (`server.rs` khoảng dòng 980). Hai route thật là:

- `POST /api/accounts/:accountId/warmup`
- `POST /api/accounts/:accountId/toggle-proxy` với body `{"enable": true}`

`probe_gateway_stats()` chỉ loại `disabled`. `probe_antigravity_status()` và `check_quota_pool()` đã xét đủ `proxy_disabled`, `disabled`, `validation_blocked`, và `quota.is_forbidden`. Cờ `is_forbidden` nằm trong `quota`, không nằm ở gốc object. Digest ngày trong watchdog bỏ sót `validation_blocked`.

`text-light-gemma` không có trong `litellm_config.yaml`. Deployment metadata là `text-gemma-12b`. Mapping mặc định trong code Antigravity đã là `internal-background-task` → `gemini-2.5-flash` (`model_mapping.rs` dòng 98). `gui_config.json` trên host đang ghi đè thành `gemini-3.8-flash-high`. File này nằm ngoài git và chứa secret. Không được commit.

Trên đĩa lúc review: 11 file tài khoản, 10 không bị cờ nào, 1 bị `proxy_disabled` kèm `is_forbidden`, lý do `Disabled manually by user`, tuổi khóa khoảng 28 giờ, không có `validation_url`. Con số 8/11 trong đề bài không còn đúng với dữ liệu hiện tại.

## Cổng warmup không phải health probe

`warm_up_account` (`quota.rs` khoảng 944–1014) làm bốn việc khác một probe:

1. Nếu `disabled` hoặc `proxy_disabled`, trả lỗi `Account is disabled`. Handler `admin_warm_up_account` đổi lỗi đó thành HTTP 500. Mọi tài khoản đang bị khóa proxy đều rơi vào nhánh này, nên bước "warmup phải 200 rồi mới enable" không bao giờ mở được khóa.
2. Khi tài khoản còn bật proxy, hàm gọi Google (`loadCodeAssist` rồi quota API). HTTP 403 từ Google được đổi thành `QuotaData.is_forbidden = true`, sau đó `mark_account_forbidden` ghi `proxy_disabled`, `is_forbidden`, và đẩy tài khoản ra khỏi pool trong RAM.
3. Model nào đang 100% thì spawn `generateContent` với prompt `Say hi` qua `/internal/warmup`. Nhánh đó cũng gọi `mark_account_forbidden` khi gặp 403 (`warmup.rs` khoảng 275–292). Đây là request sinh token thật, tốn quota và có thể ăn thêm một 403.
4. HTTP 200 được trả khi task đã được xếp hàng (`Successfully triggered warmup...`) hoặc khi `No warmup needed`, trước lúc các request nền kết thúc. 200 nghĩa là "đã nhận lệnh", không nghĩa là "đã vượt challenge".

Timeout hiện tại của ChatOps là 10 giây. Quota fetch có thể dài hơn. Timeout bị diễn giải thành challenge.

## Challenge thật thì không được gửi upstream

Ba handler `gemini.rs`, `claude.rs`, `openai.rs` cùng một thứ tự: nếu body chứa `VALIDATION_REQUIRED`, `verify your account`, hoặc `validation_url` thì đặt `validation_blocked` trong 10 phút, rồi vẫn gọi `set_forbidden`. Khóa "tạm" bị biến thành khóa vĩnh viễn ngay trong cùng một 403.

Nếu tài khoản vẫn `proxy_disabled`, warmup dừng ở HTTP 500 và chưa đụng Google. Điểm gãy xuất hiện khi đảo thứ tự để warmup chạy được: bật proxy trước, rồi warmup. Lúc đó quota fetch gặp 403 sẽ gọi `mark_account_forbidden` lần nữa. Thêm một request giữa lúc Google đang đòi xác minh trình duyệt là đúng kiểu strike cần tránh.

`GET /api/accounts/:id/quota` cũng không vô hại với challenge. `fetch_quota` biến 403 thành `Ok(is_forbidden=true)`. Nhánh `Ok` của `fetch_quota_with_retry` gọi `clear_validation_blocked`, hàm này ghi đĩa và xóa `validation_url`. Probe bằng quota lên tài khoản đang bị challenge có thể làm mất link xác minh.

Cách an toàn: phân loại trên JSON local trước. Không gọi Google khi có một trong các dấu hiệu `disabled`, `invalid_grant`, `validation_blocked`, `validation_url`, hoặc reason chứa `Verify your account`, `VALIDATION_REQUIRED`, `validation_url`, `unauthorized_client`. Trả hướng dẫn mở link trình duyệt. Không có API nào hoàn tất challenge hộ người dùng.

## Toggle-proxy chưa đủ để đưa tài khoản vào rotation

`toggle_proxy_status` chỉ xóa `proxy_disabled`, `proxy_disabled_reason`, `proxy_disabled_at`. Nó không đụng `quota.is_forbidden`.

`get_account_state_on_disk` coi `quota.is_forbidden == true` là Disabled. `reload_account` nhận `None` thì `remove_account`. Sau toggle thành công, tài khoản vẫn ở ngoài pool nếu `is_forbidden` còn true.

Người ghi `is_forbidden = false` hiện có là `update_account_quota` khi quota mới được fetch thành công. `POST /warmup` không lưu quota sạch xuống đĩa. Vì vậy chuỗi warmup 200 rồi toggle 200 vẫn để tài khoản ngoài rotation.

Thứ tự khớp với bộ lọc hiện có của Antigravity:

1. Đọc `GET /api/accounts` và từ chối local nếu là challenge, `invalid_grant`, hoặc khóa tay. Reason `Disabled manually by user` của tài khoản đang khóa thuộc nhóm này. Vòng tự động mà chỉ bỏ qua chuỗi `VALIDATION_REQUIRED` sẽ bật lại khóa operator đã đặt.
2. Với lỗi tạm: `GET /api/accounts/{id}/quota`, timeout tối thiểu 30 giây, header là admin password. Admin route dùng `force_strict`: sai secret trả 401, route không tồn tại trả 404. 403 của user-token thuộc router `/v1`, không phải bằng chứng route admin sai.
3. Đọc `quota.is_forbidden` trong body. Google 403 được Antigravity bọc thành HTTP 200 kèm `is_forbidden: true`. Chỉ HTTP status là không đủ.
4. Khi body sạch (`is_forbidden` false): `POST /api/accounts/{id}/toggle-proxy` với `{"enable": true}`. Lúc này `proxy_disabled` vẫn còn true trong suốt lúc fetch, nên scheduler và `warm_up_all` vẫn bỏ qua tài khoản. Reload sau toggle mới nhận tài khoản vì cả hai cờ đã sạch.
5. Khi body vẫn `is_forbidden`, hoặc HTTP khác 200: giữ nguyên `proxy_disabled`. Phân loại tin nhắn: 401 là sai credential, 404 là sai route, timeout là mạng, `is_forbidden` là Google còn chặn. Không gán hết vào câu "challenge chưa giải".

`/warmup` để ngoài cổng này. Reset cửa sổ quota là lệnh riêng, sau khi tài khoản đã khỏe.

## Race và Quorum

Không có race hỏng bộ nhớ giữa toggle HTTP và `set_forbidden`: cả hai đi qua `ACCOUNT_INDEX_LOCK` rồi mới sửa pool RAM. Người ghi sau thắng. Hệ quả thực tế là tài khoản nhấp nháy vào rồi bị một 403 hất ra.

Race điều khiển nằm ở warmup nền. `/internal/warmup` giữ access token và gọi upstream ngoài lượt chọn của `TokenManager`. 403 từ request `Say hi` vẫn `mark_account_forbidden` và gỡ tài khoản khỏi session đang sticky (`CacheFirst`). Command GUI `toggle_proxy_status` trong `commands/mod.rs` ghi JSON không lấy `ACCOUNT_INDEX_LOCK`. Healer chạy song song với click GUI có thể mất ghi.

Watchdog đang `sleep(600)`. Nhét healer vào `run_watchdog_cycle` sẽ chặn kiểm tra Docker, vLLM và gateway suốt thời gian Google trả lời. Chu kỳ 20 phút cần mốc `last_run` riêng. Không có mốc thì nó chạy mỗi 10 phút.

Quorum Guard hiện tại (`check_quota_pool`, khoảng dòng 309) đã coi `failed_ratio >= 0.5` hoặc `active <= 2` là sự cố hạ tầng và cố ý không cô lập từng tài khoản. Healer đâm quota fetch hàng loạt đúng lúc IP đang bị WAF sẽ tạo thêm 403 cho cả các tài khoản còn sống. Điều kiện để healer được phép chạy: quorum khỏe, đúng một tài khoản mỗi vòng, tuổi khóa tối thiểu 60 phút, tối đa 3 lần mỗi 24 giờ, bộ đếm ghi ra đĩa. Bộ đếm trong RAM mất sau mỗi lần restart process và sẽ đốt lại từ đầu.

Chính sách 1-strike nằm trong Antigravity-Manager, ngoài repo này. Healer không sửa được nó. Heal thành công, một 403 kế tiếp, khóa lại, 20 phút sau heal lại. Đó là dao động, không phải tự chữa. Việc tách 403 thành challenge, lỗi quyền một model, và lỗi tạm thuộc PR riêng của Antigravity.

## Telegram

`check_quota_pool` đã gửi một tin INFO mỗi email khi email biến mất khỏi danh sách khóa, và tin này không có cooldown. Khóa mới có cooldown 2 giờ. Tin phục hồi thì không.

Thêm câu `✅ [TỰ ĐỘNG PHỤC HỒI] Tài khoản <email>` tạo bản sao. Nhiều tài khoản trong một vòng thành một loạt tin. Tài khoản flap thì lặp mỗi vòng.

Một vòng chỉ một tin, dạng đếm và tỷ lệ pool, liệt kê tối đa năm email. Không thêm kênh gửi thứ hai. Cooldown phục hồi 6 giờ theo email. Lần thử thất bại chỉ vào audit log. Khi quorum fail thì giữ một tin CRITICAL đã có.

## Việc được merge và việc phải tách

Phase 1, sau khi sửa theo thứ tự trên:

- Một helper `account_is_usable`: blocked khi `disabled` hoặc `proxy_disabled` hoặc `validation_blocked` hoặc `quota.is_forbidden`. Dùng chung cho `probe_gateway_stats`, `probe_antigravity_status`, và digest ngày.
- Test `test_probe_gateway_stats_dual` hiện mock `[{"disabled": False}, {"disabled": True}]` và không assert dòng Quota Pool. Fixture mới phải có `proxy_disabled` và `quota.is_forbidden`, nếu không bug đếm tài khoản sống lại mà CI vẫn xanh.
- Test re-enable assert đúng URL, body `{"enable": true}`, và assert không có gọi upstream khi phân loại local từ chối. Case `is_forbidden: true` trong body quota phải giữ tài khoản khóa.
- Default `TEXT_METADATA_MODEL` thành `text-gemma-12b`, sửa comment cùng dòng. Cập nhật `playbooks/llm-api-guide.md`, ADR-0001 và ADR-0003, vì cả ba vẫn ghi tên `text-light-gemma`. Không thấy biến này trong Compose, nên default trong Python có hiệu lực.
- Sửa `internal-background-task` trên host thành `gemini-2.5-flash`, rồi restart Antigravity hoặc lưu qua API config để `update_mapping` chạy. Sửa file một mình không chắc đã vào process. `gemini-2.5-flash-lite` trong bảng map bị đổi thành `gemini-2.5-flash`, nên lite không phải là đường tắt. Xác nhận một background task trong log proxy ra model `gemini-2.5-flash`.

Phase 2 để PR sau, và chỉ sau khi Antigravity ngừng gọi `set_forbidden` cho mọi 403. Điều kiện tối thiểu của healer đã nêu ở mục Quorum.
