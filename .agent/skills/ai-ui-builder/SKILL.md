---
description: Chuyên gia sinh Code Frontend (React/Tailwind) từ ảnh Mockup/Thiết kế bằng sức mạnh của chuẩn Qwen3-VL chạy local trên DGX Spark.
---

# Kỹ năng: AI UI/UX Builder

Skill này cung cấp kịch bản cho phép bạn hoặc Team Design có thể đưa cho hệ thống một bức ảnh (Figma Mockup, Bản vẽ tay, Screenshot trang tham khảo...) và nhận lại file Source Code React kết hợp Tailwind CSS hoàn chỉnh.

## Cách sử dụng

Mở Terminal trong dự án DGX Spark Toolkit và thực thi lệnh sau:

### Phân tích từ File cục bộ
```bash
python .agent/skills/ai-ui-builder/scripts/ui_generator.py "/duong/dan/den/anh.png"
```

### Phân tích từ URL Image
```bash
python .agent/skills/ai-ui-builder/scripts/ui_generator.py "https://example.com/hinh-anh.jpg"
```

### Tính năng đặc thù:
- Tự động nhận diện cấu trúc Layout (chia lưới grid/flex).
- Tự động bắt mã màu (Color Extraction) từ thiết kế.
- Tự dọn sạch Code dư thừa (Loại bỏ Markdown rườm rà), chỉ in ra mã nguồn thuần HTML/React.
- Có lưu vào một file preview độc lập bên ngoài để dễ dàng xem trước.
