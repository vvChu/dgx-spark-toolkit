import requests
import time
import urllib3
urllib3.disable_warnings()

GATEWAY_URL = "http://100.79.241.120:8045/v1/chat/completions"
HEADERS = {
    "Authorization": "Bearer sk-9a13a60d641a42f9a74b18d58d44a358",
    "Content-Type": "application/json"
}

MODELS_TO_TEST = [
    "gemini-3.1-pro-low",
    "claude-sonnet-4-6",
    "gemini-3-flash-agent",
    "gemini-3.1-flash-lite",
    "gpt-oss-120b-medium",
    "gemini-3.1-flash-image",
    "gemini-2.5-pro",
    "gemini-pro-agent",
    "claude-opus-4-6-thinking",
    "gemini-2.5-flash-lite",
    "gemini-3.1-pro-high",
    "gemini-2.5-flash-thinking",
    "gemini-3-flash",
    "gemini-2.5-flash",
    "gemini-3-pro-image"
]

print("=== BẮT ĐẦU TEST KẾT NỐI UPSTREAM API PROXY (PORT 8045) ===\n")

for model in MODELS_TO_TEST:
    print(f"[*] Đang test model: {model} ...", end="", flush=True)
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Hello"}],
        "max_tokens": 10
    }
    
    start_time = time.time()
    try:
        response = requests.post(GATEWAY_URL, headers=HEADERS, json=payload, timeout=15)
        duration = time.time() - start_time
        
        if response.status_code == 200:
            print(f" ✅ THÀNH CÔNG ({duration:.2f}s)")
        else:
            print(f" ❌ THẤT BẠI ({duration:.2f}s) - Lỗi HTTP {response.status_code}: {response.text.strip()}")
    except requests.exceptions.Timeout:
        print(f" ⏳ TIMEOUT sau 15s")
    except Exception as e:
        print(f" 💥 LỖI KẾT NỐI: {e}")

print("\n=== HOÀN TẤT TEST ===")
