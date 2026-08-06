import base64
import requests
import json
import os
import fitz

pdf_path = "/app/data/legal_test/Luat_31-2024-QH15_Luat Dat dai_thaytheLuat45-2013.pdf"

def test_ocr():
    doc = fitz.open(pdf_path)
    page = doc[0] # Page 1
    pix = page.get_pixmap(dpi=300)
    img_data = pix.tobytes("jpeg")
    b64 = base64.b64encode(img_data).decode("utf-8")
    
    prompt = """Bạn là máy OCR. CHỈ xuất văn bản thuần túy từ ảnh.
QUY TẮC BẮT BUỘC:
1. Trích xuất TOÀN BỘ nội dung pháp lý, giữ nguyên thứ tự từ trên xuống dưới
2. Giữ nguyên cấu trúc: Điều, Khoản, Điểm, Chương, Mục, Phần, Phụ lục
3. BẢNG BIỂU → Markdown table (| col1 | col2 |) — CHỈ KHI THẤY BẢNG THẬT TRONG ẢNH
4. Giữ nguyên số hiệu, ngày tháng, tên cơ quan
5. TUYỆT ĐỐI KHÔNG thêm nhận xét, giải thích, đánh số, phân tích
6. KHÔNG mô tả font, style, bold, caps
7. Mỗi đề mục/mục số (1.1, 1.2, 2.3.4...) PHẢI nằm trên dòng riêng biệt
8. KHÔNG dùng markdown heading (#), CHỈ dùng markdown cho bảng biểu (|)
9. KHÔNG viết tiếng Anh
10. CHỈ VĂN BẢN THUẦN TÚY — NGUYÊN VĂN từng chữ trong ảnh
11. KHÔNG BAO GIỜ tự thêm nội dung, từ ngữ, hoặc bảng biểu mà KHÔNG CÓ trong ảnh
12. KHÔNG tự sáng tạo hoặc suy luận nội dung — chỉ đọc chính xác những gì hiển thị

BỎ QUA HOÀN TOÀN (KHÔNG trích xuất):
- Logo, watermark, header điện tử (VGP, CỔNG THÔNG TIN ĐIỆN TỬ, chinhphu.vn, email, thời gian ký)
- Chữ viết tay, ghi chú tay (TTĐT(2), TT(2), bút đỏ...)
- Con dấu điện tử, con dấu đỏ, chữ ký số, chữ ký tay
- Khối "Nơi nhận:" và toàn bộ danh sách phân phối sau đó
- Tên/chức danh người ký (KT. THỦ TƯỚNG, PHÓ THỦ TƯỚNG, TM., tên riêng)
- Mã lưu trữ (Lưu: VT, KGVX...)
- Số trang đứng riêng"""

    payload = {
        "model": "gemini-3-flash",
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": [
                {"type": "text", "text": "OCR:"},
                 {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            ]}
        ],
        "temperature": 0.0
    }
    
    url = "http://ai-gateway:4000/v1/chat/completions"
    headers = {"Authorization": f"Bearer {os.environ.get('LITELLM_MASTER_KEY', '1234')}"}
    resp = requests.post(url, json=payload, headers=headers)
    
    try:
        print(resp.json()['choices'][0]['message']['content'])
    except Exception as e:
        print("Error:", resp.text)

test_ocr()
