# Hermes Agent — lịch sử, năng lực và quản trị an toàn

Ngày đối chiếu: 2026-09-28. Đối tượng là Hermes Agent của Nous Research
([tài liệu](https://hermes-agent.nousresearch.com/docs),
[mã nguồn](https://github.com/NousResearch/hermes-agent)).
Đây không phải Hermes JavaScript engine của Meta. Không có nguồn sơ cấp đã đọc
xác nhận agent này chính là dòng mô hình Nous Hermes hoặc OpenHermes.

Máy và repo `dgx-spark-toolkit` không có một bản cài Hermes Agent, nên báo cáo
này là lịch sử sản phẩm và cách vận hành an toàn, không phải nhật ký của một
instance đang chạy.

Trạng thái chứng cứ: các mục dưới đây bám `SECURITY.md` trên `main`, trang
[Security](https://hermes-agent.nousresearch.com/docs/user-guide/security),
release ổn định mới nhất, và advisory CVE-2026-53870 — đều được đọc trực tiếp
ngày 2026-09-28. Các mốc release cũ hơn và một số giới hạn của checkpoint,
managed scope, iron-proxy, skill và API server lấy từ đợt nghiên cứu đã cross-check
cùng ngày; chỗ hai tài liệu lệch nhau được ghi rõ, không được gộp thành một sự thật.

## Chiến lược khi tự host trên Linux đang giữ dữ liệu nhạy cảm

Chính sách của dự án chỉ công nhận **một ranh giới chịu lực trước một mô hình
đối nghịch: cô lập ở mức hệ điều hành**. Cổng duyệt lệnh, redaction, bộ lọc mẫu
và allowlist công cụ là heuristic trong process. Chúng chặn nhầm lẫn khi mô hình
còn hợp tác. Chúng không phải lớp giam.

Có hai tư thế cô lập, và chúng không thay nhau:

1. **Cô lập terminal backend** (Docker, Singularity, Modal, Daytona, Vercel
   Sandbox, SSH). Chỉ giam lệnh shell và thao tác file đi qua shell. Không giam
   process Python của agent: `execute_code` (subprocess trên host theo
   `SECURITY.md`), process con MCP, nạp plugin, hook, và skill được import vào
   interpreter.
2. **Bọc cả cây process.** Mọi đường — shell, thực thi mã, MCP, file, plugin,
   hook, skill — chịu cùng chính sách filesystem, mạng và process. Dự án hỗ trợ
   hai cách: image Docker và Compose của Hermes, hoặc
   [NVIDIA OpenShell](https://github.com/NVIDIA/OpenShell) (sandbox theo phiên,
   policy mạng lớp 7, syscall, định tuyến inference; credential lấy từ Provider
   store và không nằm trên filesystem của sandbox).

Tư thế được hỗ trợ khi agent đọc nội dung người vận hành không kiểm soát
(web, email, kênh nhiều người, MCP lạ), hoặc khi triển khai production / dùng
chung, là **bọc cả cây process**. Chạy backend local với đầu vào không tin cậy,
hoặc chọn sandbox terminal rồi kỳ vọng nó giam các đường không đi qua shell,
nằm ngoài tư thế đó.

Với kho tài liệu nội bộ (ví dụ văn bản pháp lý) trên cùng máy:

- Chạy agent trong container chính thức, user không phải root. Image chính thức
  đã làm vậy. Không chạy gateway bằng root.
- Không mount kho tài liệu vào workspace của agent. Không đặt `terminal.cwd`
  lên thư mục nhạy cảm.
- `terminal.backend: docker` là lớp cho lệnh shell, không phải thay cho việc bọc
  cả process. Trang Security còn ghi rằng backend container **bỏ** kiểm tra lệnh
  nguy hiểm, vì container được coi là ranh giới.
- Để API server tắt nếu không có người tiêu thụ cụ thể. Khi bật, mọi request
  có `API_SERVER_KEY` dùng toàn bộ toolset, gồm terminal, và Jobs API tạo rồi
  chạy cron.
- Mỗi adapter lộ mạng phải có allowlist. Không đặt
  `GATEWAY_ALLOW_ALL_USERS=true` và không đặt cờ allow-all theo từng nền tảng.
  Không đưa gateway hoặc API ra internet công cộng khi chưa có VPN, Tailscale
  hoặc firewall.
- Trong một adapter, `SECURITY.md` nói mọi caller đã nằm trong allowlist được
  tin ngang nhau, và khuyên tách instance nếu cần phân quyền. Trang messaging
  còn mô tả quyền lệnh admin và regular-user; hai chỗ này chưa được đối chiếu
  đến từng dòng code. Cách vận hành an toàn vẫn là không đưa người không tin
  cậy vào allowlist, và tách profile hoặc instance khi cần tách quyền.
- Giữ `approvals.mode` ở `smart` hoặc `manual`. Không `off`, không `--yolo`,
  không `HERMES_YOLO_MODE=1`. Giữ `cron_mode`, `single_query_mode` và
  `unattended_mode` ở `deny`.
- Thêm `approvals.deny` cho lệnh không bao giờ được chạy (`git push --force*`,
  pipe sang shell). Đó là policy trên chuỗi lệnh, không phải sandbox của OS:
  biến, alias, binary đổi tên và script vẫn có thể đi đường khác.
- Tắt toolset không phục vụ việc cần làm (`hermes tools` hoặc
  `agent.disabled_toolsets`): computer use, trình duyệt, kho đăng nhập, sinh
  ảnh, và các toolset khác không có việc.
- Không thêm khóa nhà cung cấp hay token gateway vào `terminal.env_passthrough`
  hoặc `terminal.docker_forward_env`. Biến mà skill khai báo trong
  `required_environment_variables` vẫn được chuyển vào `execute_code`, terminal
  local, Docker và Modal sau khi skill được nạp.
- Credential để ở file credential của operator, quyền chặt, không ghi vào config
  chính và không đưa vào git. Dưới OpenShell thì dùng Provider store.
  `chmod 600` cho `~/.hermes/.env` nằm trong checklist trang Security.
- Skill và plugin bên thứ ba chỉ cài sau khi đọc mã Python và script. Skill chạy
  Python tùy ý lúc import. Skills Guard chỉ là công cụ hỗ trợ đọc.
- Nếu vẫn dùng vòng tự ghi skill và memory: bật duyệt ghi và bật scanner cho
  skill do agent tạo trước khi để bước nền chạy. Trang skill mô tả ghi tự do khi
  công tắc duyệt tắt; release v0.21.0 nói file chỉ dẫn agent luôn cần duyệt ghi.
  Hai mô tả này chưa được chứng minh là đã thống nhất. Kiểm tra công tắc trên
  đúng bản đang cài.
- Không giao cron hoặc Jobs API cho phiên không có người duyệt. Timeout duyệt
  lệnh mặc định 300 giây và **từ chối** nếu không có người trả lời.
- Cập nhật bằng `hermes update` (bản git) hoặc image gắn tag ổn định. Không chạy
  bản canary trên máy giữ dữ liệu.
- Checkpoint, managed scope và iron-proxy không phải lưới đủ cho mọi backend.
  Checkpoint tắt mặc định và không rollback path nằm trong container terminal.
  Managed scope cưỡng chế bằng quyền file, không chặn agent khi process chạy
  root hoặc ghi được thư mục managed. iron-proxy tắt mặc định, ở bản tài liệu
  đã đọc chỉ nối Docker, và không chống host đã bị chiếm.

Việc ghép cặp user trên image Docker phải chạy đúng user `hermes`, nếu không
file approve mode `0600` thuộc root sẽ bị gateway bỏ qua:

```bash
docker exec -u hermes hermes-agent hermes pairing approve telegram ABC12DEF
```

## Lịch sử phát hành đã kiểm chứng

Bảng này là các mốc có release note hoặc advisory đã đọc, không phải mọi bản
nằm giữa.

| Phiên bản | Tag | Thời điểm | Việc đã ghi trong nguồn |
| --- | --- | --- | --- |
| v0.2.0 | `v2026.3.12` | 2026-03-12 | Bản tag đầu tiên kể từ nền tảng pre-public v0.1.0. Hardening: path traversal, shell injection, symlink, prompt-injection bypass, quyền file 0600/0700. |
| v0.5.0 | `v2026.3.28` | 2026-03-28 | “The hardening release”: hơn 50 sửa bảo mật và độ tin cậy, audit supply chain, gỡ dependency `litellm` bị compromised, pin version, `uv.lock` có hash, CI quét supply chain. |
| 0.16.0 | `v2026.6.5` được advisory trỏ tới | ngày phát hành của đúng bản vá chưa được đọc | Vá CVE-2026-53870. Bản trước 0.16.0 tạo `response_store.db` và `webhook_subscriptions.json` mode `0o644`. User local đọc được lịch sử hội thoại, tool payload, prompt và HMAC secret theo route. |
| v0.21.0 | `v2026.8.31` | 2026-08-31 | Hardening: file chỉ dẫn agent (AGENTS.md, skill, memory store) cần duyệt ghi; vá lỗ redaction rò secret; approval học lệnh phá hủy trên Windows. |
| v0.21.2 | `v2026.9.11` | 2026-09-11 | Cô lập multi-profile: profile phụ không kế thừa allow-list profile mặc định; adapter không gửi credential sang host profile mặc định; stdio MCP không nhận vault secret của profile mặc định. |
| v0.21.5 | `v2026.9.24` | 2026-09-24 | Bản GitHub Release ổn định mới nhất lúc kiểm tra (`prerelease: false`). Ghi chú tuyển chọn của cửa sổ này được hoãn sang v0.22.0. Image: `nousresearch/hermes-agent:v2026.9.24`. |

Feed công khai ngày 2026-09-28 còn một bản canary
`v0.21.4+canary.20260928T071354Z`. Canary không thay bản ổn định.

Tag `v0.1.0` trả 404 lúc tra, nên không có ngày công bố kiểm chứng cho nền
pre-public. Các bài viết thứ cấp nói “tháng 2/2026” không được dùng làm mốc.

## Năng lực gắn với rủi ro vận hành

Hermes Agent là agent tự trị, tự host. Tài liệu chính thức mô tả các bề mặt sau;
mức độ cô lập của từng bề mặt lấy từ `SECURITY.md` và trang Security.

- **Vòng học.** Agent giữ memory xuyên phiên, tự tạo và sửa skill dưới
  `~/.hermes/skills/`, và có thể tự cải thiện skill khi dùng lại. Skill đã nạp
  được khai báo biến môi trường và file credential; các biến đó đi vào sandbox
  thực thi. Scanner cho skill do agent tạo mặc định tắt.
- **Terminal.** Bảy backend: local (quyền file của chính user), SSH, Docker,
  Singularity, Modal, Daytona, Vercel Sandbox. Local và SSH vẫn duyệt lệnh
  nguy hiểm. Năm backend còn lại bỏ kiểm tra đó.
- **Cổng nhắn tin.** Một process gateway cho Telegram, Discord, Slack, WhatsApp,
  Signal, email, SMS và nhiều nền tảng khác. Không có allowlist và không bật
  allow-all thì mọi người bị từ chối. DM lạ mặc định nhận mã ghép cặp 8 ký tự,
  TTL 1 giờ; chủ máy duyệt bằng `hermes pairing approve`.
- **Cron, webhook, API không người trực.** Gặp lệnh nguy hiểm thì mặc định từ
  chối (`cron_mode` / `unattended_mode: deny`). Đặt `approve` là tự duyệt.
- **MCP.** Subprocess stdio chỉ nhận `PATH`, `HOME`, `USER`, `LANG`, `LC_ALL`,
  `TERM`, `SHELL`, `TMPDIR`, biến `XDG_*`, và biến khai báo trong `env` của
  server. Phần còn lại bị gỡ. MCP vẫn là process sinh từ môi trường của agent,
  nên terminal sandbox không giam nó.
- **API server.** Mặc định tắt, chỉ lắng nghe `127.0.0.1` khi bật. Một key hợp
  lệ có toàn bộ toolset.
- **Dashboard và các HTTP plugin.** Mặc định loopback. Bind `0.0.0.0` là quyết
  định break-glass; hardening phơi ra internet thuộc về người vận hành.
- **Computer use, trình duyệt, sinh ảnh, TTS, kho đăng nhập.** Có trong sản phẩm.
  Trang Security không biến chúng thành ranh giới. Chúng là bề mặt đọc và gửi
  dữ liệu; tắt nếu việc cần làm không dùng tới.
- **Checkpoint / rollback.** Tùy chọn, tắt mặc định. Không chụp path bên trong
  terminal container và từ chối rollback ở đó.
- **Managed scope.** Cấu hình do quản trị viên ghim, cưỡng chế bằng quyền file.
  Không phải ranh giới chống agent.
- **iron-proxy.** Proxy egress tùy chọn, tắt mặc định, chỉ nối backend Docker
  trong bản tài liệu đã đọc.

Trang Security gọi tám lớp (ủy quyền user, duyệt lệnh, chặn ghi file, container,
lọc credential MCP, quét context file, cô lập phiên, sanitize input) là security
boundary. `SECURITY.md` nói chỉ cô lập OS là boundary trước LLM đối nghịch.
Khi hai văn bản lệch, quyết định vận hành đi theo `SECURITY.md`.

## Ưu điểm và hạn chế

Sự kiện có lợi, đã có nguồn:

- Mặc định đóng trên các bề mặt dễ hở: không allowlist thì từ chối; cron và phiên
  không người trực từ chối lệnh nguy hiểm; hết giờ duyệt thì từ chối; API server
  tắt; container image chạy non-root; hardline blocklist vẫn chặn một số lệnh
  thảm họa khi YOLO hoặc `approvals.mode: off` đang bật.
- Các đợt hardening có release note: path traversal và shell injection (v0.2.0),
  supply chain gồm dependency `litellm` (v0.5.0), quyền file world-readable
  (0.16.0), duyệt ghi file chỉ dẫn và redaction (v0.21.0), cô lập profile
  (v0.21.2).
- Chính sách viết thẳng heuristic nào không phải containment, và nêu tư thế nào
  được hỗ trợ. Người vận hành có thể chọn lớp OS thay vì tin cổng duyệt.
- Model không bị khóa một nhà cung cấp: Nous Portal, OpenRouter, OpenAI,
  Anthropic, Google, hoặc endpoint tương thích OpenAI; có hướng dẫn model local.
- MIT, tự host. Có Bitwarden, 1Password và command helper làm nguồn secret.

Hạn chế lấy từ chính sách, advisory và giới hạn tài liệu tự nhận:

- Denylist shell không đầy đủ về cấu trúc. Shell Turing-complete; cổng duyệt
  bắt lỗi ở chế độ hợp tác, không phải đầu ra đối nghịch. Báo cáo bypass các
  heuristic này nằm ngoài phạm vi lỗ hổng của dự án.
- Sandbox terminal không bọc process Python. Một skill hoặc plugin đã được import
  đọc được credential đang nằm trong bộ nhớ của agent.
- Backend container bỏ kiểm tra lệnh nguy hiểm. Write-guard chỉ phủ `write_file`
  và `patch`; tool terminal của cùng user vẫn ghi được path bị denylist chặn.
- Skill tự sửa được cây skill của nó, và biến môi trường do skill khai báo được
  đưa vào môi trường thực thi, kể cả container.
- CVE-2026-53870: trước 0.16.0, user local khác đọc được lịch sử hội thoại và
  HMAC secret vì file mode `0644`. Bản ổn định 0.21.5 nằm sau bản vá, nhưng máy
  nhiều user vẫn nên kiểm tra quyền các file state.
- Checkpoint, managed scope và iron-proxy dễ bị dùng như lưới an toàn dù tài liệu
  nói chúng không đủ vai trò đó.
- Cửa sổ v0.21.x có 460 pull request được gộp vào v0.21.5 mà ghi chú tuyển chọn
  hoãn sang v0.22.0. Lịch sử chức năng của cửa sổ đó chưa được chính dự án viết
  thành bản đọc được.

## Điều chưa xác minh được

- Ngày của nền pre-public v0.1.0, và ngày phát hành chính xác của bản vá 0.16.0
  (advisory chỉ chốt phiên bản vá và trỏ tới tag `v2026.6.5`).
- Nội dung ghi chú bị hoãn của v0.22.0.
- Đặc tả đầy đủ của `MEMORY.md`, curator, delegation, computer use và web
  dashboard — các trang này có trong mục lục nhưng không được đưa vào kết luận
  vì claim tương ứng không qua được bước kiểm chứng hoặc chưa được đọc hết.
- `SECURITY.md` nói `execute_code` là subprocess trên host nên terminal backend
  không giam nó. Trang cấu hình có chỗ nói Docker backend đưa `execute_code`
  qua `docker exec`. Chưa đọc mã để biết câu nào đúng với cây hiện tại. Cách
  xử lý là bọc cả process, không chờ hai câu này được hòa giải.
- Lệch giữa “luôn duyệt ghi skill/memory” (release v0.21.0) và “ghi tự do khi
  công tắc tắt” (trang skill và trang cấu hình).
- Advisory Database có thêm bản ghi chưa review, gồm một GHSA về DNS rebinding
  trên WebSocket trước 0.16.0. Chúng không được tính là lỗ hổng đã xác minh
  trong báo cáo này ngoài CVE-2026-53870, vì chưa đối chiếu commit vá.
- Không có mount list, luật firewall hay danh sách toolset bắt buộc nào trong
  tài liệu cho “mọi máy Linux giữ dữ liệu nội bộ”. Các mục ở trên là control
  có tên trong sản phẩm, không phải một file cấu hình bịa.

## Nguồn

- [SECURITY.md](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/SECURITY.md) — trust model, ranh giới OS, phạm vi báo cáo, hardening.
- [Security](https://hermes-agent.nousresearch.com/docs/user-guide/security) — duyệt lệnh, YOLO, hardline, allowlist gateway, cờ Docker, so sánh backend.
- [v2026.3.12](https://github.com/NousResearch/hermes-agent/releases/tag/v2026.3.12)
- [v2026.3.28](https://github.com/NousResearch/hermes-agent/releases/tag/v2026.3.28)
- [v2026.8.31](https://github.com/NousResearch/hermes-agent/releases/tag/v2026.8.31)
- [v2026.9.11](https://github.com/NousResearch/hermes-agent/releases/tag/v2026.9.11)
- [v2026.9.24](https://github.com/NousResearch/hermes-agent/releases/tag/v2026.9.24) — đối chiếu `releases/latest` ngày 2026-09-28.
- [CVE-2026-53870 / GHSA-99f9-j8r3-p853](https://github.com/advisories/GHSA-99f9-j8r3-p853)
- [Skills](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills)
- [API server](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server)
- [Checkpoints](https://hermes-agent.nousresearch.com/docs/user-guide/checkpoints-and-rollback)
- [Managed scope](https://hermes-agent.nousresearch.com/docs/user-guide/managed-scope)
- [iron-proxy](https://hermes-agent.nousresearch.com/docs/user-guide/egress/iron-proxy)
