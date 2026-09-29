# Platform-Aware KISS Standard v2.0 (Review Guideline)

> **Trạng thái**: Chuẩn mực Đánh giá Thiết kế (Review Guideline) áp dụng cục bộ tại Spoke `dgx-spark-toolkit`.
> **Nguồn gốc**: Đồng thuận phản biện đối kháng độc lập giữa Grok 4.7 xhigh và Antigravity (Tháng 9/2026), hoàn thiện từ bản thảo Platform-Aware KISS ban đầu.
> **Quan hệ với Hub**: Ban hành dưới dạng **Review Guideline** nội bộ. Việc chuyển đổi thành Cổng CI bắt buộc (Hard CI Gate) trên toàn Hub đang chờ giải quyết 4 điều kiện bảo lưu nền tảng (Platform Reservations) được nêu ở Mục 5.

---

## 1. Lời mở đầu & Phạm vi áp dụng

Nguyên tắc **Platform-Aware KISS v2.0** giải quyết mâu thuẫn giữa nguyên tắc KISS truyền thống ("viết script đơn giản 10–15 dòng trong file hiện có") và nguyên tắc Tái sử dụng của Nền tảng CCBA ("không tạo data silo cục bộ khi nền tảng đã có Seam").

Văn bản này đóng vai trò là **Review Guideline** định hướng cho các Agent và Kỹ sư khi lập kế hoạch, phản biện kiến trúc và rà soát pull request. Các tiêu chí phức tạp mã nguồn (Cyclomatic Complexity, SLOC) và ma trận tiện ích mã nguồn ($U$) tại tài liệu này được áp dụng qua quá trình thẩm định (peer review), chưa cấu hình thành lệnh fail tự động trong CI cho đến khi hoàn thành bộ linter hợp đồng tại Điều khoản E.

---

## 2. Các điều khoản cốt lõi (Clauses 4.1 – 4.8)

### 4.1. Điều khoản A — Ba loại hiện vật, một chỉ mục hợp đồng

Trước khi bậc 1 được phép là cổng chặn, Hub phát hành `seam-contracts.yaml` (tên có thể đổi, hình dạng thì không). Mỗi card:

```yaml
seam_id: legal_markdown.v1
kind: package            # package | skill | workflow
import_path: ccba_markdown:ConversionPipeline
capability:
  in: [pdf, docx]
  out: [markdown]
hardware: [any]          # any | linux_cuda | dgx_spark
failure_modes: [corrupt_pdf, timeout, unsupported_layout]
owner: hub-docs
version: "1.4.2"
health_check: python -m ccba_markdown health
forbidden_substitute_imports: [fpdf, direct_pymupdf_in_spoke]
```

- `kind: skill` ghi `command` và đường dẫn `SKILL.md`.
- `kind: workflow` ghi tên workflow.
- Card skill không có `import_path`. Agent tái sử dụng skill bằng cách nạp skill. Agent tái sử dụng package bằng cách import symbol trong `import_path`.

Lệnh tra cứu trả card, không trả đoạn mô tả trúng từ:

```text
ccba-platform find-seam --in pdf --out markdown --hardware any
```

Không có card khớp thì kết quả là `NO_MATCH` kèm hash của chỉ mục đã đọc. `NO_MATCH` là chứng cứ "chỉ mục này không có", không phải chứng cứ "nền tảng không có". Khi catalog trên đĩa và chỉ mục hợp đồng lệch nhau, bậc 1 không được quyền kết luận.

`compile_catalog.py` ghi ra artifact build. Nó không ghi đè `catalog.yaml` của một Spoke chỉ checkout một phần skill.

Cho đến ngày lệnh trên tồn tại và có test trong Hub, bậc 1 ở Spoke là nghĩa vụ **đọc** `catalog.yaml` và `__all__` của package đã cài. Thiếu CLI không bị diễn giải thành quyền viết Seam mới, cũng không bị diễn giải thành quyền đứng máy.

### 4.2. Điều khoản B — Cửa thoát có hạn (circuit breaker của Spoke)

Khi card tồn tại mà health check của card thất bại (`ImportError`, lệch tag `hardware`, timeout quá ngân sách đã ghi trên card, hoặc regression đã có issue Hub), Spoke được gọi Quarantine Adapter:

- Cùng Protocol với Seam.
- Nằm ở đường dẫn cố định `adapters/quarantine/<seam_id>.py`.
- Mang marker một dòng, máy kiểm được:

```text
# ccba:seam-escape seam_id=legal_markdown.v1 until=2026-10-13 issue=https://github.com/vvChu/ccba-agent-platform/issues/N reason=hardware_mismatch
```

`reason` thuộc tập đóng: `hardware_mismatch | seam_regression | health_timeout | version_conflict`.

CI:
- Fail khi `until` nhỏ hơn ngày chạy.
- Fail khi mã sản xuất import thư viện nằm trong `forbidden_substitute_imports` mà không có marker còn hạn.
- Fail khi health check của Seam đã xanh trở lại mà file quarantine vẫn được import.
- Một lần gọi thử Seam (half-open) trên mỗi lần deploy khi mạch đang mở.

Script đặt tên tự do trong `scripts/` không phải trạng thái mở của cầu dao. Không có marker thì không có ngoại lệ.

### 4.3. Điều khoản C — Spike có hạn, tách khỏi cây sản xuất

Thí nghiệm hợp pháp khi đủ cả năm điều kiện:

1. File nằm trong `.md/scratch/spikes/` hoặc trong Spoke có `guardrails.sandbox_mode: true`.
2. Đầu file ghi câu hỏi thiết kế, ngày hết hạn không quá 7 ngày, và điều kiện xóa.
3. Đồ thị import của `services/` và package công khai không trỏ tới file đó. CI fail nếu trỏ.
4. File không được copy vào `scripts/` hoặc `services/` trong cùng thay đổi với lời hứa refactor sau.
5. Khi câu hỏi đã có lời, phần logic thuần đi theo `prototype_logic.md` hoặc `/ccba-promote-sandbox`. Vỏ thí nghiệm bị xóa trong cùng PR nâng cấp.

Anti-Phantom Deferral áp vào PR nào thêm mã vào cây sản xuất kèm câu "phase sau sẽ tích hợp". Spike trong scratch không cần xin Seam.

### 4.4. Điều khoản D — Bậc KISS viết lại cho hết vùng chết

| Bậc | Khi nào | Việc làm |
|---|---|---|
| 1. Card khớp | Card cùng `in`/`out`/`hardware`, health check xanh | Gọi `import_path` hoặc nạp skill/workflow đúng `kind`. |
| 2. Lần đầu, trong module chủ | Chưa có card khớp. Logic thuộc file đang sửa. Complexity của hàm mới ≤ 10. | Viết trong file đó. Trần 15 dòng bị xóa. |
| 3. Theo dõi | Bản sao thứ hai trong cùng package hoặc khác Spoke, hành vi còn trùng | Mở issue "watch", ghi hai đường dẫn. Chưa tách package. |
| 4. Tách Seam | Bản sao thứ ba, hoặc hai bản đã lệch hành vi, và có đủ adapter sản xuất + adapter test | Đưa vào package chủ của năng lực. Public Hub chỉ khi package đó thuộc Hub. Một adapter thì Seam stays internal. |

Câu hỏi 10–15 dòng giữ vai trò gợi ý cho thay đổi nhỏ trong file hiện có. Nó không còn là điều kiện duy nhất của bậc 2.

**Cổng chất lượng hàm (Review & Gating):**
- **Complexity $\ge 15$**: Lỗi review (yêu cầu cấu trúc lại trước khi merge; tự động fail CI khi linter Điều khoản E được kích hoạt).
- **Complexity $\ge 10$**: Cảnh báo review (yêu cầu giải trình hoặc tách nếu có nhánh logic độc lập).
- **SLOC > 80 và Complexity $\le 10$**: Người review ghi chú xác nhận khối là một trình tự đơn điệu (linear sequential processing) hoặc chỉ ra tên phần cần tách. Không cơ học tách hàm chỉ để ép số dòng xuống dưới 50 nếu làm gãy luồng xử lý tuần tự.
- Hàm sinh mã hoặc bảng ánh xạ (regex pháp lý, bảng mã lỗi) được đo complexity trên phần điều khiển, không đo trên từng nhánh thay thế của một `re.sub`.

### 4.5. Điều khoản E — Cổng CI biết phân biệt cái gì

Chỉ những kiểm này là tất định. Phần còn lại là review.

1. Mỗi PR đụng `services/**/*.py` hoặc `packages/**/*.py` chạy kiểm tra import: nếu file import một tên trong `forbidden_substitute_imports` của bất kỳ card nào, file phải chứa marker `ccba:seam-escape` còn hạn **hoặc** phải import `import_path` của card đó.
2. Marker hết hạn thì fail, kể cả khi không có diff mới trên dòng đó (quét toàn cây).
3. `services/**/scripts/*.py` vào ngân sách, với một allowlist theo vai trò (`daemon`, `benchmark`, `audit`) ghi trong YAML, không theo tiền tố `check_`.
4. Archive không phải cách xử lý mặc định của vượt ngân sách. Báo cáo in vai trò của từng tệp. Daemon trong allowlist không bị đề nghị chuyển vào `.md/archive/legacy_scripts/`.
5. Không cấm `re`, `pathlib`, hay `json`. Cấm nằm ở import của thư viện đã có chủ Seam, và chỉ sau khi card tồn tại.
6. Âm tính đã biết, ghi thẳng vào tài liệu cổng: script không import thư viện cấm, mà tự viết HTTP client, sẽ không bị AST này thấy. Bắt lớp đó bằng card có `capability` và một test hợp đồng ở Hub, không bằng regex trên thân hàm.

Dương tính giả phải có test trong repo của linter: file ví dụ của Seam (regex hợp pháp), file quarantine còn hạn, file quarantine hết hạn, file `services/` dùng PyMuPDF trong khi card đã cấm.

### 4.6. Điều khoản F — Thang điểm có chiều, có chứng cứ, bỏ tích

Bước 1 là cổng nhị phân, không chấm điểm. Ứng viên bị loại khi card không khớp `in`, `out`, hoặc `hardware`. Trúng từ khóa trong mô tả skill không qua cổng này.

Bước 2, chỉ trên các ứng viên còn sống, mỗi hạng 0, 1, hoặc 2:

```text
U = 3*Outcome + 2*Fitness + 2*Reversibility + 2*Locality
    − 2*InterfaceCost − 3*UnresolvedRisk
```

| Hạng | 0 | 2 |
|---|---|---|
| Outcome | Không có ca kiểm chứng | Có lệnh hoặc test chỉ ra kết quả đổi |
| Fitness | Khớp một phần card | Khớp `in`, `out`, `hardware`, `failure_modes` |
| Reversibility | Xóa là mất dữ liệu hoặc không có lối về | Một PR đảo được |
| Locality | Sửa phải đụng từ hai Spoke trở lên | Sửa một module |
| InterfaceCost | Người gọi phải biết thứ tự nội bộ | Người gọi học 1–3 entry point |
| UnresolvedRisk | Chưa có đo đạc, chưa có issue cho rủi ro đã nêu | Rủi ro đã có test đỏ hoặc số đo |

- **KISS thực chất** được phản ánh qua: $\text{Locality} - \text{InterfaceCost}$. Không dùng biến KISS thứ tư tùy tiện.
- Mỗi hạng kèm một dòng chứng cứ (lệnh đã chạy, đường dẫn test, id card, số đo). Hạng không có chứng cứ bị tính 0 nếu là hạng cộng, và bị tính 2 nếu là `UnresolvedRisk`. Người viết phương án không được ghi `UnresolvedRisk = 0` cho phương án của chính mình khi chưa có test.
- Đẩy Seam lên Hub (bậc 4) cần một người đọc thứ hai xác nhận từng hạng. Điểm tự kể trong phần mô tả PR không đủ.
- GPI giữ nguyên vai trò của nó: cổng đặt skill theo ADR-0057. GPI không bị thay bằng $U$, và $U$ không bị thay bằng GPI. Skill đi qua GPI; lựa chọn thiết kế mã đi qua $U$.

### 4.7. Điều khoản G — Số subagent

- Giữ nguyên nguyên tắc **Single-Writer**: duy nhất một tác nhân được ghi vào cây mã nguồn sản xuất.
- Giữ nguyên trần ADR-0035 trong `design_it_twice.md`: tối đa 3 subagent song song khi thiết kế interface, không có subagent lồng nhau (không có cháu), đầu ra là tệp nháp trong scratch.
- Fan-out đọc lớn hơn 3 chỉ nằm trong workflow đã khai `agent_budget`.
- Trần "$\le 2$ subagent" bị bãi bỏ vì mâu thuẫn với trần 3 đã được chấp thuận của ADR-0035 và siết nhầm các tác vụ chỉ đọc (read-only research).

### 4.8. Điều khoản H — Văn phong lệnh cho agent

Mỗi điều cấm đi kèm việc thay thế ở ngay câu sau, tránh lỗi suy diễn phủ định (failure mode Negation). Mẫu chuẩn:

> Mã trong `services/` gọi `import_path` của card khi health check xanh. Khi health check đỏ, mã đó gọi Quarantine Adapter còn hạn.

Loại bỏ hoàn toàn các khẩu hiệu mơ hồ như "zero technical debt" hay "xác nhận 100%". Thay bằng các khẳng định định lượng và có căn cứ: "không thêm bản sao thứ hai của một capability đã có card xanh" và "NO_MATCH trên chỉ mục hash `<sha>`".

---

## 3. Quy tắc không làm (Anti-Patterns)

- **Không** bật kiểm tra ngặt nghèo để fail CI trên các từ khóa thông thường như `regex`, `pdf`, `requests`, hoặc trên các hàm xử lý tuần tự dài hơn 50 dòng có độ phức tạp thấp.
- **Không** chạy `compile_catalog.py` trong Spoke để tạo lệnh giả lập `--query`, tránh làm rơi vỡ các entry chính thống của Hub.
- **Không** hạ ngân sách tệp bằng cách archive các daemon vận hành dài hạn (`chatops_daemon.py`, `smart_watchdog.py`, `hermes_executive_mcp.py`, `mcp_server.py`, `model_auto_updater.py`, `peer_bridge_watcher.py`, `prune_spend_logs.py`).
- **Không** dùng ma trận tích số vô hướng (nhân 4 biến) vì nó dung túng cho các phương án rủi ro cao và phức tạp.

---

## 4. Bốn điều kiện để dỡ bỏ bảo lưu Nền tảng (Platform Reservations)

Bảo lưu nền tảng sẽ chính thức được dỡ bỏ và tích hợp thành Hard CI Gate trên toàn hệ sinh thái CCBA khi cả 4 điều kiện sau được nghiệm thu tại Hub:

1. **CLI `find-seam`**: Trả card theo `in` / `out` / `hardware`, có test cho trường hợp `NO_MATCH` và phân giải chính xác khi nhiều skill có cùng từ khóa.
2. **Linter Hợp đồng Nhập khẩu**: AST Import Linter ở Điều khoản E chạy xanh trên fixture hợp pháp, đỏ trên mã tự viết thay thế không có marker, và đỏ khi marker quá hạn.
3. **Chuẩn hóa Văn bản Cốt lõi**: Thay thế công thức tích 4 biến bằng Cổng nhị phân + Công thức $U$; đồng bộ viện dẫn `prototype_logic.md`, ADR-0046, ADR-0035, và ADR-0053.
4. **Chuẩn hóa Ngân sách Spoke Cleanliness**: `check_spoke_cleanliness.py` phân loại chính xác các tiến trình dài hạn (daemons/crontab) thông qua allowlist vai trò khai báo, phân tách hoàn toàn khỏi các script one-off tạm thời.
