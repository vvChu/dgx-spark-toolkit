import base64
import requests
import fitz  # PyMuPDF
import json
import time

PDF_PATH = "/app/data/legal_docs_source/Linh vuc_BTP/20250610_QD1111-TTg_Ban hanh DS dv SNCL thuoc BTP_ththeQD792-2023.pdf"
API_KEY = "AIzaSyC2Tx-whTFq7oeZjjqtp9gEsxecTVgGrZA"
DIRECT_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemma-3-27b-it:generateContent?key={API_KEY}"

def main():
    print(f"Loading and extracting page 1 from {PDF_PATH}...")
    try:
        doc = fitz.open(PDF_PATH)
        page = doc.load_page(0)  
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("jpeg")
        b64_image = base64.b64encode(img_bytes).decode('utf-8')
        doc.close()
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return

    print("Sending Direct request to Google AI Studio for Gemma-3-27B...")
    
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": "Trích xuất toàn bộ nội dung văn bản trong hình ảnh này. Giữ nguyên định dạng và lưu bảng dưới dạng markdown."},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": b64_image
                        }
                    }
                ]
            }
        ]
    }

    t0 = time.time()
    try:
        response = requests.post(DIRECT_URL, json=payload, headers={"Content-Type": "application/json"})
        response.raise_for_status()
        
        result = response.json()
        try:
            text_output = result["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            text_output = json.dumps(result, indent=2)
            
        elapsed = time.time() - t0
        print(f"\n--- SUCCESS (Time: {elapsed:.2f}s) ---\n")
        print("======== Gemma-3-27B OCR Output ========")
        print(text_output[:1000] + "...\n[TRUNCATED_FOR_CONSOLE]")
        print("========================================")
        
        with open("/app/exports/gemma_direct_ocr_result.md", "w", encoding="utf-8") as f:
            f.write(text_output)
            
    except requests.exceptions.HTTPError as e:
        print(f"\n--- API ERROR {e.response.status_code} ---")
        print(e.response.text)
    except Exception as e:
        print(f"\n--- REQUEST ERROR ---\n{e}")

if __name__ == "__main__":
    main()
