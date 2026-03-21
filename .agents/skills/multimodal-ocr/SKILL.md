---
name: Multimodal OCR
command: /multimodal-ocr
description: Đặc trị rút trích dữ liệu từ file Hóa đơn, Bản vẽ thô thành định dạng chuẩn JSON.
type: skill
category: custom
enabled: true
version: v3.0
---

# Kỹ năng: Multimodal OCR & Data Extractor

Bạn có rất nhiều hóa đơn, phiếu thu, hoặc tài liệu báo cáo dạng ảnh/PDF cần được nhập liệu vào phần mềm quản trị (Ví dụ: IDOP)? Hãy dùng Skill OCR & Data Extractor này để biến dữ liệu tĩnh thành cấu trúc JSON linh hoạt nhờ vào khả năng multimodal mạnh mẽ của Qwen 3.5 35B.

## Cách sử dụng

Mở Terminal và thực thi lệnh:

```bash
python .agent/skills/multimodal-ocr/scripts/data_extractor.py <duong_dan_anh> "<yeu_cau_trich_xuat_dac_biet_neu_co>"
```

### Ví dụ Hóa đơn
```bash
python .agent/skills/multimodal-ocr/scripts/data_extractor.py "receipt_1294.jpg" "Trích xuất [Tên công ty], [Ngày xuất], [Tổng Số tiền], [VAT]. Lưu dưới dạng JSON."
```

### Ví dụ Bản vẽ Kỹ thuật
```bash
python .agent/skills/multimodal-ocr/scripts/data_extractor.py "banve_cau.jpg" "Liệt kê danh sách số lượng vật tư thép được ghi chú trên bản vẽ. Trả về format JSON."
```

Hệ thống sẽ ép mô hình loại bỏ các lời giải thích dong dài, trả thẳng ra một mảng bộ nhớ chứa JSON, sẵn sàng gửi vào API Backend.
