# 📡 TỔNG HỢP TIẾN ĐỘ THỜI GIAN THỰC TỪ GROK

- **Cập nhật lúc**: `2026-09-30 06:04:22`
- **Session ID**: `01a0e74f-80fe-7202-8817-47c5291188f9`
- **Workflow ID**: `wf_01a0e7935df572a18dcb6c7d8eabafe3`
- **Giai đoạn hiện tại**: **`Report`**
- **Trạng thái**: `complete`
- **Báo cáo cuối cùng (`docs/architecture_audit_report.md`)**: ✅ ĐÃ SẴN SÀNG

## 🤖 Tiến độ Subagents của Grok

| Subagent | Giai đoạn | Trạng thái | Tokens | Thời gian (ms) |
|---|---|---|---|---|
| `research-planner` | Plan | **done** | 36,066 | 88,072 |
| `researcher-0` | Research | **done** | 689,778 | 239,606 |
| `researcher-1` | Research | **done** | 460,187 | 219,562 |
| `researcher-2` | Research | **done** | 441,278 | 435,872 |
| `researcher-3` | Research | **done** | 626,887 | 304,178 |
| `evidence-verifier-0` | Verify | **done** | 590,017 | 453,955 |
| `evidence-verifier-1` | Verify | **done** | 623,458 | 260,229 |
| `report-synthesizer` | Report | **done** | 41,072 | 381,767 |

## 🔍 Các phát hiện cốt lõi từ Grok đã thu thập được

### Subagent: `01a0e793-5e18-7cf2-b624-12c415fff506` (`01a0e793`)

Bốn câu hỏi dưới đây bám bốn đích bằng chứng khác nhau: lịch sử phát hành, năng lực vận hành, mô hình kiểm soát chính thức, và lỗ hổng hoặc giới hạn đã được ghi nhận cùng phần không kiểm chứng được.

```json
{"questions":["Theo GitHub releases, tags và release notes của https://github.com/NousResearch/hermes-agent cùng tài liệu chính thức https://hermes-agent.nousresearch.com/docs, những mốc phát hành công khai nào của Nous Research Hermes Agent được kiểm chứng đến hết tháng 9/2026, gồm ngày công bố và các đợt hardening bảo mật? Chỉ dùng release note, tag hoặc trang docs; không dùng blog, Wikipedia hay bài tổng hợp làm bằng chứng ngày hoặc phiên bản; không gộp Meta Hermes JavaScript engine, và chỉ nhắc mô hình Nous Hermes hoặc OpenHermes khi nguồn sơ cấp xác nhận liên hệ.","Các trang tính năng và kiến trúc chính thức, đặc biệt features/memory, features/skills, features/cron, messaging, developer-guide/architecture và docker, mô tả những năng lực vận hành nào làm thay đổi bề mặt rủi ro: learning loop gồm MEMORY.md, skill tự tạo và curator; terminal backend local, Docker, SSH và sandbox; messaging gateway; cron; delegation; MCP; credential vault; computer use; API server và web dashboard?","Các trang user-guide/security, checkpoints-and-rollback, managed-scope, secrets, egress (gồm iron-proxy và network isolation) cùng SECURITY.md mô tả mô hình an toàn chính thức nào và tự thừa nhận những giới hạn nào về phê duyệt lệnh, chặn mẫu nguy hiểm, cô lập container, egress, managed scope, secrets manager, checkpoint/rollback và ủy quyền người dùng trên gateway?","SECURITY.md, GitHub security advisories và các giới hạn được docs ghi rõ cho thấy sự kiện, lỗ hổng đã vá và nhược điểm nào; từ đúng các control được các nguồn ấy nêu, chiến lược tự host nào áp dụng được trên máy Linux đang giữ dữ liệu nội bộ nhạy cảm — gồm cô lập runtime, toolset, ai được nhắn gateway, bí mật, bộ nhớ và skill tự sinh, cron không giám sát, cập nhật và những gì không nên bật — mà không bịa cấu hình, đồng thời điều nào không xác minh được từ nguồn sơ cấp?"]}
```

---

### Subagent: `01a0e794-b665-7110-a8ec-04f020a6927c` (`01a0e794`)

Các mốc dưới đây chỉ lấy từ GitHub Releases/tags/release notes của Nous Research Hermes Agent và trang docs chính thức. Không có release note, tag hoặc trang docs đã xem nào xác nhận liên hệ với mô hình Nous Hermes hay OpenHermes.

```json
{"claims":[{"claim":"Hermes Agent v0.2.0, tag v2026.3.12, được công bố ngày 12 tháng 3 năm 2026 (published_at 2026-03-12T10:07:34Z). Release note gọi đây là bản tag đầu tiên kể từ v0.1.0, mô tả là nền tảng pre-public ban đầu, và có mục Security Hardening.","confidence":"high","evidence":"Release note: “Release Date: March 12, 2026” và “First tagged release since v0.1.0 (the initial pre-public foundation).” API ghi published_at 2026-03-12T10:07:34Z. Cùng note có mục “Security Hardening”, gồm sửa path traversal, shell injection, symlink boundary/bypass, prompt-injection bypass và quyền file 0600/0700.","source_title":"Hermes Agent v0.2.0 (2026.3.12)","source_locator":"https://github.com/NousResearch/hermes-agent/releases/tag/v2026.3.12","source_type":"primary"},{"claim":"Hermes Agent v0.5.0, tag v2026.3.28, được công bố ngày 28 tháng 3 năm 2026 và được release note gọi là “The hardening release”, gồm một đợt supply-chain hardening.","confidence":"high","evidence":"“Release Date: March 28, 2026” và “The hardening release … 50+ security and reliability fixes, and a comprehensive supply chain audit.” API: published_at 2026-03-28T20:12:05Z. Mục Supply chain hardening ghi đã gỡ dependency litellm bị compromised, pin version range, tạo lại uv.lock có hash, thêm CI quét supply-chain và bump dependency để sửa CVE.","source_title":"Hermes Agent v0.5.0 (v2026.3.28)","source_locator":"https://github.com/NousResearch/hermes-agent/releases/tag/v2026.3.28","source_type":"primary"},{"claim":"Hermes Agent v0.21.0, tag v2026.8.31, được công bố ngày 31 tháng 8 năm 2026 và release note ghi một đợt “Security hardening across the board”.","confidence":"high","evidence":"“Release Date: August 31, 2026”; API published_at 2026-08-31T19:29:49Z. Highlight: “Security hardening across the board — Protected agent-instruction files (AGENTS.md, skills, memory stores) now always require write approval … A deep redaction sweep closed secret-leak gaps … the approval system learned Windows destructive commands; and macOS permission grants finally survive updates via a stable TCC signing identity.”","source_title":"Hermes Agent v0.21.0 (v2026.8.31)","source_locator":"https://github.com/NousResearch/hermes-agent/releases/tag/v2026.8.31","source_type":"primary"},{"claim":"Hermes Agent v0.21.2, tag v2026.9.11, được công bố ngày 11 tháng 9 năm 2026 và release note có mục “Multi-profile isolation hardening”.","confidence":"high","evidence":"Tiêu đề “The state.db Patch Release”, “Release Date: September 11, 2026”; API published_at 2026-09-11T19:20:31Z. Mục hardening nói các profile phụ không còn kế thừa allow-list của profile mặc định, adapter không gửi credential tới host của profile mặc định, stdio MCP không nhận vault secret của profile mặc định, và MEDIA delivery không gắn .env, auth.json hoặc state.db của profile khác.","source_title":"Hermes Agent v0.21.2 (v2026.9.11)","source_locator":"https://github.com/NousResearch/hermes-agent/releases/tag/v2026.9.11","source_type":"primary"},{"claim":"Bản GitHub Release ổn định mới nhất tại thời điểm kiểm tra là Hermes Agent v0.21.5, tag v2026.9.24, công bố ngày 24 tháng 9 năm 2026; note hoãn curated notes sang v0.22.0.","confidence":"high","evidence":"Endpoint releases/latest trả về tag_name v2026.9.24, prerelease false, published_at 2026-09-24T10:09:38Z. Note: “Release Date: September 24, 2026” và “Full curated release notes for this window ship with v0.22.0”.","source_title":"Hermes Agent v0.21.5 (v2026.9.24)","source_locator":"https://github.com/NousResearch/hermes-agent/releases/tag/v2026.9.24","source_type":"primary"},{"claim":"Đến 28 tháng 9 năm 2026 vẫn có bản công khai dạng canary: tag v0.21.4+canary.20260928T071354Z, cập nhật 2026-09-28T07:13:55Z.","confidence":"high","evidence":"Feed releases.atom có entry title “v0.21.4+canary.20260928T071354Z”, updated 2026-09-28T07:13:55Z, nội dung “Hermes Agent canary 20260928T071354Z”, tác giả github-actions[bot].","source_title":"Release notes from hermes-agent","source_locator":"https://github.com/NousResearch/hermes-agent/releases.atom","source_type":"primary"}],"uncertainties":["API release và git ref của tag v0.1.0 đều trả 404, nên không có ngày công bố kiểm chứng cho nền tảng pre-public mà release note v0.2.0 nhắc.","Release note các bản patch nói curated notes từ v0.21.0 được hoãn tới v0.22.0; releases/latest hiện là v2026.9.24, không phải bằng chứng rằng v0.22.0 đã phát hành.","Docs stable-releases mô tả ref rc.<N>-vX.Y.Z là attempt lock chứ không phải tag stable; không dùng các ref rc.* nhìn thấy ngày 25/9/2026 làm ngày phát hành ổn định.","Không có release note, tag hoặc trang docs đã xem nào xác nhận Hermes Agent chính là mô hình Nous Hermes hoặc OpenHermes."]}
```

---

### Subagent: `01a0e794-b66b-7cd1-8633-d39d77b73473` (`01a0e794`)

Các trang tài liệu chính thức của Hermes Agent mô tả một vòng học có ghi nhớ và skill, thực thi lệnh trên nhiều backend, gateway nhắn tin kèm cron, cùng API server và dashboard web. Sáu nhận định dưới đây bám đúng những gì các trang đó nói.

```json
{
  "claims": [
    {
      "claim": "MEMORY.md và USER.md trong ~/.hermes/memories/ được đưa vào system prompt như snapshot đóng băng khi phiên bắt đầu; agent, kể cả background self-improvement review, ghi chúng bằng memory tool và mặc định không cần duyệt, nhưng mục khớp prompt injection, đánh cắp credential hoặc SSH backdoor bị chặn trước khi lưu.",
      "confidence": "high",
      "evidence": "Both files “are injected into the system prompt as a frozen snapshot at session start.” The agent “can add, replace, or remove entries.” “By default the agent saves memory freely — including from the background self-improvement review,” and memory.write_approval defaults to false. “Memory entries are scanned for injection and exfiltration patterns before being accepted”; matches for “prompt injection, credential exfiltration, SSH backdoors” or invisible Unicode “are blocked.”",
      "source_locator": "https://hermes-agent.nousresearch.com/docs/user-guide/features/memory",
      "source_title": "Persistent Memory | Hermes Agent",
      "source_type": "primary"
    },
    {
      "claim": "Agent có thể sửa hoặc xóa mọi skill trong ~/.hermes/skills/ bằng skill_manage; ghi skill mặc định được commit ngay, kể cả từ background review, và biến môi trường mà skill khai báo được chuyển vào sandbox của execute_code và terminal.",
      "confidence": "high",
      "evidence": "“All skills live in ~/.hermes/skills/” and “The agent can modify or delete any skill.” “By default the agent writes skills freely — including from the background self-improvement review,” with skills.write_approval: false. “Once set, declared env vars are automatically passed through to execute_code and terminal sandboxes.”",
      "source_locator": "https://hermes-agent.nousresearch.com/docs/user-guide/features/skills",
      "source_title": "Skills System | Hermes Agent",
      "source_type": "primary"
    },
    {
      "claim": "Curator bật mặc định, chỉ quản lý skill do background review đánh dấu agent-created, tự chuyển skill lâu không dùng sang stale rồi archive mà không tự xóa; pass LLM có thể patch hoặc gộp skill chỉ chạy khi curator.consolidate bật, và mặc định pass đó tắt.",
      "confidence": "high",
      "evidence": "The curator “periodically spawns a short auxiliary-model review” but “never auto-deletes”; unused skills move to ~/.hermes/skills/.archive/. Defaults include enabled: true and consolidate: false. Only the “background self-improvement review fork” sets created_by agent; foreground skill_manage creates, including /learn, “are not marked as agent-created.” With consolidate: true the forked agent may “patch (via skill_manage)” or consolidate skills.",
      "source_locator": "https://hermes-agent.nousresearch.com/docs/user-guide/features/curator",
      "source_title": "Curator | Hermes Agent",
      "source_type": "primary"
    },
    {
      "claim": "Với terminal backend docker, singularity, modal, daytona và vercel_sandbox, Hermes bỏ qua kiểm tra lệnh nguy hiểm vì coi container là ranh giới an toàn; cron, hermes chat -q và phiên webhook hoặc API server mặc định từ chối lệnh đó khi không có người duyệt.",
      "confidence": "high",
      "evidence": "“When running in docker, singularity, modal, daytona, or vercel_sandbox backends, dangerous command checks are skipped because the container itself is the security boundary.” Separately, cron_mode, single_query_mode, and unattended_mode for “webhook, msgraph_webhook, api_server” all default to deny.",
      "source_locator": "https://hermes-agent.nousresearch.com/docs/user-guide/security",
      "source_title": "Security | Hermes Agent",
      "source_type": "primary"
    },
    {
      "claim": "Messaging gateway là một tiến trình nền nối nhiều nền tảng, mặc định từ chối người không thuộc allowlist hoặc chưa ghép đôi qua DM, cấp toolset có terminal cho các nền tảng đã cấu hình, và tự tick bộ lập lịch cron mỗi 60 giây.",
      "confidence": "high",
      "evidence": "“By default, the gateway denies all users who are not in an allowlist or paired via DM. This is the safe default for a bot with terminal access.” The platform toolset table lists Telegram, Discord, Slack, WhatsApp, Signal, Email, webhooks, and others as “Full tools including terminal.” “The gateway also runs the cron scheduler, ticking every 60 seconds to execute any due jobs.”",
      "source_locator": "https://hermes-agent.nousresearch.com/docs/user-guide/messaging/",
      "source_title": "Messaging Gateway | Hermes Agent",
      "source_type": "primary"
    },
    {
      "claim": "API server mặc định tắt và chỉ lắng nghe 127.0.0.1, nhưng khi bật thì mọi request có API_SERVER_KEY được dùng toàn bộ toolset của agent, gồm lệnh terminal, và còn có API tạo, sửa và chạy cron job.",
      "confidence": "high",
      "evidence": "“The API server gives full access to hermes-agent's toolset, including terminal commands. API_SERVER_KEY is required for every deployment, including the default loopback bind on 127.0.0.1.” API_SERVER_ENABLED defaults to false and API_SERVER_HOST defaults to 127.0.0.1. The Jobs API accepts “prompt, schedule, skills, provider override, delivery target” and can “Trigger the job to run immediately.”",
      "source_locator": "https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server",
      "source_title": "API Server | Hermes Agent",
      "source_type": "primary"
    }
  ],
  "uncertainties": [
    "Trang delegation nói delegate_task tạo terminal session riêng, còn trang Docker nói một container sandbox bền được dùng chung cho tool call, /new và subagent; không có một câu trên cùng một trang đã đọc kết luận đó là cùng một container hay các container tách biệt.",
    "Một mục lục llms-full có nhắc container_persistent: false để cô lập theo phiên, nhưng trang cấu hình tương ứng chưa được đọc trực tiếp nên chế độ đó không được đưa vào nhận định."
  ]
}
```

---

### Subagent: `01a0e794-b66b-7cd1-8633-d3be4b8b309c` (`01a0e794`)

The official Hermes Agent policy treats OS isolation as the only boundary against an adversarial model. The six claims below are the load-bearing rules and the limits those docs state themselves.

```json
{
  "claims": [
    {
      "claim": "Hermes Agent's security policy says the operating system is the only boundary against an adversarial LLM; the approval gate, output redaction, pattern scanners, and tool allowlists are not containment, and a shell denylist is structurally incomplete and aimed at cooperative mistakes rather than adversarial output.",
      "confidence": "high",
      "evidence": "SECURITY.md §2.2: \"The only security boundary against an adversarial LLM is the operating system. Nothing inside the agent process constitutes containment — not the approval gate, not output redaction, not any pattern scanner, not any tool allowlist.\" §2.4: \"Shell is Turing-complete; a denylist over shell strings is structurally incomplete. The gate catches cooperative-mode mistakes, not adversarial output.\" §3.2 lists approval-gate and pattern-scanner bypasses as out of scope for vulnerability reports.",
      "source_locator": "https://raw.githubusercontent.com/NousResearch/hermes-agent/main/SECURITY.md",
      "source_title": "Hermes Agent Security Policy (SECURITY.md)",
      "source_type": "primary"
    },
    {
      "claim": "Terminal-backend container, remote-host, or cloud-sandbox isolation confines only shell and file-tool operations; it does not confine the agent Python process, including the code-execution tool, MCP subprocesses, plugin loading, hook dispatch, and skill loading.",
      "confidence": "high",
      "evidence": "SECURITY.md §2.2: \"What this confines: anything the agent does by issuing shell or file operations. What this does not confine: everything the agent does in its own Python process. That includes the code-execution tool (spawned as a host subprocess), MCP subprocesses (spawned from the agent's environment), plugin loading, hook dispatch, and skill loading (all imported into the agent interpreter).\" Operators who expect that sandbox to contain non-shell paths \"are operating outside the supported security posture.\"",
      "source_locator": "https://raw.githubusercontent.com/NousResearch/hermes-agent/main/SECURITY.md",
      "source_title": "Hermes Agent Security Policy (SECURITY.md)",
      "source_type": "primary"
    },
    {
      "claim": "On network-exposed gateway surfaces, callers inside a configured allowlist are equally trusted: Hermes does not model per-caller capabilities in one adapter, and session IDs are routing handles rather than authorization boundaries.",
      "confidence": "high",
      "evidence": "SECURITY.md §2.6: \"Session identifiers are routing handles, not authorization boundaries.\" \"Within the authorized set, all callers are equally trusted. Hermes Agent does not model per-caller capabilities inside a single adapter. Operators who need capability separation should run separate agent instances with separate allowlists.\" The same section requires an allowlist before a network adapter may dispatch work, resolve approvals, or relay output, and calls fail-open when no allowlist is set a code bug.",
      "source_locator": "https://raw.githubusercontent.com/NousResearch/hermes-agent/main/SECURITY.md",
      "source_title": "Hermes Agent Security Policy (SECURITY.md)",
      "source_type": "primary"
    },
    {
      "claim": "Checkpoint/rollback is opt-in and off by default, and container terminal backends are outside it: Hermes does not snapshot those sandbox paths or record the agent-write ledger, and /rollback diff and restore are refused.",
      "confidence": "high",
      "evidence": "Checkpoints page: \"Checkpoints are opt-in as of v2 … so the default is off.\" \"With a container terminal backend (docker, singularity, modal, daytona, vercel_sandbox, or a container plugin) … Hermes therefore does not take checkpoints or record the agent-write ledger for those paths, and /rollback … refuses diff and restore, on the CLI and in messaging-gateway chats alike.\"",
      "source_locator": "https://raw.githubusercontent.com/NousResearch/hermes-agent/main/website/docs/user-guide/checkpoints-and-rollback.md",
      "source_title": "Checkpoints and /rollback",
      "source_type": "primary"
    },
    {
      "claim": "Managed scope v1 is not an agent-proof boundary: enforcement is filesystem permissions only, it is advisory for root or anyone who can write or repoint the managed directory, the managed .env is mode 0644, and the agent can still change a managed variable in its own subprocess shell.",
      "confidence": "high",
      "evidence": "Managed Scope, \"Security model and limitations (v1)\": \"Enforcement is filesystem permissions only. If a user has write access to the managed directory (or runs Hermes as root), managed scope is advisory.\" \"The managed .env is world-readable (0644).\" \"The agent's own tools are not hard-blocked from a managed env value … nothing stops the agent from setting a different value inside its own subprocess shell. v1 is a management-convenience boundary against a normal user, not an un-escapable sandbox.\" A separate warning says a user who can set HERMES_MANAGED_DIR can point the scope at a directory they control.",
      "source_locator": "https://raw.githubusercontent.com/NousResearch/hermes-agent/main/website/docs/user-guide/managed-scope.md",
      "source_title": "Managed Scope",
      "source_type": "primary"
    },
    {
      "claim": "The iron-proxy egress control is optional, defaults to off, and in this release is wired only to the Docker terminal backend; its own model does not cover host compromise, raw-socket bypass of HTTPS_PROXY, exfiltration to an allowlisted host, AWS SigV4 or GCP service-account credentials left in the sandbox, or same-uid reads of secrets in proxy memory.",
      "confidence": "high",
      "evidence": "iron-proxy page: \"This release wires the egress proxy into the Docker backend only. Modal, Daytona, SSH, and Singularity do not receive proxy env vars or CA mounts yet.\" The documented proxy.enabled default is false, described as a complete no-op when false. \"What it does NOT protect against\" lists a compromised host process, \"Sandbox processes that bypass HTTPS_PROXY by using a raw socket,\" \"Allowlisted-host data exfiltration,\" uncovered AWS Bedrock SigV4 and GCP Vertex service-account OAuth credentials, and in-memory secrets readable via core dump or /proc/<pid>/mem by a same-uid attacker, marked \"Out of scope for this layer.\"",
      "source_locator": "https://raw.githubusercontent.com/NousResearch/hermes-agent/main/website/docs/user-guide/egress/iron-proxy.md",
      "source_title": "Egress credential-injection proxy (iron-proxy)",
      "source_type": "primary"
    }
  ],
  "uncertainties": [
    "The user-guide security page calls eight layers security boundaries, while SECURITY.md says only OS-level isolation is a boundary against an adversarial LLM. These claims follow SECURITY.md for the load-bearing rule and do not decide which wording controls if the two are treated as conflicting.",
    "GitHub main Markdown was fetched for SECURITY.md, the security guide, checkpoints, managed scope, iron-proxy, and network isolation. The rendered secrets page was fetched after raw website/docs/user-guide/secrets.md returned 404. Those copies were not byte-compared to the live HTML.",
    "The network-isolation and secrets pages were read, but their limitation statements are not among the six claims because of the six-claim cap."
  ]
}
```

---

### Subagent: `01a0e794-b66b-7cd1-8633-d3c493752dd2` (`01a0e794`)

Đối chiếu SECURITY.md trên `main`, tab advisory của repo, hai bản ghi GitHub Advisory Database đã mở, và tài liệu vận hành chính thức. Các control dưới đây là những gì các nguồn đó nêu, không phải cấu hình tự đặt.

```json
{
  "claims": [
    {
      "claim": "Chính sách Hermes Agent coi hệ điều hành là ranh giới duy nhất trước LLM đối nghịch: approval gate, output redaction, pattern scanner và tool allowlist chỉ là heuristic. Terminal-backend chỉ giam lệnh shell và file tool đi qua shell; execute_code, process con MCP, plugin, hook và skill import trong interpreter không bị giam. Posture được hỗ trợ khi nhận nội dung ngoài tầm kiểm soát của operator, hoặc khi triển khai production/shared, là bọc cả cây process bằng Docker image/Compose của Hermes hoặc NVIDIA OpenShell.",
      "confidence": "high",
      "evidence": "SECURITY.md §2.2: “The only security boundary against an adversarial LLM is the operating system.” Terminal-backend “does not confine” code-execution, MCP subprocesses, plugin loading, hook dispatch, and skill loading. Whole-process wrapping is “Hermes Agent's own Docker image and Compose setup” or NVIDIA OpenShell, and is “the supported posture” for uncontrolled input surfaces and production or shared deployments. Local backend plus untrusted input, or expecting a terminal sandbox to contain non-shell paths, is “outside the supported security posture.”",
      "source_locator": "https://raw.githubusercontent.com/NousResearch/hermes-agent/main/SECURITY.md",
      "source_title": "Hermes Agent Security Policy (SECURITY.md)",
      "source_type": "primary"
    },
    {
      "claim": "Các control triển khai được chính sách nêu là: chạy non-root; credential chỉ ở file credential của operator với quyền chặt, không để trong config chính hay VCS, còn OpenShell thì dùng Provider store; không đưa gateway hoặc API ra Internet công cộng nếu không có VPN, Tailscale hoặc firewall; mỗi adapter lộ mạng phải có caller allowlist và mọi caller trong allowlist được tin ngang nhau; skill/plugin bên thứ ba phải được đọc mã Python và script trước khi cài. Lọc biến môi trường không phải containment vì code trong process đọc được credential đang nằm trong bộ nhớ.",
      "confidence": "high",
      "evidence": "§2.3 says credentials are stripped from shell, MCP, cron scripts, and the code-execution child, but “It is not containment” because in-process skills, plugins, and hooks can read in-memory credentials. §2.4 says skills “execute arbitrary Python at import time” and Skills Guard is only a review aid. §2.6 requires an allowlist on every network-exposed adapter and says all authorized callers are equally trusted. §4 repeats non-root, tight credential-file permissions, no public exposure without VPN/Tailscale/firewall, per-adapter allowlists, and review of skill Python and scripts before install.",
      "source_locator": "https://raw.githubusercontent.com/NousResearch/hermes-agent/main/SECURITY.md",
      "source_title": "Hermes Agent Security Policy (SECURITY.md)",
      "source_type": "primary"
    },
    {
      "claim": "Tab Security Advisories của chính repo NousResearch/hermes-agent không có advisory nào được publish tại thời điểm đọc.",
      "confidence": "high",
      "evidence": "The repository security-advisories page states: “There aren't any published security advisories.”",
      "source_locator": "https://github.com/NousResearch/hermes-agent/security/advisories",
      "source_title": "Security Advisories · NousResearch/hermes-agent",
      "source_type": "primary"
    },
    {
      "claim": "GitHub Advisory Database, không phải tab advisory của repo, ghi CVE-2026-53870: hermes-agent trước 0.16.0 tạo response_store.db và webhook_subscriptions.json với mode 0o644, để user local đọc lịch sử hội thoại, tool payload, prompt và HMAC secret theo route; phiên bản ghi là đã vá là 0.16.0.",
      "confidence": "high",
      "evidence": "GHSA-99f9-j8r3-p853 lists affected versions < 0.16.0 and patched versions 0.16.0. Description: Hermes Agent before 0.16.0 creates those two files world-readable (mode 0o644), exposing conversation history, tool payloads, prompts, and per-route HMAC secrets to local users. It was published by NVD on Jun 17, 2026 and marked reviewed Jun 19, 2026.",
      "source_locator": "https://github.com/advisories/GHSA-99f9-j8r3-p853",
      "source_title": "GHSA-99f9-j8r3-p853 / CVE-2026-53870",
      "source_type": "primary"
    },
    {
      "claim": "Tài liệu Security ghi mặc định từ chối mọi người nhắn gateway khi chưa có allowlist và chưa bật GATEWAY_ALLOW_ALL_USERS; cron và phiên không người trực mặc định chặn lệnh nguy hiểm; tắt approval hoặc bật YOLO bỏ các kiểm tra đó trừ hardline blocklist; backend container bỏ luôn kiểm tra lệnh nguy hiểm. Cùng trang nói write-guard và deny rule không phải sandbox, và biến đưa vào container có thể bị đọc rồi gửi đi.",
      "confidence": "high",
      "evidence": "The guide says that with no allowlists and GATEWAY_ALLOW_ALL_USERS unset, all users are denied, and the production checklist says never set GATEWAY_ALLOW_ALL_USERS=true, use terminal.backend docker, chmod 600 ~/.hermes/.env, do not run the gateway as root, keep terminal.cwd off sensitive directories, and run hermes update regularly. cron_mode and unattended_mode default to deny; approve auto-approves in that context, while a command_allowlist rule key still runs under deny. approvals.mode off equals --yolo; YOLO skips dangerous-command checks except the hardline blocklist; docker, singularity, modal, daytona, and vercel_sandbox skip those checks. Write guards cover write_file and patch only; deny rules “are not … an OS capability sandbox.” Names in docker_forward_env can be read and exfiltrated, and skill-declared required_environment_variables are forwarded into Docker even without being listed there. Provider API keys and gateway tokens should not be added to env_passthrough.",
      "source_locator": "https://hermes-agent.nousresearch.com/docs/user-guide/security",
      "source_title": "Security | Hermes Agent",
      "source_type": "primary"
    },
    {
      "claim": "Trên máy local, docs nói agent có quyền file của chính user; cách docs đưa ra là tắt tool bằng hermes tools hoặc agent.disabled_toolsets, hoặc chuyển sang Docker. Skill do agent tạo mặc định không bị scanner chặn, và cả skill lẫn memory mặc định ghi tự do, kể cả bước self-improvement chạy nền, cho tới khi bật write_approval. hermes update là lệnh áp dụng bản cập nhật; backup trước update mặc định là quick, gồm pairing, cron, config và auth.",
      "confidence": "high",
      "evidence": "Configuration docs: on the local backend, “The agent has the same filesystem access as your user account. Use hermes tools to disable tools you don't want, or switch to Docker.” agent.disabled_toolsets removes named toolsets on CLI and every gateway platform. skills.guard_agent_created is “off by default” (example sets true). skills.write_approval defaults to false, “write freely”; memory.write_approval defaults to false, and when true the background self-improvement review is staged for /memory approve or reject. updates.pre_update_backup defaults to quick, snapshotting “pairing data, cron jobs, config, auth”; applying an update is hermes update.",
      "source_locator": "https://hermes-agent.nousresearch.com/docs/user-guide/configuration",
      "source_title": "Hermes Agent Configuration",
      "source_type": "primary"
    }
  ],
  "uncertainties": [
    "SECURITY.md trên main vẫn nói execute_code là subprocess trên host nên terminal-backend không giam nó, trong khi trang configuration hiện nói Docker backend đưa cả execute_code qua docker exec. Chưa đọc mã nên không xác định câu nào đúng với code hiện tại.",
    "Tab advisory của repo không liệt kê CVE. Phần Security của release v2026.6.5 có nêu CVE-2026-48710, siết SSRF và gỡ bearer token khỏi môi trường subprocess, nhưng đoạn đã đọc không nêu CVE-2026-53869 hay CVE-2026-53870; chưa đối chiếu commit vá.",
    "GHSA-4pqm-j46f-795x mô tả DNS rebinding trên WebSocket trước 0.16.0 và ghi patched version 0.16.0, nhưng không đủ chỗ trong sáu claim; chưa kiểm tra bản mới hơn 0.16.0 có hồi quy hay không.",
    "Trang tìm GitHub Advisory Database với truy vấn hermes-agent báo 48 advisory, phần lớn gắn nhãn Unreviewed. Các CVE kiểu VulDB nói vendor không phản hồi, gồm cả bản ghi Skills Guard, không được xác minh trên mã hoặc main và không được tính là lỗ hổng nhà phát triển đã thừa nhận.",
    "Không có nguồn sơ cấp nào đã đọc đưa một danh sách mount, luật firewall, hay danh sách toolset bắt buộc cho mọi máy Linux đang giữ dữ liệu nội bộ nhạy cảm; chọn các giá trị đó sẽ là bịa cấu hình.",
    "Hành vi thực tế của NVIDIA OpenShell và việc cron.allow_agent_scheduling mặc định false có còn đúng trên mọi profile cài đặt không được kiểm tra ngoài văn bản docs đã đọc."
  ]
}
```

---

### Subagent: `01a0e79b-5d51-7d23-90cd-9d157379bcb8` (`01a0e79b`)

Đã đối chiếu release API, `SECURITY.md`, trang memory/curator/messaging/security, managed scope và tab advisories. Các mệnh đề có ngoại lệ trên chính trang được trích được đánh không được chứng minh.

```json
{"verdicts":[{"claim_id":"claim-0","supported":true,"reason":"GitHub names this release Hermes Agent v0.2.0, tag v2026.3.12, published_at 2026-03-12T10:07:34Z. The note calls it the first tagged release since v0.1.0 (the initial pre-public foundation) and has a Security Hardening section.","evidence":"API name \"Hermes Agent v0.2.0 (2026.3.12)\", tag_name \"v2026.3.12\", published_at \"2026-03-12T10:07:34Z\". Body: \"Release Date: March 12, 2026\" and \"First tagged release since v0.1.0 (the initial pre-public foundation).\" The note includes the heading \"### Security Hardening\" (path traversal, shell injection, symlink boundary/bypass, prompt-injection bypass, and 0600/0700 permissions).","source_title":"Hermes Agent v0.2.0 (2026.3.12)","source_locator":"https://github.com/NousResearch/hermes-agent/releases/tag/v2026.3.12"},{"claim_id":"claim-2","supported":true,"reason":"The v2026.8.31 release is Hermes Agent v0.21.0, published 31 August 2026, and its highlights include the phrase Security hardening across the board.","evidence":"API tag_name \"v2026.8.31\", name \"Hermes Agent v0.21.0 (v2026.8.31)\", published_at \"2026-08-31T19:29:49Z\". Body: \"Release Date: August 31, 2026\" and highlight \"Security hardening across the board — Protected agent-instruction files (AGENTS.md, skills, memory stores) now always require write approval…\"","source_title":"Hermes Agent v0.21.0 (v2026.8.31)","source_locator":"https://github.com/NousResearch/hermes-agent/releases/tag/v2026.8.31"},{"claim_id":"claim-4","supported":true,"reason":"At check time the newest non-prerelease GitHub release is Hermes Agent v0.21.5, tag v2026.9.24, published 24 September 2026, and the note defers full curated notes to v0.22.0.","evidence":"GET /releases/latest and the releases list both return tag_name \"v2026.9.24\", name \"Hermes Agent v0.21.5 (v2026.9.24)\", prerelease false, published_at \"2026-09-24T10:09:38Z\". Body: \"Release Date: September 24, 2026\", \"Full curated notes for this window are deferred to v0.22.0\", and \"Full curated release notes for this window ship with v0.22.0\". The next listed release is older, v2026.9.21.","source_title":"Hermes Agent v0.21.5 (v2026.9.24)","source_locator":"https://api.github.com/repos/NousResearch/hermes-agent/releases/latest"},{"claim_id":"claim-6","supported":false,"reason":"Both memory files are a frozen session-start snapshot and threat matches are blocked before accept, but background-review replace/remove writes are staged even when the approval gate is off, so default unapproved writes do not cover that review.","evidence":"The memory guide says both files in ~/.hermes/memories/ \"are injected into the system prompt as a frozen snapshot at session start\", write_approval defaults to false, and entries matching prompt injection, credential exfiltration, or SSH backdoors are blocked before acceptance. The same page says \"the background review stages these even with the gate off\" for replace/remove. Issue #120841 (2026-09-24) says that since #105921 the background review stages every replace or remove for approval.","source_title":"Persistent Memory | Hermes Agent","source_locator":"https://hermes-agent.nousresearch.com/docs/user-guide/features/memory"},{"claim_id":"claim-8","supported":false,"reason":"Curator is on by default and does not auto-delete, but it is not limited to skills the background review marked, and the LLM patch/merge pass can be forced with --consolidate while curator.consolidate stays false.","evidence":"Curator defaults include enabled: true and consolidate: false, and it \"never auto-deletes\". \"hermes curator adopt\" writes the same created_by: agent marker, and \"hermes curator run --consolidate\" forces the LLM pass \"overriding the config default\". With consolidate true the fork may patch via skill_manage or consolidate skills, but that is not the only way the pass runs.","source_title":"Curator | Hermes Agent","source_locator":"https://hermes-agent.nousresearch.com/docs/user-guide/features/curator"},{"claim_id":"claim-10","supported":false,"reason":"The gateway is one background process, denies non-allowlisted and unpaired users, and ticks cron every 60 seconds, but a configured platform does not always get a terminal toolset: Raft is wake-only.","evidence":"The messaging guide says the gateway \"is a single background process that connects to all your configured platforms\", \"denies all users who are not in an allowlist or paired via DM\", and \"runs the cron scheduler, ticking every 60 seconds\". The toolset table gives many platforms \"Full tools including terminal\", but Raft is \"Wake-only channel; agent uses Raft CLI for message I/O\".","source_title":"Messaging Gateway | Hermes Agent","source_locator":"https://hermes-agent.nousresearch.com/docs/user-guide/messaging/"},{"claim_id":"claim-12","supported":true,"reason":"SECURITY.md says the operating system is the only boundary against an adversarial LLM, names the approval gate, redaction, pattern scanners, and tool allowlists as non-containment, and says a shell denylist is structurally incomplete and only catches cooperative mistakes.","evidence":"§2.2: \"The only security boundary against an adversarial LLM is the operating system. Nothing inside the agent process constitutes containment — not the approval gate, not output redaction, not any pattern scanner, not any tool allowlist.\" §2.4: \"a denylist over shell strings is structurally incomplete. The gate catches cooperative-mode mistakes, not adversarial output.\"","source_title":"Hermes Agent Security Policy (SECURITY.md)","source_locator":"https://raw.githubusercontent.com/NousResearch/hermes-agent/main/SECURITY.md"},{"claim_id":"claim-14","supported":false,"reason":"SECURITY.md says allowlisted callers are equally trusted and that session IDs are only routing handles, but the messaging guide documents per-caller admin versus regular-user command rights inside one platform adapter.","evidence":"SECURITY.md §2.6: \"Session identifiers are routing handles, not authorization boundaries\" and \"Within the authorized set, all callers are equally trusted. Hermes Agent does not model per-caller capabilities inside a single adapter.\" The messaging guide says allow_admin_from and user_allowed_commands split allowlisted users into admin and regular user for slash commands on that platform scope.","source_title":"Hermes Agent Security Policy (SECURITY.md)","source_locator":"https://raw.githubusercontent.com/NousResearch/hermes-agent/main/SECURITY.md"},{"claim_id":"claim-16","supported":true,"reason":"Managed scope v1 is filesystem-permission enforcement only, advisory for root or a writer, defeatable by repointing HERMES_MANAGED_DIR, uses a 0644 managed .env, and does not stop the agent changing a managed variable in its own subprocess shell.","evidence":"\"Security model and limitations (v1)\": \"Enforcement is filesystem permissions only. If a user has write access to the managed directory (or runs Hermes as root), managed scope is advisory.\" \"The managed .env is world-readable (0644).\" \"nothing stops the agent from setting a different value inside its own subprocess shell.\" Warning: a user who can set HERMES_MANAGED_DIR \"can repoint managed scope at a directory they control, defeating it.\" v1 is \"not an un-escapable sandbox.\"","source_title":"Managed Scope","source_locator":"https://raw.githubusercontent.com/NousResearch/hermes-agent/main/website/docs/user-guide/managed-scope.md"},{"claim_id":"claim-18","supported":true,"reason":"The policy treats the OS as the only adversarial-LLM boundary, calls the named in-process controls non-containment heuristics, limits terminal-backend isolation to shell and shell-backed file tools, and names Docker/Compose or NVIDIA OpenShell whole-process wrapping as the supported posture for uncontrolled input and production or shared deployments.","evidence":"§2.2 says the OS is the only security boundary and that the approval gate, output redaction, pattern scanners, and tool allowlists are not containment, with in-process screening treated as a heuristic. Terminal-backend isolation confines shell and file tools implemented on the shell contract, and does not confine the code-execution tool, MCP subprocesses, plugin loading, hook dispatch, or skill loading in the agent interpreter. Whole-process wrapping via \"Hermes Agent's own Docker image and Compose setup\" or NVIDIA OpenShell \"is the supported posture\" for content from surfaces the operator does not control and for production or shared deployments.","source_title":"Hermes Agent Security Policy (SECURITY.md)","source_locator":"https://raw.githubusercontent.com/NousResearch/hermes-agent/main/SECURITY.md"},{"claim_id":"claim-20","supported":true,"reason":"At the time of reading, the repository security-advisories tab and the GitHub advisories API both show no published advisories.","evidence":"The advisories page states \"There aren't any published security advisories.\" GET https://api.github.com/repos/NousResearch/hermes-agent/security-advisories returns an empty array.","source_title":"Security Advisories · NousResearch/hermes-agent","source_locator":"https://github.com/NousResearch/hermes-agent/security/advisories"},{"claim_id":"claim-22","supported":true,"reason":"The security guide states default gateway deny without allowlists and without GATEWAY_ALLOW_ALL_USERS, default deny for cron and unattended dangerous commands, a hardline exception for YOLO and approvals off, skipped dangerous-command checks on container and sandbox backends, and that write guards, deny rules, and forwarded container variables are not a sandbox.","evidence":"The guide says that if no allowlists are configured and GATEWAY_ALLOW_ALL_USERS is not set, all users are denied. cron_mode and unattended_mode default to deny. approvals.mode off equals --yolo, and YOLO disables dangerous-command checks except the hardline blocklist. Docker, singularity, modal, daytona, and vercel_sandbox skip dangerous-command checks. Write guards \"do not sandbox a hostile or compromised agent\", deny rules \"are not … an OS capability sandbox\", and names in docker_forward_env \"can be read and exfiltrated\".","source_title":"Security | Hermes Agent","source_locator":"https://hermes-agent.nousresearch.com/docs/user-guide/security"}]}
```

---

### Subagent: `01a0e79b-5d52-77b3-a156-ff67e73cf6c5` (`01a0e79b`)

Đã đối chiếu release note, API GitHub, tài liệu Hermes và advisory NVD/GHSA. Mười hai claim đều khớp đúng câu chữ nguồn, không phải diễn giải rộng.

```json
{"verdicts":[{"claim_id":"claim-1","supported":true,"reason":"The v2026.3.28 release is named Hermes Agent v0.5.0, is dated March 28, 2026, calls itself “The hardening release,” and has a Supply chain hardening item covering the compromised litellm removal, version pins, hashed uv.lock, supply-chain CI, and CVE bumps.","evidence":"Release name “Hermes Agent v0.5.0 (v2026.3.28)”, “Release Date: March 28, 2026”, and “The hardening release … comprehensive supply chain audit.” The Supply chain hardening highlight says the compromised litellm dependency was removed, dependency ranges were pinned, uv.lock was regenerated with hashes, a CI workflow scans PRs for supply-chain attacks, and dependencies were bumped to fix CVEs. GitHub API published_at is 2026-03-28T20:12:05Z.","source_title":"Hermes Agent v0.5.0 (v2026.3.28)","source_locator":"https://github.com/NousResearch/hermes-agent/releases/tag/v2026.3.28"},{"claim_id":"claim-3","supported":true,"reason":"The v2026.9.11 release is Hermes Agent v0.21.2, dated September 11, 2026, and its notes contain the heading Multi-profile isolation hardening.","evidence":"Title “Hermes Agent v0.21.2 (v2026.9.11) — The state.db Patch Release”, “Release Date: September 11, 2026”, and a “### Multi-profile isolation hardening” section. GitHub API published_at is 2026-09-11T19:20:31Z. That section says secondary profiles no longer inherit the default allow-lists, adapters no longer send credentials to the default profile host, stdio MCP no longer receives the default profile’s vault secrets, and MEDIA delivery can no longer attach another profile’s .env, auth.json, or state.db.","source_title":"Hermes Agent v0.21.2 (v2026.9.11)","source_locator":"https://github.com/NousResearch/hermes-agent/releases/tag/v2026.9.11"},{"claim_id":"claim-5","supported":true,"reason":"On 2026-09-28 the public releases feed and the public tag page both still show this canary with that exact update time.","evidence":"releases.atom’s first entry is titled “v0.21.4+canary.20260928T071354Z”, updated “2026-09-28T07:13:55Z”, with content “Hermes Agent canary 20260928T071354Z” and author github-actions[bot]. The public tag page repeats that title and says github-actions tagged it on 28 Sep 07:13.","source_title":"Release notes from hermes-agent","source_locator":"https://github.com/NousResearch/hermes-agent/releases.atom"},{"claim_id":"claim-7","supported":true,"reason":"The skills guide says every skill under ~/.hermes/skills/ can be modified or deleted, default skill writes are committed rather than staged, including background review, and declared env vars are passed into execute_code and terminal sandboxes.","evidence":"“All skills live in ~/.hermes/skills/” and “The agent can modify or delete any skill.” skill_manage creates, updates, and deletes skills. “By default the agent writes skills freely — including from the background self-improvement review,” with skills.write_approval false; write_approval true stages writes “instead of committed.” “Once set, declared env vars are automatically passed through to execute_code and terminal sandboxes.”","source_title":"Skills System | Hermes Agent","source_locator":"https://hermes-agent.nousresearch.com/docs/user-guide/features/skills"},{"claim_id":"claim-9","supported":true,"reason":"The security guide skips dangerous-command checks on those five backends because it treats the container as the boundary, and the three unattended approval modes default to deny.","evidence":"“When running in docker, singularity, modal, daytona, or vercel_sandbox backends, dangerous command checks are skipped because the container itself is the security boundary.” Defaults are cron_mode deny, single_query_mode deny for hermes chat -q, and unattended_mode deny for webhook, msgraph_webhook, and api_server sessions that have no human to answer an approval.","source_title":"Security | Hermes Agent","source_locator":"https://hermes-agent.nousresearch.com/docs/user-guide/security"},{"claim_id":"claim-11","supported":true,"reason":"The API server is disabled by default, binds to 127.0.0.1 by default, and a key grants the full agent toolset including terminal commands; the Jobs API creates, updates, and immediately runs cron jobs.","evidence":"API_SERVER_ENABLED defaults to false and API_SERVER_HOST defaults to 127.0.0.1, described as localhost only by default. “The API server gives full access to hermes-agent's toolset, including terminal commands. API_SERVER_KEY is required for every deployment, including the default loopback bind on 127.0.0.1.” POST /api/jobs accepts prompt, schedule, skills, provider override, and delivery target; PATCH updates a job; POST /api/jobs/{job_id}/run triggers it immediately.","source_title":"API Server | Hermes Agent","source_locator":"https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server"},{"claim_id":"claim-13","supported":true,"reason":"SECURITY.md §2.2 limits terminal-backend isolation to shell and file operations and explicitly excludes the in-process paths named in the claim.","evidence":"A non-default terminal backend runs shell commands in a container, remote host, or cloud sandbox, and file tools follow that backend. “What this confines: anything the agent does by issuing shell or file operations. What this does not confine: everything the agent does in its own Python process,” including the code-execution tool, MCP subprocesses, plugin loading, hook dispatch, and skill loading.","source_title":"Hermes Agent Security Policy (SECURITY.md)","source_locator":"https://raw.githubusercontent.com/NousResearch/hermes-agent/main/SECURITY.md"},{"claim_id":"claim-15","supported":true,"reason":"Checkpoints are documented as opt-in and off by default, and container terminal backends are excluded from snapshots, the write ledger, and rollback diff/restore.","evidence":"“Checkpoints are opt-in as of v2 … so the default is off,” and checkpoints.enabled defaults to false. For docker, singularity, modal, daytona, vercel_sandbox, or a container plugin, “Hermes therefore does not take checkpoints or record the agent-write ledger for those paths, and /rollback … refuses diff and restore.”","source_title":"Checkpoints and /rollback","source_locator":"https://raw.githubusercontent.com/NousResearch/hermes-agent/main/website/docs/user-guide/checkpoints-and-rollback.md"},{"claim_id":"claim-17","supported":true,"reason":"iron-proxy is optional, defaults off, is wired only to Docker in this release, and its own non-goals list every gap named in the claim.","evidence":"proxy.enabled defaults to false and is “a complete no-op” when false. “This release wires the egress proxy into the Docker backend only. Modal, Daytona, SSH, and Singularity do not receive proxy env vars or CA mounts yet.” “What it does NOT protect against” includes a compromised host process, raw-socket bypass of HTTPS_PROXY, allowlisted-host data exfiltration, AWS Bedrock SigV4 and GCP Vertex service-account credentials left in the sandbox, and same-uid reads of in-memory secrets via core dump or /proc/<pid>/mem, marked out of scope.","source_title":"Egress credential-injection proxy (iron-proxy)","source_locator":"https://raw.githubusercontent.com/NousResearch/hermes-agent/main/website/docs/user-guide/egress/iron-proxy.md"},{"claim_id":"claim-19","supported":true,"reason":"SECURITY.md states each listed deployment control, equal trust inside an adapter allowlist, pre-install review of skill Python and scripts, and that environment filtering is not containment.","evidence":"§4 says run non-root; keep credentials in the operator credential file with tight permissions, never in the main config or version control, and use the OpenShell Provider store; do not expose the gateway or API publicly without VPN, Tailscale, or firewall; set a caller allowlist for every network-exposed adapter; and review third-party skills and plugins before install by reading Python and scripts. §2.6 says all authorized callers are equally trusted. §2.3 says environment filtering “is not containment” because in-process code can read in-memory credentials.","source_title":"Hermes Agent Security Policy (SECURITY.md)","source_locator":"https://raw.githubusercontent.com/NousResearch/hermes-agent/main/SECURITY.md"},{"claim_id":"claim-21","supported":true,"reason":"The GitHub Advisory Database entry, whose repository_advisory_url is null, records CVE-2026-53870 with the stated files, mode, impact, affected range, and patched version 0.16.0. NVD repeats the same description.","evidence":"GHSA-99f9-j8r3-p853 is a reviewed GitHub Advisory Database record with repository_advisory_url null. It affects hermes-agent < 0.16.0 and lists first patched version 0.16.0. The description says Hermes Agent before 0.16.0 creates response_store.db and webhook_subscriptions.json mode 0o644, exposing conversation history, tool payloads, prompts, and per-route HMAC secrets to local users. NVD’s CVE-2026-53870 description matches.","source_title":"GHSA-99f9-j8r3-p853 / CVE-2026-53870","source_locator":"https://github.com/advisories/GHSA-99f9-j8r3-p853"},{"claim_id":"claim-23","supported":true,"reason":"The configuration guide states the local user-level filesystem access and the three controls, the default-off agent-skill scanner, free skill and memory writes until write_approval, and the quick pre-update backup taken by hermes update.","evidence":"On the local backend: “The agent has the same filesystem access as your user account. Use hermes tools to disable tools you don't want, or switch to Docker.” agent.disabled_toolsets removes named toolsets on the CLI and every gateway platform. skills.guard_agent_created defaults to false. skills.write_approval defaults to false (“write freely”), and memory.write_approval defaults to false; when memory approval is on, the background self-improvement review is staged. The skills guide says default skill writes include that background review. Applying an update is hermes update, and updates.pre_update_backup defaults to quick, snapshotting pairing data, cron jobs, config, and auth.","source_title":"Hermes Agent Configuration","source_locator":"https://hermes-agent.nousresearch.com/docs/user-guide/configuration"}]}
```

---

### Subagent: `01a0e7a2-4aca-7f70-b78b-8e5d4b87bbb0` (`01a0e7a2`)

<report-body>
Hermes Agent của Nous Research có chuỗi mốc phát hành công khai kiểm chứng được bằng tag và release note, từ nền tảng pre-public tới bản ổn định mới nhất trong tháng 9/2026, và feed công khai sau đó vẫn còn một bản canary. Chính sách dự án không coi cổng duyệt lệnh, redaction, bộ lọc mẫu hay allowlist là lớp giam mô hình đối nghịch: ranh giới được công nhận là hệ điều hành, còn sandbox terminal chỉ bó lệnh shell và file. Trên máy Linux đang giữ tài liệu nội bộ, chỉ nên dựa vào control có thật — bọc cả cây process, non-root, allowlist gateway, secret tách khỏi config, duyệt ghi skill và memory, toolset tối thiểu — và không bật các chế độ bỏ qua duyệt, mở gateway cho mọi người, hay API nếu không cần. Một số hạng mục được hỏi không có trong tài liệu và release đã đọc; chúng nằm ở mục cuối, không suy ra thêm.

### Lịch sử phát hành đã kiểm chứng

| Phiên bản | Tag | Thời điểm | Ghi nhận trong release |
| --- | --- | --- | --- |
| v0.2.0 | v2026.3.12 | 12/3/2026, published_at 2026-03-12T10:07:34Z | Bản tag đầu tiên kể từ v0.1.0 (nền tảng pre-public). Mục Security Hardening: path traversal, shell injection, symlink boundary/bypass, prompt-injection bypass, quyền file 0600/0700. [S1] |
| v0.5.0 | v2026.3.28 | 28/3/2026, published_at 2026-03-28T20:12:05Z | “The hardening release”: hơn 50 sửa bảo mật và độ tin cậy, kèm audit supply chain; gỡ dependency litellm bị compromised, pin version, tạo lại uv.lock có hash, thêm CI quét supply-chain, bump dependency để vá CVE. [S2] |
| v0.21.0 | v2026.8.31 | 31/8/2026, published_at 2026-08-31T19:29:49Z | “Security hardening across the board”: file chỉ dẫn agent (AGENTS.md, skill, memory store) luôn cần duyệt ghi; quét redaction lỗ hổng rò secret; approval học lệnh phá hủy trên Windows; quyền macOS giữ qua cập nhật nhờ danh tính ký TCC ổn định. [S3] |
| v0.21.2 | v2026.9.11 | 11/9/2026, published_at 2026-09-11T19:20:31Z | “The state.db Patch Release”. Multi-profile isolation: profile phụ không kế thừa allow-list profile mặc định; adapter không gửi credential tới host profile mặc định; stdio MCP không nhận vault secret profile mặc định; MEDIA không gắn .env, auth.json hoặc state.db của profile khác. [S4] |
| v0.21.5 | v2026.9.24 | 24/9/2026, published_at 2026-09-24T10:09:38Z | Bản GitHub Release ổn định mới nhất lúc kiểm tra (prerelease false). Curated notes của cửa sổ này hoãn sang v0.22.0. [S5] |
| canary | v0.21.4+canary.20260928T071354Z | updated 2026-09-28T07:13:55Z | Vẫn trên feed công khai ngày 28/9/2026; nội dung “Hermes Agent canary 20260928T071354Z”; tác giả github-actions[bot]. [S6] |

Bảng chỉ gồm artifact có release note, tag hoặc entry feed đã đọc, không phải mọi số phiên bản ở giữa hai cụm đầu và cụm cuối hè. Canary đứng sau bản mà endpoint ổn định trả về và không thay bản đó. Nội dung phần note bị hoãn không có trong các nguồn này.

### Năng lực vận hành gắn với rủi ro

Mọi skill trong ~/.hermes/skills/ đều có thể bị agent sửa hoặc xóa; ghi skill mặc định được commit ngay, kể cả từ bước self-improvement chạy nền, vì duyệt ghi đang tắt, và biến môi trường do skill khai báo được chuyển vào sandbox của execute_code lẫn terminal. [S7] Trên backend local, agent có quyền file của chính user; toolset không cần có thể tắt bằng hermes tools hoặc agent.disabled_toolsets trên CLI và mọi nền tảng gateway, hoặc chuyển sang Docker. Scanner cho skill do agent tạo mặc định tắt. memory.write_approval cũng mặc định tắt; khi bật, bản self-improvement nền được xếp chờ /memory approve hoặc reject thay vì ghi thẳng. hermes update là lệnh áp dụng bản mới; backup trước update mặc định ở mức quick, gồm pairing, cron, config và auth. Trang skill và trang cấu hình vẫn mô tả ghi tự do khi công tắc duyệt tắt, lệch với ô hardening cuối hè trong bảng về duyệt ghi skill và memory. [S20]

API server mặc định tắt và chỉ lắng nghe 127.0.0.1; khi bật, mọi request có API_SERVER_KEY dùng toàn bộ toolset của agent, gồm lệnh terminal, và Jobs API tạo, sửa rồi chạy cron job ngay (prompt, lịch, skill, provider, đích giao). [S9]

### Mô hình an toàn và giới hạn được ghi

Chính sách coi hệ điều hành là ranh giới duy nhất trước LLM đối nghịch. Cổng duyệt, redaction đầu ra, pattern scanner và tool allowlist không phải containment; denylist shell không đầy đủ về cấu trúc vì shell Turing-complete, chỉ bắt lỗi khi mô hình còn hợp tác, không phải đầu ra đối nghịch, và bypass các cổng đó nằm ngoài phạm vi nhận báo cáo lỗ hổng. Cô lập terminal dạng container, máy remote hoặc cloud sandbox chỉ giam lệnh shell và thao tác file đi qua shell; không giam process Python của agent, gồm execute_code (subprocess trên host), process con MCP, nạp plugin, hook và skill import trong interpreter. Posture được hỗ trợ khi nhận nội dung ngoài tầm kiểm soát của người vận hành, hoặc khi triển khai production hay dùng chung, là bọc cả cây process bằng Docker image và Compose của Hermes hoặc NVIDIA OpenShell. Backend local với đầu vào không tin cậy, hoặc kỳ vọng sandbox terminal giam các đường không phải shell, nằm ngoài posture đó. [S10][S11][S15]

Checkpoint là tùy chọn và tắt mặc định (docs ghi opt-in as of v2). Với terminal backend docker, singularity, modal, daytona, vercel_sandbox hoặc container plugin, Hermes không chụp các path sandbox, không ghi sổ lần agent ghi, và /rollback từ chối diff lẫn restore trên CLI và trong chat gateway. [S12]

Managed scope v1 không phải ranh giới chống agent: chỉ cưỡng chế bằng quyền file, mang tính khuyến cáo nếu chạy root hoặc nếu ai đó ghi được hay trỏ lại thư mục managed (kể cả bằng HERMES_MANAGED_DIR), file .env managed là 0644, và agent vẫn đổi được biến managed trong shell của subprocess của chính nó. [S13]

iron-proxy là egress tùy chọn, tắt mặc định (tắt thì no-op hoàn toàn), và ở bản tài liệu này chỉ nối vào backend Docker; Modal, Daytona, SSH và Singularity chưa nhận biến proxy hay mount CA. Chính mô hình này không chống host đã bị chiếm, process sandbox vượt HTTPS_PROXY bằng raw socket, đẩy dữ liệu tới host nằm trong allowlist, credential AWS Bedrock SigV4 hoặc GCP Vertex để lại trong sandbox, và cùng uid đọc secret trong bộ nhớ proxy qua core dump hoặc /proc/<pid>/mem. [S14]

Khi chưa có allowlist và chưa bật GATEWAY_ALLOW_ALL_USERS thì mọi người nhắn gateway bị từ chối; cron, hermes chat -q, webhook, msgraph_webhook và api_server mặc định từ chối lệnh nguy hiểm, trong đó approve nghĩa là tự duyệt còn rule command_allowlist vẫn chạy dưới deny; tắt approval hoặc bật YOLO bỏ kiểm tra lệnh nguy hiểm trừ hardline blocklist; docker, singularity, modal, daytona và vercel_sandbox bỏ hẳn các kiểm tra đó vì coi container là ranh giới; write-guard chỉ phủ write_file và patch, deny rule không phải sandbox năng lực của OS; tên trong docker_forward_env có thể bị đọc rồi gửi đi, và biến required_environment_variables do skill khai báo vẫn vào Docker dù không nằm trong danh sách forward; không đưa khóa API nhà cung cấp và token gateway vào env_passthrough. Checklist production: không bao giờ GATEWAY_ALLOW_ALL_USERS=true, dùng terminal.backend docker, chmod 600 ~/.hermes/.env, không chạy gateway bằng root, không đặt terminal.cwd trên thư mục nhạy cảm, chạy hermes update đều. [S8][S19]

### Ưu điểm và nhược điểm

Sự kiện có lợi là các mốc hardening và cô lập profile trong bảng, cùng các mặc định đóng và công tắc đã nêu (gateway, phiên không người trực, API server, duyệt ghi, tắt toolset, backup trước cập nhật). Đánh giá tách riêng: chúng không phải containment, và mất đúng phần việc mà chính sách gọi là ngoài posture được hỗ trợ hoặc khi mặc định bị đảo.

Nhược điểm chỉ lấy từ lỗ hổng đã ghi và giới hạn docs tự nhận, không lấy từ cảm nhận. Tab Security Advisories của chính repo không có advisory nào lúc đọc, trong khi GitHub Advisory Database — không phải tab đó — ghi CVE-2026-53870: bản trước 0.16.0 tạo response_store.db và webhook_subscriptions.json với mode 0o644, user local đọc được lịch sử hội thoại, tool payload, prompt và HMAC secret theo route; bản ghi đã vá là 0.16.0; NVD công bố 17/6/2026, rà soát 19/6/2026. [S17][S18] Các giới hạn còn lại là những gì mục mô hình an toàn đã thừa nhận.

### Quản trị khi tự host trên máy chứa dữ liệu nhạy cảm

Checklist trang Security muốn terminal chạy trong container thay vì quyền file của user trên máy local; chính sách bảo mật vẫn coi việc bọc cả cây process là posture được hỗ trợ khi tài liệu hoặc người nhắn không nằm trong tầm kiểm soát. Hai lớp không thay nhau. Credential chỉ để ở file credential của operator với quyền chặt, không đưa vào config chính hay VCS; nếu dùng OpenShell thì dùng Provider store. Không đưa gateway hoặc API ra Internet công cộng khi chưa có VPN, Tailscale hoặc firewall. Mỗi adapter lộ mạng phải có allowlist, và mọi caller trong allowlist được tin ngang nhau. Skill và plugin bên thứ ba chỉ cài sau khi đọc mã Python và script: skill chạy Python tùy ý lúc import, Skills Guard chỉ là công cụ hỗ trợ đọc, còn việc gỡ credential khỏi shell, MCP, script cron và process con execute_code không phải containment vì code trong process đọc được credential đang nằm trong bộ nhớ. [S16]

Với kho tài liệu nội bộ, giữ nguyên các mặc định từ chối và checklist đã nêu; để API server tắt; không bật cho phép mọi người dùng gateway; không tắt approval và không dùng YOLO; không đưa secret nhà cung cấp hay token gateway vào luồng chuyển biến môi trường; tắt toolset không phục vụ việc cần làm; không trỏ thư mục làm việc của terminal vào kho nhạy cảm; không giao cron hoặc Jobs API cho phiên không người duyệt. Nếu vẫn dùng vòng tự ghi skill và memory, bật duyệt ghi và scanner cho skill do agent tạo trước khi để bước nền chạy. Không coi checkpoint, managed scope hay iron-proxy là lưới đủ cho mọi backend: checkpoint không phủ terminal container, managed scope không chặn agent, iron-proxy tắt sẵn và mới nối Docker. Cập nhật bằng hermes update, vốn đã kèm backup quick.

### Điều chưa xác minh được

Không có ngày cho nền tảng pre-public, không có release note cho các bản nằm giữa các hàng trong bảng, và không có ngày phát hành của bản vá 0.16.0 — chỉ có phiên bản vá theo advisory. Nội dung curated notes bị hoãn không nằm trong note đã đọc. Không có đặc tả MEMORY.md, curator, delegation, computer use hay web dashboard. Không có nguồn sơ cấp trong tập đã đọc xác nhận liên hệ với dòng mô hình Nous Hermes hoặc OpenHermes. SSH chỉ được ghi là chưa nhận biến và mount CA của iron-proxy, chưa có mô tả đủ về backend SSH. Vault chỉ xuất hiện trong bản vá cô lập profile, chưa có đặc tả kho secret riêng ngoài file credential, .env managed và iron-proxy. Canary không kèm ghi chú chức năng. Chưa thấy nguồn nào cho biết lệch “luôn duyệt ghi” và “ghi tự do khi công tắc tắt” đã được làm thống nhất ở bản sau hay chưa.
</report-body>

---

