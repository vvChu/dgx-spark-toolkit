# Báo cáo Nghiên cứu & Đánh giá An ninh: Thiết lập Antigravity Tools (Antigravity Manager)

> **Mã nghiên cứu:** `research-antigravity-tools-security-audit`  
> **Thời gian đánh giá:** 2026-09-27  
> **Đối tượng khảo sát:** Hệ thống Antigravity Tools (Antigravity Manager v4.8.1 / Tauri v2) và cấu hình dịch vụ trên máy chủ nội bộ.  
> **Quy chuẩn đánh giá:** Double-Pass Adversarial Review, CWE Top 25, Maskara Guardrail, Google Terms of Service.

---

## 1. Tóm tắt Thực thi (Executive Summary)

Sau khi rà soát toàn diện mã nguồn (`src-tauri` Rust backend, React frontend), tệp cấu hình thực tế (`~/.antigravity_tools/gui_config.json`), tiến trình mạng (`0.0.0.0:8045`), cơ chế lưu trữ tài khoản và dịch vụ tự động cập nhật `systemd`, câu trả lời trực diện cho câu hỏi *"Setup đã đảm bảo an toàn tuyệt đối cho tài khoản chưa?"* là:

> ⚠️ **KHÔNG ĐẢM BẢO AN TOÀN TUYỆT ĐỐI.**  
> Hiện tại hệ thống đang tồn tại **4 lỗ hổng bảo mật nghiêm trọng (2 Critical, 2 High)** đe dọa trực tiếp đến tính an toàn của các tài khoản Google đã nạp, đồng thời mang rủi ro nội tại về việc **bị Google cấm (ban/suspend) tài khoản** do vi phạm Chính sách Dịch vụ (ToS).

### Bảng tóm tắt các phát hiện trọng yếu:

| Mức độ | Lỗ hổng / Rủi ro | Mô tả ngắn | Trạng thái thực tế |
| :--- | :--- | :--- | :--- |
| 🔴 **CRITICAL** | Lộ Admin API qua LAN/Tailscale + Fallback Key | `allow_lan_access: true` bind `0.0.0.0:8045`. `admin_password: null` khiến API Key Proxy kiêm luôn quyền Admin. Endpoint `/api/accounts/export` trả về toàn bộ `refresh_token` gốc dạng plaintext. | Đã chứng minh thực tế (PoC thành công) |
| 🔴 **CRITICAL** | Cập nhật tự động thiếu chữ ký số (CWE-494) | Script `antigravity-tools-autoupdate` tải nhị phân AppImage trực tiếp từ GitHub Releases qua cronjob hàng ngày mà không xác thực SHA-256 hay chữ ký GPG. | Kích hoạt tự động lúc 03:30 mỗi ngày |
| 🟠 **HIGH** | Lưu trữ Token không mã hóa (CWE-312) | Toàn bộ `refresh_token`, `access_token`, `id_token` lưu trong các file JSON thuần tại `~/.antigravity_tools/accounts/` với quyền `0664`. | Đang lưu plaintext |
| 🟠 **HIGH** | Vi phạm Google ToS & Nguy cơ Ban Account | Reverse-engineer API nội bộ (`cloudcode-pa.googleapis.com`), xoay tua token qua headless proxy dễ bị hệ thống telemetry của Google gắn cờ lạm dụng. | Rủi ro pháp lý & vận hành |
| 🟡 **MEDIUM** | Lộ lọt dữ liệu prompt trong DB cục bộ | Toàn bộ prompt, response, thinking content lưu trong `proxy_logs.db` (35.8 MB) và `thinking_store.db` không mã hóa. | Đang lưu trữ |

---

## 2. Hiện trạng Setup & Phương pháp Khảo sát (Methodology)

### 2.1. Kiểm tra tiến trình và mạng
- Tiến trình `antigravity-tools` (PID `898769`) đang chạy ngầm, lắng nghe tại cổng `*:8045` (`0.0.0.0:8045`).
- Máy chủ hiện kết nối đồng thời: Mạng nội bộ LAN (`192.168.1.47`), Wi-Fi (`192.168.1.48`), và mạng Tailscale VPN (`100.83.192.30`).
- File cấu hình `~/.antigravity_tools/gui_config.json` chỉ định:
  - `"allow_lan_access": true`
  - `"port": 8045`
  - `"auth_mode": "all_except_health"`
  - `"admin_password": null`

### 2.2. Kiểm tra mã nguồn Rust Backend (`src-tauri`)
- Cơ chế bind địa chỉ (`src-tauri/src/proxy/config.rs`):
  ```rust
  if self.allow_lan_access { "0.0.0.0" } else { "127.0.0.1" }
  ```
- Cơ chế xác thực Admin (`src-tauri/src/proxy/middleware/auth.rs`):
  ```rust
  let authorized = if force_strict {
      match &security.admin_password {
          Some(pwd) if !pwd.is_empty() => api_key.map(|k| k == pwd).unwrap_or(false),
          _ => api_key.map(|k| k == security.api_key).unwrap_or(false), // Fallback về proxy api_key!
      }
  }
  ```

---

## 3. Phân tích Chi tiết Các Rủi ro An ninh

### 3.1. [CRITICAL] Trích xuất toàn bộ Google Refresh Tokens qua LAN / VPN
- **Cơ chế lỗi:** Do `admin_password` không được cấu hình (`null`), hệ thống tự động cho phép bất kỳ ai sở hữu `api_key` của proxy được quyền truy cập vào toàn bộ các endpoint quản trị `/api/*`.
- **Hành vi kiểm chứng (Proof of Concept):**
  Thực hiện gửi một request POST nội bộ:
  ```bash
  curl -s -X POST \
    -H "Authorization: Bearer <PROXY_API_KEY>" \
    -H "Content-Type: application/json" \
    -d '{"accountIds":["<TARGET_ACCOUNT_ID>"]}' \
    http://127.0.0.1:8045/api/accounts/export
  ```
- **Kết quả:** Endpoint `/api/accounts/export` trả về trực tiếp mảng đối tượng chứa cặp `{"email": "...", "refresh_token": "..."}` hoàn toàn dưới dạng plaintext.
- **Hệ quả:** Bất kỳ thiết bị nào cùng mạng LAN (192.168.1.x) hoặc người dùng được chia sẻ API key để dùng LLM đều có thể chiếm đoạt vĩnh viễn quyền kiểm soát toàn bộ 12 tài khoản Google trên máy chủ mà người dùng không hề hay biết.

---

### 3.2. [CRITICAL] Tấn công Chuỗi cung ứng (Supply Chain Attack) qua Auto-Updater
- **Vị trí:** `~/.local/bin/antigravity-tools-autoupdate` kết hợp `systemd/user/antigravity-tools-autoupdate.timer`.
- **Cơ chế:** Mỗi ngày lúc 03:30 sáng, cronjob tự động:
  1. Gọi API GitHub của repository bên thứ ba `lbjlaq/Antigravity-Manager`.
  2. Tải trực tiếp file nhị phân `.AppImage`.
  3. Cấp quyền thực thi `chmod +x` và ghi đè vào `$HOME/Applications/Antigravity.Tools.AppImage`.
  4. Khởi động lại service bằng quyền user hiện tại.
- **Lỗ hổng:** Hoàn toàn **không kiểm tra mã băm SHA-256** và **không kiểm tra chữ ký số GPG/PGP**.
- **Hệ quả:** Nếu tài khoản GitHub của tác giả hoặc kho chứa release bị xâm nhập (compromised), máy chủ của bạn sẽ tự động tải về và chạy mã độc với đầy đủ quyền hạn truy cập tệp tin, dữ liệu, SSH keys và token của tài khoản người dùng.

---

### 3.3. [HIGH] Dữ liệu Xác thực (Tokens) Lưu trữ Plaintext
- **Vị trí:** Thư mục `~/.antigravity_tools/accounts/` chứa danh sách các tệp JSON đại diện cho 12 tài khoản.
- **Chi tiết:** Trong mỗi tệp JSON, các trường nhạy cảm nhất bao gồm:
  - `access_token`
  - `refresh_token`
  - `id_token`
  - `email`
- **Lỗ hổng:**
  - Không có bất kỳ lớp mã hóa bảo vệ nào (không dùng Secret Service API của Linux, không dùng GNOME Keyring, không dùng mã hóa đối xứng AES bằng Master Password).
  - Quyền file mặc định là `0664` (`-rw-rw-r--`), cho phép đọc rộng hơn mức cần thiết. Bất kỳ script hoặc tiến trình nào chạy dưới quyền người dùng đều đọc được ngay lập tức.

---

### 3.4. [HIGH] Rủi ro Vi phạm Chính sách Google (ToS) & Nguy cơ Bị Khóa Tài Khoản Hàng Loạt
- **Bản chất công nghệ của Antigravity Tools:**
  - Phần mềm không sử dụng Google Cloud Vertex AI API chính thống (trả phí theo lượt).
  - Phần mềm hoạt động bằng cách **giả lập/bọc lại (reverse-engineer)** các endpoint nội bộ của Google Cloud Code / Antigravity IDE:
    - `https://cloudcode-pa.googleapis.com/v1internal`
    - `https://daily-cloudcode-pa.googleapis.com/v1internal`
  - Hệ thống sử dụng cơ chế xoay tua (multi-account matrix) để lách hạn ngạch (quota bypass).
- **Cơ chế giám sát của Google:**
  - Google thu thập telemetry từ client (User-Agent, môi trường thực thi, địa chỉ IP xuất phát, tần suất request, sự bất thường giữa các phiên đăng nhập).
  - Khi phát hiện một IP máy chủ / datacenter bắn liên tục hàng loạt request với nhiều tài khoản xoay tua mà không có môi trường IDE tương tác người dùng, Google có thể:
    1. Đưa IP hoặc Client ID vào diện chặn (HTTP 403 Forbidden). Trong danh sách tài khoản hiện tại trên máy, đã có tài khoản bị đánh dấu `is_forbidden: true` (`ibstpm@gmail.com`).
    2. Thu hồi toàn bộ Refresh Token của các tài khoản liên đới.
    3. Khóa hoặc đình chỉ tài khoản Google cá nhân vì hành vi lạm dụng tự động hóa trái phép (Violating Terms of Service regarding reverse engineering and unauthorized automated access).
- **Kết luận:** Ngay cả khi bảo mật phần cứng tuyệt đối, **việc sử dụng các công cụ proxy bọc API nội bộ như Antigravity Tools vốn dĩ không bao giờ có thể "An toàn tuyệt đối" đối với sự tồn tại của tài khoản Google.**

---

### 3.5. [MEDIUM] Rò rỉ Dữ liệu Prompt và Lịch sử Suy luận (Inference Leak)
- **Vị trí:** `~/.antigravity_tools/proxy_logs.db` (kích thước ~35.8 MB) và `thinking_store.db`.
- **Chi tiết:** Lưu trữ chi tiết nội dung trao đổi, prompt nghiệp vụ, mã nguồn và câu trả lời mô hình dưới dạng SQLite thuần.
- **Rủi ro:** Khi sử dụng proxy cho các dự án nội bộ nhạy cảm, toàn bộ dữ liệu dự án bị lưu vết cục bộ không mã hóa và có thể bị đọc trộm nếu máy bị truy cập trái phép.

---

## 4. Ma trận Đánh giá Tổng thể

| Tiêu chí | Điểm / Nhận định | Phân tích chi tiết |
| :--- | :---: | :--- |
| **Giá trị sử dụng** | **Cao (8/10)** | Cung cấp proxy tiện lợi, tận dụng quota Gemini Pro/Flash/Claude cho các công cụ lập trình. |
| **Độ an toàn Token** | **Rất thấp (2/10)** | Token lưu plaintext, Admin API bị lộ qua LAN/Tailscale, cho phép trích xuất token dễ dàng. |
| **Rủi ro Chuỗi cung ứng** | **Cao (3/10)** | Auto-updater tải binary trực tiếp từ GitHub mỗi ngày mà không verify hash. |
| **Tuân thủ Google ToS** | **Vi phạm (1/10)** | Dùng endpoint nội bộ, có nguy cơ bị ban/flag tài khoản bất cứ lúc nào. |
| **Đánh giá chung** | **KHÔNG AN TOÀN** | Cần can thiệp cấu hình khẩn cấp để chặn các lỗ hổng rò rỉ dữ liệu. |

---

## 5. Kế hoạch Khắc phục & Khuyến nghị Hành động Khẩn cấp

Để bảo vệ tối đa các tài khoản Google và an ninh máy chủ, cần thực hiện ngay các bước sau:

### Bước 1: Khóa chặt mạng và đặt mật khẩu Admin độc lập (Khẩn cấp)
Sửa tệp `~/.antigravity_tools/gui_config.json`:
1. Chuyển `"allow_lan_access": false` để proxy chỉ lắng nghe tại `127.0.0.1` (ngăn toàn bộ truy cập từ LAN và Tailscale).
2. Thiết lập `"admin_password"` với một chuỗi ký tự bí mật mạnh ngẫu nhiên (tách biệt hoàn toàn với `api_key` của proxy).
3. Đổi `"api_key"` proxy hiện tại sang một khóa mới để hủy hiệu lực của key cũ đã bị lộ.

### Bước 2: Vô hiệu hóa Auto-Updater không an toàn từ bên thứ ba
1. Tắt và dừng systemd timer:
   ```bash
   systemctl --user stop antigravity-tools-autoupdate.timer
   systemctl --user disable antigravity-tools-autoupdate.timer
   ```
2. Chỉ cập nhật phiên bản mới khi tự tay kiểm tra mã nguồn (build từ source `Codebase/Antigravity-Manager`) hoặc kiểm tra SHA-256 đối chiếu với release tag chính thức.

### Bước 3: Siết chặt phân quyền tệp tin cục bộ
Chạy lệnh phân quyền hạn chế tối đa việc đọc file tài khoản:
```bash
chmod 700 ~/.antigravity_tools
chmod 600 ~/.antigravity_tools/accounts/*.json
chmod 600 ~/.antigravity_tools/*.json
chmod 600 ~/.antigravity_tools/*.db*
```

### Bước 4: Chiến lược phân tách tài khoản Google (Nguyên tắc Cách ly Rủi ro)
- **Tuyệt đối không dùng tài khoản Google chính (Primary/Main Account)** chứa email quan trọng, Google Drive cá nhân, hoặc dịch vụ tài chính/ngân hàng trong Antigravity Tools.
- **Chỉ sử dụng tài khoản phụ (Throwaway / Disposable Accounts):** Chuẩn bị tinh thần các tài khoản này có thể bị Google đánh cờ (flag), chặn quyền truy cập Cloud Code, hoặc khóa bất cứ lúc nào khi Google cập nhật thuật toán phát hiện gian lận hạn ngạch.
