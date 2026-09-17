import requests
import time
import urllib3
urllib3.disable_warnings()

GATEWAY_URL = "http://100.79.241.120:8045/v1/chat/completions"
HEADERS = {
    "Authorization": "Bearer sk-9a13a60d641a42f9a74b18d58d44a358",
    "Content-Type": "application/json"
}

payload = {
    "model": "gemini-3.1-flash-lite",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 10,
    "safety_settings": [
        {
            "category": "HARM_CATEGORY_HARASSMENT",
            "threshold": "BLOCK_NONE"
        },
        {
            "category": "HARM_CATEGORY_HATE_SPEECH",
            "threshold": "BLOCK_NONE"
        },
        {
            "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
            "threshold": "BLOCK_NONE"
        },
        {
            "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
            "threshold": "BLOCK_NONE"
        }
    ]
}

start_time = time.time()
response = requests.post(GATEWAY_URL, headers=HEADERS, json=payload, timeout=15)
duration = time.time() - start_time

if response.status_code == 200:
    print(f"✅ THÀNH CÔNG ({duration:.2f}s)")
    print(response.json())
else:
    print(f"❌ THẤT BẠI ({duration:.2f}s) - Lỗi HTTP {response.status_code}: {response.text.strip()}")
