# Ticket [TICK-04]: Xây dựng Script Tự Động Kiểm Tra Cập Nhật & Tích hợp CI Audit

**Bản đồ cha:** [Bản đồ Định hướng Hiện đại hóa Dependency](../map.md)  
**Phân loại:** `Task [AFK]`  
**Trạng thái:** `Completed (Hoàn thành)`  
**Assignee:** Antigravity Agent  
**Phụ thuộc:** [TICK-01](TICK-01-app-lockfile-uv-compile.md), [TICK-02](TICK-02-ci-conftest-stub-speedup.md) (Đã hoàn thành)  

---

## 1. Mục tiêu
Xây dựng một script vận hành duy nhất `scripts/check_dependency_updates.sh` và bổ sung job quét an ninh phòng vệ vào GitHub Actions workflow, giúp việc kiểm tra phiên bản mới diễn ra nhanh chóng, thuận tiện và an toàn.

## 2. Chi tiết Triển khai
1. Đã tạo script `scripts/check_dependency_updates.sh`:
   - Hỗ trợ cờ `--all`, `--outdated`, `--audit`.
   - Kiểm tra `uv pip list --outdated` cho Python backend kèm hướng dẫn kiến trúc 3 Tiers (Tier A tiện ích, Tier B DB client, Tier C hardware pinned).
   - Kiểm tra `npm outdated` cho React frontend.
   - Chạy `uvx pip-audit` quét an ninh trên `requirements-ci.txt` và cảnh báo advisories trên `requirements-app.lock`.
   - Chạy `npm audit --omit=dev --audit-level=critical` kiểm tra lỗ hổng nghiêm trọng trên frontend, bảo vệ thư viện đồ thị `react-force-graph`.
2. Cập nhật `.github/workflows/ci.yml`:
   - Bổ sung job `security-audit`:
     ```yaml
     security-audit:
       name: Security Audit
       runs-on: ubuntu-latest

       steps:
         - uses: actions/checkout@v4

         - name: Install uv
           uses: astral-sh/setup-uv@v5

         - name: Backend pip-audit
           run: uvx pip-audit -r services/rag-service/requirements-ci.txt

         - uses: actions/setup-node@v4
           with:
             node-version: "20"
             cache: npm
             cache-dependency-path: services/frontend/package-lock.json

         - name: Frontend npm audit
           working-directory: services/frontend
           run: npm audit --omit=dev --audit-level=critical
     ```

## 3. Tiêu chí Nghiệm thu (Acceptance Criteria)
- [x] Script `scripts/check_dependency_updates.sh` thực thi thành công trên DGX Spark với cờ exit 0 và định dạng màu phân biệt rõ ràng.
- [x] CI workflow chạy bổ sung job security-audit thành công không làm nghẽn PR.
- [x] Không có false-alarm nào từ các devDependencies của frontend gây cản trở build.
