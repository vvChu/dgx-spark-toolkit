import httpx
import json
import os

VLLM_API_BASE = "http://host.docker.internal:8004/v1"
MODEL = "qwen3.5-35b"

prompt = (
    "Extract the following metadata from this Vietnamese legal document text: "
    "1. Document Number (Số hiệu), 2. Signing Date (Ngày ban hành: YYYY-MM-DD), "
    "3. Document Type (QD, TT, ND, etc.), 4. Issuing Authority (BXD, TTg, etc.). "
    "Respond ONLY with a JSON object, no explanation."
)

text = """
CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
Độc lập - Tự do - Hạnh phúc
-------
Số: 1486/QĐ-TTg                       Hà Nội, ngày 24 tháng 11 năm 2023

QUYẾT ĐỊNH
Phê duyệt Quy hoạch tỉnh Hà Tĩnh thời kỳ 2021 - 2030, tầm nhìn đến năm 2050
THỦ TƯỚNG CHÍNH PHỦ
Căn cứ Luật Tổ chức Chính phủ ngày 19 tháng 6 năm 2015; Luật sửa đổi, bổ sung một số điều của Luật Tổ chức Chính phủ và Luật Tổ chức chính quyền địa phương ngày 22 tháng 11 năm 2019;
"""

messages = [
    {"role": "system", "content": "You are a precise JSON extractor. You MUST output ONLY raw JSON. Do NOT include any 'Thinking Process', 'Analysis', or preamble. NO text before or after the JSON block. Start exactly with '{' and end exactly with '}'."},
    {"role": "user", "content": f"Extract metadata as JSON for this document: {text}\n\nRequired format:\n{{\"doc_number\": \"...\", \"doc_date\": \"YYYY-MM-DD\", \"doc_type\": \"...\", \"authority\": \"...\"}}"}
]

payload = {
    "model": MODEL,
    "messages": messages,
    "max_tokens": 1024,
    "temperature": 0.0,
}

try:
    resp = httpx.post(f"{VLLM_API_BASE}/chat/completions", json=payload, timeout=60)
    print(f"Status: {resp.status_code}")
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    print(f"RAW CONTENT:\n{content}")
    
    # Test the extraction logic
    from production_ingest import _extract_json_from_response
    extracted = _extract_json_from_response(data)
    print(f"EXTRACTED JSON:\n{json.dumps(extracted, indent=2)}")
except Exception as e:
    print(f"Error: {e}")
    # Print raw response if json parsing fails
    if 'resp' in locals():
        print(f"Raw Status: {resp.status_code}")
        print(f"Raw Response: {resp.text}")
