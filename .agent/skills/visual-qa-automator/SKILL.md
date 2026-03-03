---
description: Dùng AI rà soát lỗi giao diện (CSS, Layout) bằng mắt thường bằng cách so sánh ảnh thực tế và ảnh thiết kế gốc.
---

# Kỹ năng: Visual QA Automator

Kỹ năng này biến Qwen3-VL thành một nhân viên Kiểm thử UI (Tester) tự động. Nó nhận vào 2 hình ảnh (1 là ảnh chụp màn hình đang code thực tế trên web, 1 là ảnh Mockup yêu cầu của Designer) và sẽ so sánh, chỉ ra những điểm sai lệch bằng văn bản.

## Cách sử dụng

Mở Terminal trong dự án DGX Spark Toolkit và chạy:

```bash
python .agent/skills/visual-qa-automator/scripts/visual_tester.py <anh_thiet_ke> <anh_thuc_te>
```

Ví dụ:
```bash
python .agent/skills/visual-qa-automator/scripts/visual_tester.py figma_design.png my_coded_ui.png
```

Agent sẽ in ra cho bạn:
- Độ tương đồng % (Similarity Score)
- Danh sách những thẻ bị sai màu, lệch pixel, sai khoảng cách Padding/Margin
- Gợi ý cách để bạn sửa Code Tailwind/CSS cho đúng thiết kế.
