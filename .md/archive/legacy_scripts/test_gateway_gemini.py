import requests
import time
import urllib3
urllib3.disable_warnings()

GATEWAY_URL = "http://127.0.0.1:8090/v1/chat/completions"
HEADERS = {
    "Authorization": "Bearer sk-spark-secure-key-2026",
    "Content-Type": "application/json"
}

payload = {
    "model": "gemini-3.1-flash-lite",
    "messages": [{"role": "user", "content": "Hello Gemini 3.1 Flash Lite!"}],
    "max_tokens": 10
}

start_time = time.time()
try:
    response = requests.post(GATEWAY_URL, headers=HEADERS, json=payload, timeout=20)
    duration = time.time() - start_time
    if response.status_code == 200:
        print(f"✅ THÀNH CÔNG qua AI Gateway local ({duration:.2f}s)")
        print(response.json()["choices"][0]["message"]["content"])
    else:
        print(f"❌ THẤT BẠI ({duration:.2f}s) - Lỗi HTTP {response.status_code}: {response.text.strip()}")
except Exception as e:
    print(f"Lỗi: {e}")
