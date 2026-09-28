# Báo Cáo Phản Biện Chéo Độc Lập — Grok 4.7 Thẩm Định Kế Hoạch MCP Tham Vấn Peer Review

**Thời điểm**: 2026-09-28 22:30 ICT  
**Thực hiện**: Grok 4.7 (Auditor & Peer Reviewer)  
**Đối tượng**: Kế hoạch thiết lập MCP Server `peer_consultant` cho Hermes Agent kết nối Telegram để tham vấn Grok và Antigravity.  
**Tài liệu đối soát**: `.md/peer_exchange/prompt_grok_review_peer_consultation_mcp.md`, cấu hình `~/.grok/config.toml`, `~/.gemini/antigravity-cli/settings.json`, mã nguồn Hermes MCP loader.

---

## Phán Quyết Của Grok: CHẤP THUẬN CÓ ĐIỀU KIỆN (APPROVE WITH MODIFICATIONS)

> *"MCP server chạy qua stdio là ranh giới kiến trúc hoàn toàn chính xác. Tuy nhiên, cách gọi lệnh ban đầu trong kế hoạch chưa phải là mô hình least-privilege (đặc quyền tối thiểu). Nếu triển khai đúng như bản thảo ban đầu, bạn vô tình trao cho Telegram một Agent thứ hai có toàn quyền chạy lệnh tự động (always-approve)."*

### Bảng Điểm Phản Biện (Scorecard)

| Tiêu chí | Điểm | Nhận định của Grok |
| :--- | :---: | :--- |
| **Cô lập an ninh (Security Isolation)** | **2/10** | Cả hai CLI (`grok` và `agy`) trên máy chủ đều đang cấu hình chính sách `always-approve` và chạy trong thư mục repo. Telegram sẽ gián tiếp lấy lại quyền chạy shell, git, docker và đọc file secret nếu không đặt cờ chặn. |
| **Đồng thời & Hiệu năng (Concurrency & Performance)** | **4/10** | Chưa có khóa đồng thời (`Semaphore`), cấu hình timeout chưa đồng bộ giữa Hermes và CLI con, và prompt dài sẽ làm sập lệnh `execve` của Linux nếu truyền qua tham số dòng lệnh. |
| **Tuân thủ giao thức (Protocol Conformance)** | **4/10** | Cú pháp `server:tool` trong `platform_toolsets` không hợp lệ trong Hermes. Cần khai báo tên server `peer_consultant` và lọc tool bằng `mcp_servers.peer_consultant.tools.include`. |
| **Tuân thủ KISS** | **5/10** | Thiết kế 1 file server stdio là đơn giản, gọn gàng, nhưng cần hoàn thiện bộ cờ thực thi thực tế. |

---

## 1. Những Lỗ Hổng Chí Mạng Được Grok Vạch Ra

### A. Nguy cơ Rò Rỉ Quyền Hạn Từ Cấu Hình Local của Grok & Antigravity
1. **Lỗ hổng Grok**: File `~/.grok/config.toml` trên máy chủ đang đặt `permission_mode = "always-approve"`. Nếu chỉ gọi `grok -p "<prompt>"`, Grok sẽ khởi động với tư cách là một AI Agent có đầy đủ công cụ. Kẻ tấn công trên Telegram có thể gửi prompt yêu cầu Grok đọc file `~/.hermes/config.yaml`, `~/.hermes/.env` hoặc chạy lệnh bash $\to$ Grok sẽ tự động thực thi và gửi nội dung secret về Telegram!
   - **Giải pháp**: BẮT BUỘC phải truyền:
     - `--permission-mode dontAsk`
     - `--sandbox read-only`
     - `--tools read_file,grep,list_dir`
     - Cùng danh sách cấm tuyệt đối: `--deny "Bash(*)"`, `--deny "Edit(*)"`, `--deny "Read(~/.hermes/**)"`, `--deny "Read(~/.ssh/**)"`, `--deny "Read(**/.env)"`.
     - Đặt `GROK_MEMORY=0` để không làm ô nhiễm bộ nhớ của Grok.

2. **Lỗ hổng Antigravity**: File `~/.gemini/antigravity-cli/settings.json` đang đặt `toolPermission: always-proceed`, cho phép tự động chạy `docker compose`, `npm install`, ghi file repo.
   - **Giải pháp**: BẮT BUỘC phải cô lập `HOME` của `agy` sang thư mục riêng: `/home/vvc/.hermes/peer-consultant/agy-home` với file `settings.json` độc lập từ chối toàn bộ: `write_file(*)`, `command(*)`, `unsandboxed(*)`, và các thư mục nhạy cảm.

### B. Giới Hạn Chiều Dài Tham Số Dòng Lệnh Linux (`execve` 128 KiB)
- Nếu người dùng gửi tài liệu dài hoặc codebase lớn, việc truyền thẳng prompt vào argument `grok -p "<prompt>"` sẽ khiến Linux văng lỗi `Argument list too long` (giới hạn 128 KiB).
- **Giải pháp**:
  - Với Grok: Ghi prompt ra file tạm `0600` và dùng `--prompt-file <path>`.
  - Với Antigravity: Truyền prompt qua `stdin` với `--input-format text`.

### C. Nguy Cơ Rơi Vào Cơ Chế Tràn Ngữ Cảnh (Spillover) Của Hermes
- Hermes có cơ chế: Nếu output của một tool vượt quá ngưỡng context budget (khoảng 19.600 ký tự với Qwen 32k), Hermes sẽ chỉ giữ 1.500 ký tự preview và đẩy toàn bộ văn bản còn lại vào file trên ổ đĩa (`~/.hermes/cache/spillover`).
- Vì giao diện Telegram **đã bị khóa công cụ đọc file**, người dùng sẽ KHÔNG THỂ đọc được phần còn lại của phản biện nếu output bị spillover!
- **Giải pháp**: Cắt gọn kết quả trả về của Grok/Antigravity ở mức **tối đa 8.000 ký tự**. 8.000 ký tự là vừa vặn nằm trọn trong context của Telegram và không bao giờ bị kích hoạt spillover.

### D. Chuẩn Hóa Khai Báo Trong Hermes `config.yaml`
- Trong `platform_toolsets.telegram`, Hermes nhận tên server `peer_consultant`, KHÔNG PHẢI `peer_consultant:consult_grok`.
- Bộ lọc danh sách tool được đặt tại `mcp_servers.peer_consultant.tools.include: [consult_grok, consult_antigravity]`.
- Trên các nền tảng khác (CLI, Discord, Slack, cron), phải gắn nhãn `no_mcp` để tránh việc MCP server bị tự động gán vào các job cron chạy ngầm không giám sát.

---

## 2. Mã Nguồn MCP Server & Cấu Hình Đã Chuẩn Hóa Theo Grok

### A. File cấu hình `~/.hermes/config.yaml`
```yaml
mcp_servers:
  peer_consultant:
    command: "/home/vvc/.hermes/installs/cc8cbe0b24121cdc/environments/8e9ad5ae5c6d4be28df51459735d1a80/venv/bin/python3"
    args: ["/home/vvc/.hermes/mcp/peer_consultant.py"]
    timeout: 180
    connect_timeout: 30
    supports_parallel_tool_calls: false
    tools:
      include: [consult_grok, consult_antigravity]
      resources: false
      prompts: false
    sampling:
      enabled: false
    elicitation:
      enabled: false

platform_toolsets:
  cli: [hermes-cli, no_mcp]
  telegram: [clarify, image_gen, memory, session_search, skills, todo, tts, vision, web, peer_consultant]
  discord: [hermes-discord, no_mcp]
  whatsapp: [hermes-whatsapp, no_mcp]
  slack: [hermes-slack, no_mcp]
  signal: [hermes-signal, no_mcp]
  homeassistant: [hermes-homeassistant, no_mcp]
  qqbot: [hermes-qqbot, no_mcp]
  yuanbao: [hermes-yuanbao, no_mcp]
  teams: [hermes-teams, no_mcp]
  google_chat: [hermes-google_chat, no_mcp]
  cron: [no_mcp]
```

### B. Logic triển khai `~/.hermes/mcp/peer_consultant.py`
- Dùng `asyncio.Semaphore(1)` khóa đồng thời tuần tự hóa các lượt gọi.
- Dùng `asyncio.create_subprocess_exec` với `start_new_session=True` và `os.killpg` dọn dẹp tiến trình con sạch sẽ khi timeout (150s).
- Ghi prompt vào temp file `0600` cho Grok và pipe qua stdin cho Antigravity.
- Truyền đầy đủ các cờ Sandbox và Deny bảo vệ bí mật tuyệt đối.
