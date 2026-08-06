import os
import base64
import time
import httpx

GATEWAY_URL = os.getenv("VLLM_API_BASE", "http://ai-gateway:4000/v1")
API_KEY = os.getenv("LITELLM_MASTER_KEY", "sk-spark-secure-key-2026")

SHORT_STRICT_PROMPT = """Bạn là công cụ OCR. Trích xuất chính xác 100% nội dung chữ trong ảnh và đưa vào trong thẻ <TEXT></TEXT>. 
CẤM giải thích, CẤM thêm bất kỳ chữ nào bên ngoài block <TEXT></TEXT>."""

import fitz
doc = fitz.open("./services/rag-service/data/legal_test/Luat_50-2014-QH13_Luat Xay dung_18-6-2014.pdf")
page = doc[21]
pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))
img_bytes = pix.tobytes("jpeg")
b64 = base64.b64encode(img_bytes).decode("utf-8")

payload = {
    "model": "ocr-primary",
    "messages": [
        {"role": "system", "content": SHORT_STRICT_PROMPT},
        {"role": "user", "content": [{"type": "text", "text": "OCR:"}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]},
    ],
    "max_tokens": 8192,
    "temperature": 0.0,
}

t0 = time.time()
resp = httpx.post(f"{GATEWAY_URL}/chat/completions", headers={"Authorization": f"Bearer {API_KEY}"}, json=payload, timeout=300)
content = resp.json()["choices"][0]["message"].get("content", "")
print(f"Time: {time.time()-t0:.1f}s | Chars: {len(content)}")
print("==== gemini-3.1-flash-lite (XML constraints) ====")
print(content[:500])
