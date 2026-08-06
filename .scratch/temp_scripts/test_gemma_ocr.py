import base64
import requests
import fitz  # PyMuPDF
import sys
import time

PDF_PATH = "/home/vvc/Public/VB phap quy/Linh vuc_BTP/20250610_QD1111-TTg_Ban hanh DS dv SNCL thuoc BTP_ththeQD792-2023.pdf"
GATEWAY_URL = "http://localhost:4001/v1/chat/completions"

def main():
    print(f"Loading and extracting page 1 from {PDF_PATH}...")
    try:
        doc = fitz.open(PDF_PATH)
        page = doc.load_page(0)  # load the first page
        # Render at 150 DPI for a reasonable image size
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("jpeg")
        b64_image = base64.b64encode(img_bytes).decode('utf-8')
        doc.close()
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return

    print("Sending OCR request to Gemma-3-27B via ai-gateway...")
    
    payload = {
        "model": "gemma-3-27b",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Trích xuất toàn bộ nội dung văn bản trong hình ảnh này. Giữ nguyên cấu trúc, nếu có bảng biểu thì hãy chuyển thành định dạng markdown. Đừng thêm bất kỳ bình luận nào khác."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64_image}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 4000,
        "temperature": 0.1
    }

    t0 = time.time()
    try:
        response = requests.post(
            GATEWAY_URL, 
            json=payload, 
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        
        result = response.json()
        if "error" in result:
             print(f"\n--- API ERROR ---\n{result['error']}")
             return
             
        text_output = result["choices"][0]["message"]["content"]
        elapsed = time.time() - t0
        print(f"\n--- SUCCESS (Time: {elapsed:.2f}s) ---\n")
        print("======== Gemma-3-27B OCR Output ========")
        print(text_output)
        print("========================================")
        
        # Save output for inspection
        with open("gemma_ocr_result.md", "w", encoding="utf-8") as f:
            f.write(text_output)
        print("\nMẫu OCR đã được lưu tại: gemma_ocr_result.md")
            
    except Exception as e:
        print(f"\n--- REQUEST ERROR ---\n{e}")
        try:
            print("Response text:", response.text)
        except:
            pass

if __name__ == "__main__":
    main()
