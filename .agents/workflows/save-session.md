---
description: Lưu trạng thái session hiện tại vào session_log.md để giữ context giữa các conversation
---

# /save-session Workflow

> **Auto-save đang chạy độc lập (cron mỗi 30 phút):**
> Script `.agents/scripts/auto_state_save.sh` tự động lưu system state vào `.agents/system_state.md`
> ngay cả khi app đã tắt. Khi bắt đầu session mới, đọc file đó để restore context nhanh.

Chạy workflow này ở cuối mỗi buổi làm việc để đảm bảo context không bị mất giữa các conversation.

## Bước 1 — Thu thập trạng thái hệ thống

// turbo
```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.RunningFor}}"
```

## Bước 2 — Kiểm tra kết quả benchmark gần nhất (nếu có)

// turbo
```bash
# Tìm file benchmark result mới nhất (nếu đã save với --output)
ls -t /home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/scripts/benchmark_*.json 2>/dev/null | head -3
```

## Bước 3 — Cập nhật session_log.md

Dựa vào output từ Bước 1 và 2, cập nhật file `.agents/session_log.md`:

- **Cập nhật bảng "Trạng thái hệ thống"** với output từ `docker ps`
- **Cập nhật bảng "Benchmark"** nếu có kết quả mới (so sánh với session trước)
- **Cập nhật danh sách "Thay đổi đã thực hiện"**: đánh dấu `[x]` những việc đã xong trong session này
- **Cập nhật danh sách "Thực nghiệm đang chờ"**: thêm task mới phát sinh trong session
- **Thêm section mới** với ngày tháng nếu đây là session mới hơn

## Bước 4 — Xác nhận đã lưu

```
✅ session_log.md đã được cập nhật.
📍 Context được lưu tại: .agents/session_log.md
```

## Format section mới

Khi tạo section mới cho một ngày/session mới, dùng template:

```markdown
## 🟢 Session: YYYY-MM-DD (user)

### Trạng thái hệ thống (cuối session)
[bảng docker ps]

### Kết quả / Benchmark mới
[nếu có]

### Thay đổi đã thực hiện
- [x] ...

### Thực nghiệm đang chờ
- [ ] ...
```
