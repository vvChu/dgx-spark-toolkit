---
name: ai-ui-builder
description: Chuyên gia sinh Code Frontend (React/Tailwind) từ ảnh Mockup/Thiết kế bằng sức mạnh của Qwen 3.5 35B Local (hoặc Gemini-3 Flash fallback).
---

# Kỹ năng: AI UI/UX Builder

Skill này cung cấp kịch bản cho phép bạn hoặc Team Design có thể đưa cho hệ thống một bức ảnh (Figma Mockup, Bản vẽ tay, Screenshot trang tham khảo...) và nhận lại file Source Code React kết hợp Tailwind CSS hoàn chỉnh. Kỹ năng này hiện được tăng cường tự động bằng model **Qwen 3.5 35B Local** (tốc độ >180 t/s) thông qua AI Gateway (có thể fallback sang Gemini 3 Flash nếu cần độ phân giải cực cao).

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
- Tự động nhận diện cấu trúc Layout (chia lưới grid/flex, breakpoints responsive).
- Tự động bắt mã màu (Color Extraction) và thẩm mỹ thiết kế hiện đại (bo góc, đổ bóng).
- Hỗ trợ thư viện icon hiện đại (như lucide-react).
- Tự dọn sạch Code dư thừa, chỉ in ra mã nguồn thuần HTML/React.
- Output sinh ra file `.tsx` độc lập để sử dụng ngay lập tức.
