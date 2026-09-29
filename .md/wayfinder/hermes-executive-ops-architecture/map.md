# Bản đồ Định hướng (Wayfinding Map): Kiến Trúc Điều Hành & Vận Hành An Toàn Cho Hermes Agent Trên DGX Spark
**Mã bản đồ:** `MAP-HERMES-EXECUTIVE-OPS-20260929`  
**Trạng thái:** `Completed (100% Tickets Closed — All Phases Verified & Accepted)`  
**Thẩm định đối kháng:** Grok 4.7 — Phán quyết: **ACCEPTED** (`.md/peer_exchange/grok_final_acceptance.md`)  
**Hệ thống liên quan:** 
- Hermes Agent Gateway & Telegram Integration (`~/.hermes/`, `hermes-gateway.service`)
- Hermes Executive Tools MCP Server (`scripts/hermes_executive_mcp.py`)
- DGX-ChatOps Universal Gateway Daemon (`scripts/chatops_daemon.py`, `scripts/chatops_commands.yaml`, `dgx-chatops.service`)
- Vietnamese Legal RAG Service & Neo4j Legal Graph (`services/rag-service/`, container `rag-service`, container `neo4j-graph`)
**Hạ tầng mục tiêu:** NVIDIA DGX Spark (Grace Blackwell GB10, aarch64, 128GB Unified Memory)

---

## 1. Điểm đích (Destination)

Xây dựng và hoàn thiện cấu hình kiến trúc tổng quát cho Hermes Agent hoạt động như một Trợ lý Điều hành Cấp cao (Executive Assistant) trên Telegram cho Lãnh đạo, giải quyết đồng thời hai mục tiêu chiến lược:
1. **Tối đa hóa năng lực nghiệp vụ & vận hành (Maximal Executive Utility)**:
   - Đọc, trích xuất cấu trúc văn bản hành chính/kỹ thuật đa định dạng (.doc, .docx, .pdf, .xlsx) từ cache tài liệu.
   - Tra cứu sâu kho tri thức pháp quy xây dựng Việt Nam (QCVN, TCVN, Luật, Nghị định) qua Milvus RAG v11.
   - Thẩm tra tính hiệu lực và phả hệ sửa đổi/bổ sung của văn bản qua Neo4j Legal Graph.
   - Nắm bắt trạng thái sức khỏe phần cứng DGX Spark (GPU GB10, RAM, Swap, 8-10 containers) thời gian thực.
   - Đề xuất các tác vụ vận hành hạ tầng/ứng dụng (restart container, upgrade dependencies, trigger auto-tuner) sang Telegram của Lãnh đạo dưới dạng Thẻ tương tác 1-chạm (Interactive Approval Card).
2. **Bảo đảm an toàn tuyệt đối cho hệ thống máy chủ (Zero Host Compromise)**:
   - **Cấm cấp quyền shell thô (`terminal` / `exec`)** trên kênh Telegram (ngăn chặn triệt để prompt injection / jailbreak dẫn tới remote code execution).
   - Đóng gói toàn bộ năng lực thành 1 MCP Server duy nhất (`scripts/hermes_executive_mcp.py`), loại bỏ nhu cầu mở thêm tiến trình daemon hay bus liên lạc mới (tuân thủ triệt để nguyên lý KISS & Reuse-First).
   - Tái sử dụng cổng nội bộ `:8095` của ChatOps Daemon với cơ chế xác thực bí mật cô lập (`X-ChatOps-Secret`), nonce một lần, whitelist lệnh đột biến, xác thực regex tham số, và xây dựng nội dung thẻ phê duyệt hoàn toàn từ phía máy chủ (Server-Side Title/Body Generation chống UI Spoofing).

---

## 2. Các Quyết Định Kiến Trúc Đã Chốt (Decisions Established)

- [x] **[DEC-01] Không cấp quyền shell thô trên Telegram**: Hermes trên Telegram bị tước bỏ công cụ `terminal` và lệnh khẩn cấp `/exec`. Mọi tương tác vận hành hệ thống bắt buộc phải đi qua cơ chế đề xuất có kiểm duyệt (Proposed Mutating Operations).
- [x] **[DEC-02] Kiến trúc 1 MCP Server Hợp Nhất (KISS & Reuse-First)**: Thay vì phân mảnh thành 4 MCP servers riêng biệt hoặc mở các bus hàng đợi trung gian (Redis DB 5), toàn bộ 5 công cụ điều hành được hợp nhất vào `scripts/hermes_executive_mcp.py` chạy dưới môi trường Python của nền tảng (`/home/vvc/ccba/ccba-agent-platform/.venv/bin/python`).
- [x] **[DEC-03] Kiểm soát đường dẫn đa tầng (Multi-Layer Path Guard)**:
  - Cấm tuyệt đối ký tự phân cách thư mục (`/`, `\`) và `..` trong tên tệp.
  - Kiểm tra `is_symlink()` và `lstat().st_nlink > 1` (chặn hardlink) trước khi giải quyết đường dẫn.
  - Sử dụng `path.resolve().is_relative_to(DOCS_CACHE_DIR)` để ngăn chặn triệt để tấn công prefix sibling collision.
  - Áp dụng kiểm tra an toàn cho mọi tệp sinh ra từ chuyển đổi OOXML/LibreOffice (`.docx` cùng stem với `.doc`), cả trước và sau khi `soffice` thực thi.
- [x] **[DEC-04] Xác thực trích dẫn pháp lý khớp chính xác (Exact Graph Match)**: Bỏ hoàn toàn toán tử so khớp lỏng `ENDS WITH` trong Neo4j Cypher query; chỉ khớp chính xác `d.id = $node_id OR d.doc_number = $node_id OR d.id = ('VBPL/' + $node_id)`. Các chuỗi hậu tố như `0/2021/NĐ-CP` hay `NĐ-CP` không khớp và trả về graph rỗng.
- [x] **[DEC-05] Secret Rotation & Cô lập môi trường (Secret Isolation Invariant)**:
  - Sinh khóa ngẫu nhiên mật mã 48 hex characters cho `CHATOPS_INTERNAL_SECRET`.
  - Phân quyền nghiêm ngặt `chmod 600` cho `.env` và `~/.hermes/config.yaml`.
  - Nạp biến môi trường vào tiến trình con stdio của Hermes qua cấu hình `mcp_servers.executive_tools.env`.
  - Xóa bỏ 100% fallback string trong mã nguồn và bộ kiểm thử; cập nhật đồng bộ container `smart-watchdog`.
- [x] **[DEC-06] Thẻ phê duyệt chống UI Spoofing & Khóa cứng Timeout Registry**:
  - Khi có hành động vận hành (`actions`), tiêu đề và thân thẻ Telegram bắt buộc phải sinh 100% từ mô tả lệnh trong registry và tham số đã kiểm tra regex an toàn. Toàn bộ text tự do từ client bị ghi đè.
  - Timeout của tác vụ luôn luôn lấy từ cấu hình `timeout_seconds` trong `chatops_commands.yaml`, bỏ qua hoàn toàn giá trị timeout client gửi lên (chặn đứng việc chiếm dụng runner).
- [x] **[DEC-07] Subprocess Exec qua Argv**: Chuyển toàn bộ việc thực thi shell trong `execute_shell_job` sang `asyncio.create_subprocess_exec(*argv)` với `use_shell=False` mặc định, loại bỏ rủi ro chèn ký tự điều khiển shell.

---

## 3. Danh Sách Ticket Đã Hoàn Thành (Tickets Completed)

| Mã Ticket | Tên Hạng Mục | Phạm Vi Triển Khai | Trạng Thái |
|---|---|---|---|
| **TICK-01** | Doc Cache Reader & Dual-Engine Parser | `scripts/hermes_executive_mcp.py` (`read_cached_document`), LibreOffice headless integration, `_validate_safe_path`, Symlink/Hardlink Guard | **COMPLETED** |
| **TICK-02** | Legal RAG & Graph Citations | `scripts/hermes_executive_mcp.py` (`search_legal_corpus`, `validate_legal_citation`), `services/rag-service/api/routers/graph.py` (query param `?id=`, exact Cypher match) | **COMPLETED** |
| **TICK-03** | ChatOps Live Infrastructure Probes | `scripts/chatops_daemon.py` (`GET /api/v1/probe/{probe_type}`), `scripts/hermes_executive_mcp.py` (`get_system_health`), GB10 GPU/RAM/Container live metrics | **COMPLETED** |
| **TICK-04** | Interactive Ops Propose & Telegram 1-Tap Approval | `scripts/chatops_daemon.py` (`POST /api/v1/notify`), `scripts/hermes_executive_mcp.py` (`propose_system_operation`), Whitelist 6 lệnh, Nonce binding, Anti-UI Spoofing | **COMPLETED** |

---

## 4. Kết Quả Thẩm Định Đối Kháng & Kiểm Thử Thực Nghiệm

- **Bộ kiểm thử tự động**: `tests/test_executive_ops_mcp.py` gồm **22/22 test cases đối kháng đạt 100% PASS** (thời gian chạy: 0.58s - 0.62s):
  - 5 tests kiểm tra Path Traversal (relative dotdot, absolute path, backslash, sibling prefix, no glob fallback).
  - 3 tests kiểm tra Symlink & Hardlink (direct symlink, same-stem .docx symlink, hardlink `st_nlink > 1`).
  - 2 tests kiểm tra Legal Citation (exact match `10/2021/NĐ-CP` vs suffix rejection `0/2021/NĐ-CP`, `2021/NĐ-CP`, `NĐ-CP`, `1/2021/NĐ-CP`).
  - 3 tests kiểm tra Secret Authentication (missing secret 401, wrong secret 401, rotated 48 hex secret 200).
  - 6 tests kiểm tra Action Proposal Hardening (emergency exec 403, unlisted command 403, invalid param regex 400, extra param 400, MCP client reject, anti-timeout inflation & anti-spoofing).
  - 3 tests kiểm tra Pagination & Limits (lower clamp 2000, upper clamp 12000, RAG search limit clamp 8).
- **Bộ kiểm thử hồi quy ChatOps**: `tests/test_chatops.py` đạt **62/62 test cases PASS** (100% tương thích ngược).
- **Phán quyết độc lập của Grok 4.7**:
  - Tệp báo cáo: `.md/peer_exchange/grok_final_acceptance.md`
  - Kết luận: **`ACCEPTED`** (Nghiệm thu toàn diện Bản đồ Wayfinder `MAP-HERMES-EXECUTIVE-OPS-20260929`).
