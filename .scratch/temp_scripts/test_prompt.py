import os
import base64
import time
import httpx

GATEWAY_URL = os.getenv("VLLM_API_BASE", "http://ai-gateway:4000/v1")
API_KEY = os.getenv("LITELLM_MASTER_KEY", "sk-spark-secure-key-2026")

MINIMAL_PROMPT = """Bạn là máy quét OCR pháp lý. NHIỆM VỤ:
Trích xuất chính xác 100% văn bản từ ảnh.
CHỈ TRẢ VỀ nội dung text, tuyệt đối KHÔNG giải thích, KHÔNG chào hỏi, KHÔNG lặp lại yêu cầu."""

import fitz
doc = fitz.open("/app/data/legal_test/Luat_50-2014-QH13_Luat Xay dung_18-6-2014.pdf")
page = doc[21]
pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))
img_bytes = pix.tobytes("jpeg")
b64 = base64.b64encode(img_bytes).decode("utf-8")

payload = {
    "model": "gemini-3.1-flash-lite",
    "messages": [
        {"role": "system", "content": MINIMAL_PROMPT + f"\n\n[ID: {time.time()}]"},
        {"role": "user", "content": [{"type": "text", "text": "OCR:"}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]},
    ],
    "max_tokens": 8192,
    "temperature": 0.0,
}

t0 = time.time()
resp = httpx.post(f"{GATEWAY_URL}/chat/completions", headers={"Authorization": f"Bearer {API_KEY}"}, json=payload, timeout=300)
content = resp.json()["choices"][0]["message"].get("content", "")
print(f"Time: {time.time()-t0:.1f}s | Chars: {len(content)}")
print("Preview:\n" + content[:300])
